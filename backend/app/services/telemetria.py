"""Servicio de telemetria en memoria.

Recibe las muestras que envia el daemon (POST /telemetria/muestras) y las
mantiene en un ring buffer multi-nodo SIN persistirlas (regla SteelNort:
no se guarda telemetria cruda). Tambien conserva un log corto de
mutaciones para alimentar el endpoint SSE /telemetria/live por cursor,
haciendo la difusion sencilla y segura entre hilos.

Ademas centraliza la persistencia de muestras NORMALES (Muestras_Normales)
y los logs de reconocimiento/clasificacion, para que el router de
telemetria quede fino.

Los eventos de anomalia los procesa ``app.services.anomalias``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.model_muestra_normal import MuestrasNormales
from app.services.nodos import obtener_o_crear_nodo

log = logging.getLogger("steelnort.telemetria")

# Nodos que ya fueron "vistos" en este arranque (para no repetir el
# log de conexion en cada muestra).
_nodos_vistos: set[str] = set()

# Configuración por defecto del ring buffer (muestras por nodo).
CAPACIDAD_POR_NODO = 220          # ~25 min a STREAM_INTERVAL=7s
MAX_MUTACIONES = 500              # mochila de mutaciones para SSE
TIMEOUT_SIN_SIGNAL = 21           # > 3 * intervalo (7s) => nodo desconectado


class TelemetriaBuffer:
    """Ring buffer multi-nodo + difusion SSE.

    Cada nodo (ej. "Servidor Negocio") mantiene su propia serie. El acceso
    se sincroniza con un candado; las mutaciones recientes se guardan en
    una cola FIFO para que el cliente SSE pueda leer las novedades a
    partir de un ``seq``.
    """

    def __init__(self, capacidad: int = CAPACIDAD_POR_NODO,
                 max_mutaciones: int = MAX_MUTACIONES) -> None:
        self._capacidad = max(1, capacidad)
        self._max_mutaciones = max(1, max_mutaciones)
        self._por_nodo: dict[str, deque] = {}
        self._ultima: dict[str, dict] = {}
        self._mutaciones: deque[tuple[int, str, dict]] = deque()
        self._seq = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def agregar(self, nodo: str, muestra: dict) -> None:
        """Guarda una muestra para ``nodo`` y la publica en el feed SSE."""
        if not isinstance(nodo, str) or not nodo:
            nodo = "desconocido"
        with self._lock:
            serie = self._por_nodo.setdefault(nodo, deque(maxlen=self._capacidad))
            serie.append(muestra)
            self._ultima[nodo] = muestra
            self._seq += 1
            self._mutaciones.append((self._seq, nodo, muestra))
            if len(self._mutaciones) > self._max_mutaciones:
                self._mutaciones.popleft()

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    def serie(self, nodo: str, n: int | None = None) -> list[dict]:
        """Ultimas ``n`` muestras de un nodo (todas si ``n`` es None)."""
        with self._lock:
            serie = self._por_nodo.get(nodo)
            if not serie:
                return []
            if n is None or n >= len(serie):
                return list(serie)
            return list(serie)[-n:]

    def ultima(self, nodo: str) -> dict | None:
        with self._lock:
            return self._ultima.get(nodo)

    def nodos(self) -> list[str]:
        with self._lock:
            return list(self._por_nodo.keys())

    def desde_seq(self, seq: int) -> list[tuple[int, str, dict]]:
        """Devuelve las mutaciones con seq > ``seq`` para el feed SSE."""
        with self._lock:
            return [(s, n, m) for s, n, m in self._mutaciones if s > seq]

    def ultimo_seq(self) -> int:
        with self._lock:
            return self._seq

    def estados(self) -> dict:
        """Heartbeat: ultima muestra por nodo y tiempo desde la senal."""
        now = time.time()
        res: dict[str, Any] = {}
        with self._lock:
            for nodo, muestra in self._ultima.items():
                ts = _ts_dato(muestra)
                hace = max(0.0, now - ts) if ts else None
                res[nodo] = {
                    "hace_seg": round(hace, 1) if hace is not None else None,
                    "estado": "offline" if (hace or 999) > TIMEOUT_SIN_SIGNAL else "operativo",
                    "ultima": muestra,
                }
        return res


def _ts_dato(muestra: dict) -> float | None:
    """Extrae el timestamp (epoch) de una muestra enviada por el daemon."""
    ts = muestra.get("fecha_str") or muestra.get("ts")
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(ts)).timestamp()
    except Exception:
        return None


# Instancia unica a nivel de aplicacion.
buffer_telemetria = TelemetriaBuffer()


# ----------------------------------------------------------------------
# Persistencia y logs (usados por el router de telemetria)
# ----------------------------------------------------------------------


def persistir_muestra_normal(
    db: Session,
    ndo_cod: int,
    fec: datetime,
    prediccion: dict,
    ventana: int = 10,
    reg_usu: str = "telemetria",
) -> None:
    """Registra una muestra NORMAL en Muestras_Normales (datos de retrain)."""
    feats_json = json.dumps(prediccion.get("features", {}), default=str)
    db.add(MuestrasNormales(
        mno_ndo=ndo_cod,
        mno_fec=fec,
        mno_score=Decimal(str(prediccion.get("score", 0))),
        mno_umbral=Decimal(str(prediccion.get("umbral", 0))),
        mno_feats=feats_json,
        mno_ventana=ventana,
        reg_usu=reg_usu,
    ))


def guardar_muestra_normal(
    db: Session,
    nodo_nombre: str,
    nodo_ip: str,
    prediccion: dict,
    ventana: dict,
) -> None:
    """Persiste la muestra NORMAL de telemetria en vivo.

    Solo se llama cuando ``prediccion['es_anomalia']`` es False.
    Guarda las features como JSON para poder reconstruir el
    dataset de entrenamiento posteriormente.
    """
    ndo_cod = obtener_o_crear_nodo(db, nodo_nombre, nodo_ip, origen="telemetria")
    if ndo_cod is None:
        return
    persistir_muestra_normal(
        db, ndo_cod, _utc_now(), prediccion,
        ventana=ventana.get("ventana", 10), reg_usu="telemetria",
    )


def log_reconocimiento(nodo: str, ip: str, recien_alta: bool) -> None:
    """Deja en el terminal/log la validacion de conexion del servidor.

    - Primera vez en TODA la vida (nodo recien registrado): "RECONOCIDO".
    - Primera vez en este arranque (nodo ya registrado, acaba de
      conectarse): "conectado".
    El resto de muestras ya no generan este log (evita ruido).
    """
    if recien_alta:
        _nodos_vistos.add(nodo)
        log.info(
            "[TELEMETRIA] Servidor/Nodo RECONOCIDO por el sistema: %s (%s) ->"
            " registrado en Nodos_SCADA",
            nodo, ip,
        )
        return
    if nodo not in _nodos_vistos:
        _nodos_vistos.add(nodo)
        log.info(
            "[TELEMETRIA] Servidor/Nodo %s (%s) conectado - enviando telemetria",
            nodo, ip,
        )


def log_prediccion(nodo: str, prediccion: dict, ventana: int) -> None:
    """Clasificacion visible en el terminal para validar el modelo."""
    marca = "ANOMALIA" if prediccion["es_anomalia"] else "NORMAL"
    log.info(
        "[TELEMETRIA] NODO=%s | %s | es_anomalia=%s | score=%.4f | umbral=%.4f | ventana=%d",
        nodo, marca, prediccion["es_anomalia"],
        prediccion["score"], prediccion["umbral"], ventana,
    )


def _utc_now() -> datetime:
    """Equivale a ``datetime.utcnow()`` sin caer en la API deprecada."""
    from app.utils import utc_now
    return utc_now()