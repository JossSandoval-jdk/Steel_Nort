"""Servicio de telemetria en memoria.

Recibe las muestras que envia el daemon (POST /telemetria/muestras) y las
mantiene en un ring buffer multi-nodo SIN persistirlas (regla SteelNort:
no se guarda telemetria cruda). Tambien conserva un log corto de
mutaciones para alimentar el endpoint SSE /telemetria/live por cursor,
haciendo la difusion sencilla y segura entre hilos.

Los eventos de anomalia los procesa ``app.services.anomalias``.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

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