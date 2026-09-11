"""Daemon de coleccion continua hacia la API web SteelNort.

Reutiliza la logica de extraccion de ``workload-collector`` (metrics
de sistema, contadores SQL Server DMV, bloqueos de negocio, Extended
Events y latencia de la API de negocio) pero en bucle infinito en lugar
de una corrida batch: cada ``STREAM_INTERVAL`` segundos arma UNA muestra
con las 22 variables del modelo entrenado y la publica en
``POST /telemetria/muestras``.

Diseno:
  - No guarda CSVs: la muestra vive solo en el ring buffer de la web.
  - JWT con login y auto-refresh (el token expira a los 120 min).
  - Si la API web falla, hace spool local (JSONL) y reintenta con backoff
    al recuperar la conexion (no se pierde la sensibilidad de alerta).
  - Los 6 features derivados de Extended Events (query_count,
    duration_avg_ms, cpu_time_sum_ms, wait_lck_count, wait_io_count,
    wait_log_count) se agregan por ventana; si XE no esta disponible se
    degradan de forma controlada a 0 / conteo de esperas puntual.

Uso:
    python -m app.collector.stream_daemon
"""

from __future__ import annotations

import logging
import os
import sys
import time
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

# Cargar entorno ANTES de importar la configuracion del collector.
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv(os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".env",
))

import requests  # noqa: E402

from app.collector.config import (  # noqa: E402
    SQL_SERVER_CONN_STR,
    SQL_HOST,
    SQL_PORT,
    SQL_DATABASE,
    LOG_TAIL_INTERVAL,
    LOGS_DIR,
    SPOOL_DIR,
    STREAM_API_URL,
    STREAM_INTERVAL,
    STREAM_NDO_IP,
    STREAM_NDO_NOM,
    STREAM_PASSWORD,
    STREAM_USER,
    XE_FILE_PATH,
)
from app.collector import metrics_collector  # noqa: E402
from app.collector import xe_collector  # noqa: E402

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
LOG_DIR = LOGS_DIR
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

