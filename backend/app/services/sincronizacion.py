"""Monitor de sincronizacion de la cadena Collector -> VPS -> Web SCADA.

Vigila la conectividad de los dos eslabones criticos del sistema:

  1. **VPS SQL Server** (fuente de logs y metricas): el SQL Server de
     Podman en ``1434`` simula la instancia de negocio remota. Si se
     pierde, la telemetria deja de llegar y no hay que "ver la
     sincronizacion" a ciegas.
  2. **Daemon/collector -> web**: el daemon publica una muestra cada
     ``STREAM_INTERVAL`` segundos; si deja de enviar mas alla del
     margen (``TIMEOUT_SIN_SIGNAL``), el nodo queda ``offline``.

Regla de alertado:
  - Estado perdido  -> abre una alerta nueva en ``Alertas`` (y una causa
    raiz hoja), SOLO si no hay otra abierta del mismo tipo.
  - Estado recuperado -> resuelve la/las alertas abiertas del tipo
    afectado.
  - Los enlaces nunca conectados (arranque, sin daemon aun) NO generan
    alertas: solo se reportan en el estado en vivo.

El estado en vivo del monitor se expone via ``GET /telemetria/sincronizacion``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

from app.database import SessionLocal
from app.models.model_alerta import Alertas, CausasRaiz
from app.services.telemetria import buffer_telemetria

log = logging.getLogger("steelnort.sincronizacion")

# Intervalo de revision del monitor (segundos); ajustable por env.
SINC_INTERVAL = int(os.getenv("SINC_INTERVAL", "15"))
# Margen de silencio para considerar perdida la conexion daemon->web.
# El buffer ya usa TIMEOUT_SIN_SIGNAL (~21s > 3x STREAM_INTERVAL).
SINC_TIMEOUT = 21
# Timeout de la prueba de conexion contra el SQL de negocio (VPS).
VPS_SQL_TIMEOUT = 5

_TIPO_VPS = "conexion_vps_sql"
_TIPO_DAEMON = "conexion_daemon"

_stop = threading.Event()
_thread: threading.Thread | None = None
_lock = threading.Lock()

# Estado en vivo del monitor (leido por el endpoint).
estado_actual: dict = {}


def _test_vps_sql() -> bool:
    """Intenta conectar al SQL Server de negocio (Podman/VPS)."""
    import pyodbc  # noqa: PLC0415

    try:
        from app.collector.config import SQL_SERVER_CONN_STR
        conn = pyodbc.connect(SQL_SERVER_CONN_STR, timeout=VPS_SQL_TIMEOUT, autocommit=True)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            ok = cur.fetchone() is not None
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return bool(ok)
    except Exception as exc:
        log.warning("VPS SQL inalcanzable: %s", exc)
        return False


def _obtener_nodo_cod(db, nombre: str) -> int | None:
    """Busca o crea el nodo SCADA para asociar la alerta de daemon."""
    from app.models.model_scada import NodosSCADA

    nodo = (
        db.query(NodosSCADA)
        .filter(NodosSCADA.ndo_nom == nombre, NodosSCADA.fec_eli.is_(None))
        .first()
    )
    if nodo is not None:
        return nodo.ndo_cod
    nodo = NodosSCADA(
        ndo_nom=nombre[:100],
        ndo_ip="127.0.0.1",
        ndo_tipo="servidor",
        ndo_est="operativo",
        reg_usu="monitor",
    )
    db.add(nodo)
    db.flush()
    return nodo.ndo_cod


def _alerta_abierta(db, tipo: str, ndo_cod: int | None = None) -> int | None:
    alerta = (
        db.query(Alertas)
        .filter(
            Alertas.alt_tipo == tipo,
            Alertas.alt_ndo == ndo_cod,
            Alertas.alt_resu == False,  # noqa: E712 (SQL Server >= 0)
            Alertas.fec_eli.is_(None),
        )
        .first()
    )
    return alerta.alt_cod if alerta else None


def _abrir_alerta(db, tipo: str, sev: str, titulo: str, diag: str,
                  ndo_nombre: str | None = None) -> None:
    ndo_cod = _obtener_nodo_cod(db, ndo_nombre) if ndo_nombre else None
    if _alerta_abierta(db, tipo, ndo_cod) is not None:
        return

    alerta = Alertas(
        alt_ndo=ndo_cod,
        alt_tipo=tipo,
        alt_sev=sev,
        alt_titulo=titulo[:200],
        alt_diag=diag[:500],
        reg_usu="monitor",
    )
    db.add(alerta)
    db.flush()

    causa = CausasRaiz(
        cra_alt=alerta.alt_cod,
        cra_nivel="root",
        cra_etiq=titulo[:200],
        cra_tono="rojo",
        reg_usu="monitor",
    )
    db.add(causa)
    db.commit()
    log.warning("Alerta abierta [%s] %s", tipo, titulo)


def _resolver_alertas(db, tipo: str, ndo_nombre: str | None = None) -> None:
    ndo_cod = _obtener_nodo_cod(db, ndo_nombre) if ndo_nombre else None
    filtro_ndo = Alertas.alt_ndo == ndo_cod if ndo_cod is not None else Alertas.alt_ndo.is_(None)
    abiertas = (
        db.query(Alertas)
        .filter(
            Alertas.alt_tipo == tipo,
            filtro_ndo,
            Alertas.alt_resu == False,  # noqa: E712
            Alertas.fec_eli.is_(None),
        )
        .all()
    )
    for alerta in abiertas:
        alerta.alt_resu = True
        alerta.alt_fec_resu = datetime.utcnow()
    if abiertas:
        db.commit()
        log.info("Alertas resueltas [%s]: %d", tipo, len(abiertas))


def _monitorear() -> dict:
    """Corre una pasada del monitor y devuelve el estado de los enlaces."""
    desde = time.time()

    # 1) VPS SQL (fuente de logs/metricas).
    vps_ok = _test_vps_sql()

    # 2) Daemon -> web (heartbeat por nodo).
    estados = buffer_telemetria.estados()
    nodos = {}
    for nodo, info in estados.items():
        nodos[nodo] = {
            "estado": info["estado"],
            "hace_seg": info.get("hace_seg"),
        }
    daemon_ok = bool(nodos)

    db = SessionLocal()
    try:
        if not vps_ok:
            _abrir_alerta(
                db,
                _TIPO_VPS,
                "critica",
                "Sin conexion al SQL Server de negocio (VPS)",
                "No se puede leer logs/metricas del SQL Server en "
                "{}:{}. Sincronizacion detenida.".format(
                    os.getenv("SQL_HOST", "127.0.0.1"),
                    os.getenv("SQL_PORT", "1434"),
                ),
            )
        else:
            _resolver_alertas(db, _TIPO_VPS)

        for nodo, info in nodos.items():
            if info["estado"] == "offline":
                _abrir_alerta(
                    db,
                    _TIPO_DAEMON,
                    "alta",
                    f"Telemetria detenida del nodo {nodo}",
                    f"El collector/daemon de {nodo} no envia muestras hace "
                    f"{info.get('hace_seg', '?')}s (margen {SINC_TIMEOUT}s).",
                    ndo_nombre=nodo,
                )
            else:
                _resolver_alertas(db, _TIPO_DAEMON, nodo)
    finally:
        db.close()

    return {
        "revisado": time.time() - desde,
        "sql_vps": {
            "conectado": vps_ok,
            "detalle": "ok" if vps_ok else "offline",
        },
        "daemon": {
            "conectado": daemon_ok,
            "nodos": nodos,
            "detalle": "ok" if daemon_ok else "sin_datos",
        },
    }


def monitor_loop() -> None:
    """Bucle del hilo: revisa los enlaces cada ``SINC_INTERVAL`` segundos."""
    log.info("Monitor de sincronizacion iniciado (cada %ss)", SINC_INTERVAL)
    while not _stop.is_set():
        try:
            resultado = _monitorear()
            with _lock:
                estado_actual.clear()
                estado_actual.update(resultado)
        except Exception:
            log.exception("Fallo la pasada del monitor de sincronizacion")
        _stop.wait(SINC_INTERVAL)
    log.info("Monitor de sincronizacion detenido")


def start_monitor() -> None:
    """Arranca el hilo del monitor (idempotente)."""
    global _thread
    _stop.clear()
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(
            target=monitor_loop,
            daemon=True,
            name="sincronizacion-monitor",
        )
        _thread.start()


def stop_monitor() -> None:
    """Detiene el hilo del monitor."""
    _stop.set()


def estado() -> dict:
    """Devuelve el ultimo estado del monitor (para el endpoint)."""
    with _lock:
        if not estado_actual:
            return {
                "sql_vps": {"conectado": None, "detalle": "sin_verificar"},
                "daemon": {"conectado": None, "nodos": {}, "detalle": "sin_verificar"},
            }
        return dict(estado_actual)