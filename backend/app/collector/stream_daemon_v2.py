"""Daemon de coleccion continua hacia la API web SteelNort.

Recolecta métricas del sistema, contadores DMV de SQL Server y Extended Events,
construye la muestra y la publica de forma continua hacia la API web de la v2.
"""

from __future__ import annotations

import logging
import os
import sys
import time
import threading
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv(os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".env",
))

import requests
import pyodbc

from app.collector.config import (
    SQL_SERVER_CONN_STR,
    SQL_HOST,
    SQL_PORT,
    SQL_DATABASE,
    LOGS_DIR,
    SPOOL_DIR,
    STREAM_API_URL,
    STREAM_INTERVAL,
    STREAM_NDO_IP,
    STREAM_NDO_NOM,
    STREAM_PASSWORD,
    STREAM_USER,
)
from app.collector import metrics_collector
from app.collector import xe_collector

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
# Helpers SQL y XE
# ---------------------------------------------------------------------

def _open_sql() -> pyodbc.Connection | None:
    try:
        conn = pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        _logger.info("Conexion SQL Server OK (%s,%s/%s)", SQL_HOST, SQL_PORT, SQL_DATABASE)
        return conn
    except Exception as exc:
        _logger.error("Conexion SQL Server fallida: %s", exc)
        return None

def _count_wait_types(conn) -> dict:
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

# ---------------------------------------------------------------------
# Autenticacion y Spool
# ---------------------------------------------------------------------
def _login() -> str | None:
    try:
        resp = requests.post(
            f"{STREAM_API_URL.rstrip('/')}/auth/login",
            json={"usuario": STREAM_USER, "clave": STREAM_PASSWORD},
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        _logger.info("Login a la web OK")
        return token
    except Exception as exc:
        _logger.error("Login a la web fallido: %s", exc)
        return None

def _spool_puts(muestra: dict) -> None:
    import json as _json
    try:
        os.makedirs(SPOOL_DIR, exist_ok=True)
        with open(os.path.join(SPOOL_DIR, "daemon-spool.jsonl"), "a", encoding="utf-8") as f:
            f.write(_json.dumps(muestra, default=str) + "\n")
        _logger.warning("Muestra almacenada en spool temporal (backend caido)")
    except Exception as exc:
        _logger.error("No se pudo escribir spool: %s", exc)

# ---------------------------------------------------------------------
# Construccion de Muestra y Publicacion
# ---------------------------------------------------------------------

_token_store = {"token": None}
_token_lock = threading.Lock()

def _publicar_payload(muestra: dict, eventos: list, logs: list) -> bool:
    with _token_lock:
        token = _token_store["token"]
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = requests.post(
            f"{STREAM_API_URL.rstrip('/')}/telemetria/push",
            json={"nodo": STREAM_NDO_NOM, "ip": STREAM_NDO_IP, "muestra": muestra, "eventos": eventos, "logs": logs},
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
                    f"{STREAM_API_URL.rstrip('/')}/telemetria/push",
                    json={"nodo": STREAM_NDO_NOM, "ip": STREAM_NDO_IP, "muestra": muestra, "eventos": eventos, "logs": logs},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
        return resp.status_code < 400
    except Exception as exc:
        _logger.warning("POST telemetria fallido: %s", exc)
        return False

def _leer_logs_sql(conn, estado) -> list[dict]:
    """Lee las entradas nuevas del error log desde el ultimo ciclo."""
    if not conn:
        return []

    ahora = datetime.now()
    desde = estado.get("sql_log_ultima_fecha", ahora - timedelta(seconds=STREAM_INTERVAL))
    vistos = estado.setdefault("sql_logs_vistos", set())
    logs = []

    try:
        cursor = conn.cursor()
        cursor.execute("EXEC sp_readerrorlog 0")
        for fecha, proceso, texto in cursor.fetchall():
            if not fecha or not texto or fecha < desde:
                continue

            proceso = str(proceso or "").strip()
            texto = " ".join(str(texto).split())
            clave = (str(fecha), proceso, texto)
            if clave in vistos:
                continue
            vistos.add(clave)

            texto_min = texto.lower()
            if any(palabra in texto_min for palabra in ("error", "failed", "deadlock", "severity")):
                nivel = "ERROR"
            elif "warning" in texto_min:
                nivel = "WARNING"
            else:
                nivel = "INFO"

            logs.append({
                "timestamp": fecha.isoformat(sep=" "),
                "nivel": nivel,
                "mensaje": f"{proceso}: {texto}".strip(": "),
            })
    except Exception as exc:
        _logger.warning("SQL error log: %s", exc)

    estado["sql_log_ultima_fecha"] = ahora
    if len(vistos) > 2000:
        vistos.clear()
    return logs


def _construir_muestra(conn, estado) -> tuple[dict, list, list]:
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

    eventos = []
    if conn and "xe_last_ts" in estado:
        try:
            from app.collector import xe_collector
            rows = xe_collector.read_xe_events(conn, estado["xe_last_ts"])
            for row in rows:
                ev = xe_collector.map_xe_event(row)
                eventos.append(ev)
                if row[1] and row[1] > estado["xe_last_ts"]:
                    estado["xe_last_ts"] = row[1]
            
            # Compute aggregations for ML
            batches = [e for e in eventos if e.get("event_name") in ("xe.sql_batch_completed", "xe.rpc_completed")]
            durations = [b.get("duration", 0) for b in batches]
            muestra["batch_count"] = float(len(batches))
            muestra["batch_duration_avg_ms"] = float(sum(durations) / len(durations) / 1000) if durations else 0.0
            muestra["batch_duration_max_ms"] = float(max(durations) / 1000) if durations else 0.0
            muestra["events_wait_count"] = float(sum(1 for e in eventos if e.get("event_name") == "xe.error_reported"))
        except Exception as exc:
            _logger.warning("Error leyendo XE: %s", exc)

    logs = _leer_logs_sql(conn, estado)

    ahora_utc = datetime.now(timezone.utc)
    muestra["ts"] = ahora_utc.timestamp()
    muestra["fecha_str"] = ahora_utc.isoformat()
    return muestra, eventos, logs

def run() -> None:
    _logger.info(
        "Daemon stream iniciado: API=%s nodo=%s intervalo=%ss",
        STREAM_API_URL, STREAM_NDO_NOM, STREAM_INTERVAL,
    )

    with _token_lock:
        _token_store["token"] = _login()

    conn = _open_sql()
    from datetime import datetime
    estado = {
        "prev_disk_read": 0, "prev_disk_write": 0,
        "prev_net_sent": 0, "prev_net_recv": 0, "prev_time": time.time(),
        "prev_counters": {}, "sql_prev_time": None,
        "sql_log_ultima_fecha": datetime.now() - timedelta(seconds=STREAM_INTERVAL),
        "sql_logs_vistos": set(),
        "xe_last_ts": datetime(2000, 1, 1),
    }
    
    # Setup XE at startup
    if conn:
        from app.collector import xe_collector
        xe_collector.setup_xe()


    while not _stop.is_set():
        muestra, eventos, logs = _construir_muestra(conn, estado)
        ok = _publicar_payload(muestra, eventos, logs)
        if not ok:
            _spool_puts(muestra)
            if conn is None:
                conn = _open_sql()

        _stop.wait(STREAM_INTERVAL)

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        _stop.set()
        _logger.info("Daemon detenido por el usuario.")