_logger = logging.getLogger("stream_daemon")
_logger.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
_handler_f = RotatingFileHandler(
    os.path.join(LOG_DIR, "daemon.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_handler_f.setFormatter(_fmt)
_handler_s = logging.StreamHandler(sys.stdout)
_handler_s.setFormatter(_fmt)
_logger.addHandler(_handler_f)
_logger.addHandler(_handler_s)

_stop = threading.Event()

# ---------------------------------------------------------------------
# Helpers SQL
# ---------------------------------------------------------------------


def _open_sql() -> "pyodbc.Connection | None":
    import pyodbc  # noqa: PLC0415 (import tardio para arranque liviano)

    try:
        conn = pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        _logger.info("Conexion SQL Server OK (%s,%s/%s)", SQL_HOST, SQL_PORT, SQL_DATABASE)
        return conn
    except Exception as exc:
        _logger.error("Conexion SQL Server fallida: %s", exc)
        return None


def _count_wait_types(conn) -> dict:
    """Muestreo puntual de sys.dm_os_waiting_tasks por categoria.

    Approximacion de ventana para los wait_* ya que el XE definido no
    captura wait_info; la ventana queda empirica (3 intervalos).
    """
    out = {"wait_lck_count": 0, "wait_io_count": 0, "wait_log_count": 0}
    try:
        c = conn.cursor()
        c.execute(
            "SELECT wait_type, COUNT(*) FROM sys.dm_os_waiting_tasks "
            "WHERE wait_type IS NOT NULL GROUP BY wait_type"
        )
        for wt, n in c.fetchall():
            wt = (wt or "").upper()
            if wt.startswith("LCK_"):
                out["wait_lck_count"] += n
            elif wt.startswith(("PAGEIOLATCH_", "PAGELATCH_")):
                out["wait_io_count"] += n
            elif wt == "WRITELOG":
                out["wait_log_count"] += n
    except Exception as exc:
        _logger.warning("wait_types: %s", exc)
    return out


_xe_unavailable = False


def _xe_agg(conn, desde: datetime, hasta: datetime) -> dict:
    """Agrega los eventos sql_batch_completed/rpc_completed del XE.

    Los archivos .xel activos hacen que fn_xe_file_target_read_file se
    quede bloqueado (o interrogue la conexion con timeout dejandola en
    estado irrecuperable), por eso el XE se lee en una conexion EFIMERA
    con timeout corto. Si falla una vez, se marca como no disponible y se
    degrada permanentemente a ``query_count`` = requests activos, sin
    volver a tocar el XE ni la conexion principal del daemon.
    """
    global _xe_unavailable
    aggs = {"query_count": 0, "duration_avg_ms": 0.0,
            "cpu_time_sum_ms": 0.0, "duration_max_ms": 0.0}
    if not conn:
        return aggs

    def _degradar():
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM sys.dm_exec_requests WHERE session_id > 50")
            aggs["query_count"] = int(c.fetchval() or 0)
        except Exception:
            pass
        return aggs

    if os.getenv("XE_ENABLED", "1") != "1" or _xe_unavailable:
        return _degradar()

    import pyodbc  # noqa: PLC0415
    rows = []
    xconn = None
    try:
        xconn = pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        xconn.timeout = 10
        rows = xe_collector.read_xe_events(xconn, desde)
    except Exception as exc:
        _logger.warning("XE no disponible, degradando query_count: %s", exc)
        _xe_unavailable = True
        return _degradar()
    finally:
        if xconn is not None:
            try:
                xconn.close()
            except Exception:
                pass

    counts = 0
    suma = 0.0
    cpu = 0.0
    max_dur = 0.0
    for row in rows:
        if row[0] not in ("sql_batch_completed", "rpc_completed"):
            continue
        ts = row[1]
        if ts and hasta:
            # row[1] viene naive de SQL Server; normalizar a naive.
            hasta_naive = hasta.replace(tzinfo=None) if hasta.tzinfo else hasta
            if ts > hasta_naive:
                break
        counts += 1
        dur_us = float(row[2] or 0)
        suma += dur_us
        max_dur = max(max_dur, dur_us)
        cpu += float(row[3] or 0)

    aggs["query_count"] = counts
    aggs["duration_avg_ms"] = round(suma / counts / 1000.0, 2) if counts else 0.0
    aggs["cpu_time_sum_ms"] = round(cpu / 1000.0, 2) if cpu else 0.0
    aggs["duration_max_ms"] = round(max_dur / 1000.0, 2) if counts else 0.0
    return aggs


# ---------------------------------------------------------------------
# Autenticacion contra la API web
# ---------------------------------------------------------------------


def _login() -> str | None:
    try:
        resp = requests.post(
            f"{STREAM_API_URL.rstrip('/')}/auth/login",
            json={"email": STREAM_USER, "password": STREAM_PASSWORD},
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        _logger.info("Login a la web OK")
        return token
    except Exception as exc:
        _logger.error("Login a la web fallido: %s", exc)
        return None


# ---------------------------------------------------------------------
# Spool (colchon ante caidas del backend)
# ---------------------------------------------------------------------


def _spool_puts(muestra: dict) -> None:
    import json as _json

    try:
        os.makedirs(SPOOL_DIR, exist_ok=True)
        with open(os.path.join(SPOOL_DIR, "daemon-spool.jsonl"), "a",
                  encoding="utf-8") as f:
            f.write(_json.dumps(muestra, default=str) + "\n")
        _logger.warning("Muestra espeleada en spool (backend caido)")
    except Exception as exc:
        _logger.error("No se pudo escribir spool: %s", exc)


def _replay_spool() -> None:
    import json as _json

    path = os.path.join(SPOOL_DIR, "daemon-spool.jsonl")
    if not os.path.exists(path):
        return
    sent = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            lineas = f.readlines()
        os.replace(path, path + ".old")
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
            try:
                m = _json.loads(linea)
            except Exception:
                continue
            if _publicar_payload(m) :
                sent += 1
            else:
                # regresar el resto al spool
                with open(path, "a", encoding="utf-8") as f:
                    f.write(linea + "\n")
                break
        os.remove(path + ".old")
        if sent:
            _logger.info("Spool reenviado: %d muestras", sent)
    except Exception as exc:
        _logger.error("Replay spool fallido: %s", exc)


# ---------------------------------------------------------------------
# Publicacion
# ---------------------------------------------------------------------

_token_store = {"token": None}
_token_lock = threading.Lock()


def _publicar_payload(muestra: dict) -> bool:
    with _token_lock:
        token = _token_store["token"]
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = requests.post(
            f"{STREAM_API_URL.rstrip('/')}/telemetria/muestras",
            json={"nodo": STREAM_NDO_NOM, "ip": STREAM_NDO_IP, "muestra": muestra},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 401:
            _logger.info("Token expirado; re-login...")
            with _token_lock:
                _token_store["token"] = _login()
            token = _token_store["token"]
            if token:
                resp = requests.post(
                    f"{STREAM_API_URL.rstrip('/')}/telemetria/muestras",
                    json={"nodo": STREAM_NDO_NOM, "ip": STREAM_NDO_IP, "muestra": muestra},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
        return resp.status_code < 400
    except Exception as exc:
        _logger.warning("POST telemetria fallido: %s", exc)
        return False


def _construir_muestra(conn, estado) -> dict:
    """Arma el dict de 22 variables + metadatos de una muestra."""
    # --- sistema ---
    res = metrics_collector.get_system_metrics(
        estado["prev_disk_read"], estado["prev_disk_write"],
        estado["prev_net_sent"], estado["prev_net_recv"], estado["prev_time"],
    )
    sys_metrics = res[0]
    (estado["prev_time"], estado["prev_disk_read"],
     estado["prev_disk_write"], estado["prev_net_sent"],
     estado["prev_net_recv"]) = res[1:]

    muestra: dict = {}
    for name, val in sys_metrics:
        try:
            muestra[name] = float(val)
        except Exception:
            muestra[name] = 0.0

    # --- SQL Server (DMV) ---
    ss_now = time.time()
    dt_ss = (ss_now - estado["sql_prev_time"]) if estado["sql_prev_time"] else 0.0
    estado["sql_prev_time"] = ss_now
    if conn:
        try:
            ss_metrics, nuevos = metrics_collector.get_sql_server_metrics(
                conn, prev_counters=estado["prev_counters"], dt=dt_ss
            )
            estado["prev_counters"] = nuevos
            for name, val in ss_metrics:
                if val is None:
                    val = 0.0
                try:
                    muestra[name] = float(val)
                except Exception:
                    muestra[name] = 0.0
        except Exception as exc:
            _logger.warning("SQL metrics: %s", exc)
        try:
            for name, val in metrics_collector.get_business_locks(conn):
                try:
                    muestra[name] = float(val or 0)
                except Exception:
                    muestra[name] = 0.0
        except Exception as exc:
            _logger.warning("Business locks: %s", exc)
        try:
            muestra.update(_count_wait_types(conn))
        except Exception:
            pass
        try:
            muestra.update(_xe_agg(conn, estado["xe_desde"], datetime.now(timezone.utc)))
        except Exception:
            pass
    else:
        for name in ("total_reads", "total_writes", "active_sessions",
                     "active_requests", "lock_waits", "total_locks",
                     "transactions_per_sec", "page_life_expectancy"):
            muestra[name] = 0.0

    # --- latencia API de negocio (cache del probe en hilo) ---
    for name, val in metrics_collector.get_api_metrics(estado["api_token"]):
        try:
            muestra[name] = float(val)
        except Exception:
            muestra[name] = 0.0

    # contadores que deben existir siempre
    for k in ("duration_max_ms",):
        muestra.setdefault(k, 0.0)

    ahora_utc = datetime.now(timezone.utc)
    muestra["ts"] = ahora_utc.timestamp()
    muestra["fecha_str"] = ahora_utc.isoformat()
    return muestra


# ---------------------------------------------------------------------
# Bucle principal
# ---------------------------------------------------------------------


def run() -> None:
    _logger.info(
        "Daemon stream iniciado: API=%s nodo=%s intervalo=%ss",
        STREAM_API_URL, STREAM_NDO_NOM, STREAM_INTERVAL,
    )

    with _token_lock:
        _token_store["token"] = _login()

    conn = _open_sql()
    # hilo de probe de la API de negocio (reutilizando metrics_collector)
    probe = threading.Thread(
        target=metrics_collector._api_probe_loop,
        args=(None,),
        daemon=True,
        name="api-probe",
    )
    probe.start()

    estado = {
        "prev_disk_read": 0, "prev_disk_write": 0,
        "prev_net_sent": 0, "prev_net_recv": 0, "prev_time": time.time(),
        "prev_counters": {}, "sql_prev_time": None,
        "xe_desde": datetime.now(timezone.utc),
        "api_token": None,
    }
    # Contadores base para tasas correctas desde la primera muestra.
    try:
        import psutil  # noqa: PLC0415
        _io = psutil.disk_io_counters()
        _net = psutil.net_io_counters()
        if _io:
            estado["prev_disk_read"] = _io.read_bytes
            estado["prev_disk_write"] = _io.write_bytes
        estado["prev_net_sent"] = _net.bytes_sent
        estado["prev_net_recv"] = _net.bytes_recv
    except Exception:
        pass

    while not _stop.is_set():
        try:
            _replay_spool()
        except Exception:
            pass

        muestra = _construir_muestra(conn, estado)

        ok = _publicar_payload(muestra)
        if not ok:
            _spool_puts(muestra)
            # reconectar SQL por si la instancia de negocio reinicio
            if conn is None:
                conn = _open_sql()

        _stop.wait(STREAM_INTERVAL)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        _stop.set()
        _logger.info("Daemon detenido por el usuario.")