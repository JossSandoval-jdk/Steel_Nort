"""
stream.py
=========
Daemon de colección continua hacia la API web SteelNort (API v2).

Recolecta métricas del sistema, DMV de SQL Server, Extended Events y
error log, construye la muestra y la publica en POST
/api/v2/telemetria/push. Ante caídas de la API escribe a un spool local
(JSONL) y lo reenvía en el próximo ciclo.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

import pyodbc
import requests
from dotenv import load_dotenv

# .env del proyecto (backend/). Este archivo vive en app/tools/collector/,
# así que se suben 4 niveles: collector -> tools -> app -> backend.
_RAIZ = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, _RAIZ)
load_dotenv(os.path.join(_RAIZ, ".env"))

from app.tools.collector.config import (                 # noqa: E402
    LOGS_DIR, SPOOL_DIR, SQL_DATABASE, SQL_HOST, SQL_PORT,
    SQL_SERVER_CONN_STR, STREAM_API_URL, STREAM_INTERNAL_TOKEN,
    STREAM_INTERVAL, STREAM_NDO_IP, STREAM_NDO_NOM, STREAM_PASSWORD,
    STREAM_USER,
)
from app.tools.collector import eventos, metrics         # noqa: E402


# ==========================================
# Logging
# ==========================================
os.makedirs(LOGS_DIR, exist_ok=True)
_log = logging.getLogger("stream_daemon")
_log.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
_fh = RotatingFileHandler(
    os.path.join(LOGS_DIR, "daemon.log"),
    maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
)
_fh.setFormatter(_fmt)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)
_log.addHandler(_fh)
_log.addHandler(_sh)

_stop = threading.Event()


# ==========================================
# SQL
# ==========================================
def _open_sql():
    try:
        conn = pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        _log.info("SQL Server OK (%s,%s/%s)", SQL_HOST, SQL_PORT, SQL_DATABASE)
        return conn
    except Exception as exc:
        _log.error("SQL Server fallido: %s", exc)
        return None


# ==========================================
# Auth y spool
# ==========================================
_token_store = {"token": None}
_token_lock = threading.Lock()


def _login():
    try:
        r = requests.post(
            f"{STREAM_API_URL.rstrip('/')}/auth/login",
            json={"usuario": STREAM_USER, "clave": STREAM_PASSWORD},
            timeout=10,
        )
        r.raise_for_status()
        _log.info("Login OK")
        return r.json().get("access_token")
    except Exception as exc:
        _log.error("Login fallido: %s", exc)
        return None


def _spool_put(muestra, eventos_list, logs_list):
    """Guarda la muestra en spool cuando la API está caída."""
    try:
        os.makedirs(SPOOL_DIR, exist_ok=True)
        with open(os.path.join(SPOOL_DIR, "daemon-spool.jsonl"),
                  "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"muestra": muestra, "eventos": eventos_list, "logs": logs_list},
                default=str,
            ) + "\n")
        _log.warning("Muestra en spool (API caída)")
    except Exception as exc:
        _log.error("No se pudo escribir spool: %s", exc)


def _spool_replay():
    """Reenvía las muestras acumuladas cuando la API vuelve."""
    path = os.path.join(SPOOL_DIR, "daemon-spool.jsonl")
    if not os.path.exists(path):
        return
    enviadas = 0
    try:
        with open(path, encoding="utf-8") as f:
            lineas = f.readlines()
        os.replace(path, path + ".old")
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
            try:
                reg = json.loads(linea)
            except Exception:
                continue
            if "muestra" not in reg:            # formato viejo
                reg = {"muestra": reg, "eventos": [], "logs": []}
            if _publicar(reg["muestra"], reg.get("eventos") or [],
                         reg.get("logs") or []):
                enviadas += 1
            else:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(linea + "\n")
                break
        if os.path.exists(path + ".old"):
            os.remove(path + ".old")
        if enviadas:
            _log.info("Spool reenviado: %d muestras", enviadas)
    except Exception as exc:
        _log.error("Replay spool fallido: %s", exc)


# ==========================================
# Publicación
# ==========================================
def _cabeceras(token):
    """Cabeceras del POST interno: JWT del collector y el token compartido.

    ``X-Internal-Token`` es obligatorio para ``/telemetria/push``; el JWT (si
    hay sesion) se mantiene porque la ruta tambien acepta usuario autenticado.
    """
    cabeceras = {}
    if STREAM_INTERNAL_TOKEN:
        cabeceras["X-Internal-Token"] = STREAM_INTERNAL_TOKEN
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    return cabeceras


def _publicar(muestra, eventos_list, logs_list):
    """POST a /telemetria/push. Devuelve True si la API lo aceptó."""
    with _token_lock:
        token = _token_store["token"]
    headers = _cabeceras(token)

    payload = {
        "nodo": STREAM_NDO_NOM, "ip": STREAM_NDO_IP,
        "muestra": muestra, "eventos": eventos_list, "logs": logs_list,
    }

    try:
        r = requests.post(
            f"{STREAM_API_URL.rstrip('/')}/telemetria/push",
            json=payload, headers=headers, timeout=10,
        )
        if r.status_code == 401:
            _log.info("Token expirado; re-login")
            with _token_lock:
                _token_store["token"] = _login()
            token = _token_store["token"]
            if token:
                r = requests.post(
                    f"{STREAM_API_URL.rstrip('/')}/telemetria/push",
                    json=payload,
                    headers=_cabeceras(token),
                    timeout=10,
                )
        return r.status_code < 400
    except Exception as exc:
        _log.warning("POST telemetría fallido: %s", exc)
        return False


# ==========================================
# Lectura de errorlog
# ==========================================
def _leer_errorlog(conn, estado):
    """Lee las entradas nuevas del errorlog desde el ciclo anterior."""
    if not conn:
        return []

    ahora = datetime.now()
    desde = estado.get("log_ultima_fecha",
                       ahora - timedelta(seconds=STREAM_INTERVAL))
    vistos = estado.setdefault("log_vistos", set())
    logs = []

    try:
        cur = conn.cursor()
        cur.execute("EXEC sp_readerrorlog 0")
        for fecha, proceso, texto in cur.fetchall():
            if not fecha or not texto or fecha < desde:
                continue

            proceso = str(proceso or "").strip()
            texto = " ".join(str(texto).split())
            clave = (str(fecha), proceso, texto)
            if clave in vistos:
                continue
            vistos.add(clave)

            bajo = texto.lower()
            if any(p in bajo for p in ("error", "failed", "deadlock", "severity")):
                nivel = "ERROR"
            elif "warning" in bajo:
                nivel = "WARNING"
            else:
                nivel = "INFO"

            logs.append({
                "timestamp": fecha.isoformat(sep=" "),
                "nivel": nivel,
                "mensaje": f"{proceso}: {texto}".strip(": "),
            })
    except Exception as exc:
        _log.warning("Errorlog: %s", exc)

    estado["log_ultima_fecha"] = ahora
    if len(vistos) > 2000:
        vistos.clear()
    return logs


# ==========================================
# Construcción de muestra
# ==========================================
def _construir_muestra(conn, estado):
    """Devuelve (muestra, eventos, logs)."""
    # SO
    sys_metrics, nuevo_estado = metrics.get_system_metrics(
        estado["prev_disk_r"], estado["prev_disk_w"],
        estado["prev_net_s"], estado["prev_net_r"], estado["prev_time"],
    )
    (estado["prev_time"], estado["prev_disk_r"], estado["prev_disk_w"],
     estado["prev_net_s"], estado["prev_net_r"]) = nuevo_estado

    muestra = {}
    for name, val in sys_metrics:
        try:
            muestra[name] = float(val)
        except Exception:
            muestra[name] = 0.0

    # SQL Server
    ss_now = time.time()
    dt_ss = (ss_now - estado["sql_prev_time"]) if estado["sql_prev_time"] else 0.0
    estado["sql_prev_time"] = ss_now

    if conn:
        try:
            ss_metrics, nuevos = metrics.get_sql_server_metrics(
                conn, estado["prev_counters"], dt_ss)
            estado["prev_counters"] = nuevos
            for name, val in ss_metrics:
                try:
                    muestra[name] = float(val if val is not None else 0.0)
                except Exception:
                    muestra[name] = 0.0
        except Exception as exc:
            _log.warning("SQL metrics: %s", exc)

        for name, val in metrics.get_business_locks(conn):
            try:
                muestra[name] = float(val or 0)
            except Exception:
                muestra[name] = 0.0
    else:
        # Sin conexión: rellenar con 0 las variables del modelo
        for name in ("total_reads", "total_writes", "active_sessions",
                     "active_requests", "long_queries", "long_transactions",
                     "lock_waits", "total_locks", "deadlocks_per_sec",
                     "transactions_per_sec", "page_life_expectancy"):
            muestra[name] = 0.0

    # API de negocio (cache del probe en hilo)
    for name, val in metrics.get_api_metrics():
        try:
            muestra[name] = float(val)
        except Exception:
            muestra[name] = 0.0

    # Extended Events
    eventos_list = []
    if conn:
        try:
            rows = eventos.read_xe_events(conn, estado["xe_last_ts"])
            for row in rows:
                ev = eventos.map_xe_event(row)
                eventos_list.append(ev)
                if row[1] and row[1] > estado["xe_last_ts"]:
                    estado["xe_last_ts"] = row[1]

            # Agregados que consume el modelo ML
            batches = [e for e in eventos_list
                       if e.get("event_name") in ("xe.sql_batch_completed",
                                                  "xe.rpc_completed")]
            durations = [b.get("duration", 0) for b in batches]
            muestra["batch_count"] = float(len(batches))
            muestra["batch_duration_avg_ms"] = (
                float(sum(durations) / len(durations) / 1000) if durations else 0.0)
            muestra["batch_duration_max_ms"] = (
                float(max(durations) / 1000) if durations else 0.0)
            muestra["events_wait_count"] = float(
                sum(1 for e in eventos_list
                    if e.get("event_name") == "xe.error_reported"))
        except Exception as exc:
            _log.warning("Error leyendo XE: %s", exc)

    # Errorlog
    logs = _leer_errorlog(conn, estado)

    # Marca temporal
    ahora_utc = datetime.now(timezone.utc)
    muestra["ts"] = ahora_utc.timestamp()
    muestra["fecha_str"] = ahora_utc.isoformat()

    return muestra, eventos_list, logs


# ==========================================
# Loop principal
# ==========================================
def run():
    _log.info("Stream daemon: API=%s nodo=%s intervalo=%ss",
              STREAM_API_URL, STREAM_NDO_NOM, STREAM_INTERVAL)

    with _token_lock:
        _token_store["token"] = _login()

    conn = _open_sql()

    # Probe de la API de negocio en hilo (latencia/estado para el modelo)
    threading.Thread(
        target=metrics._api_probe_loop, args=(None,),
        daemon=True, name="api-probe",
    ).start()

    estado = {
        "prev_disk_r": 0, "prev_disk_w": 0,
        "prev_net_s": 0, "prev_net_r": 0, "prev_time": time.time(),
        "prev_counters": {}, "sql_prev_time": None,
        "log_ultima_fecha": datetime.now() - timedelta(seconds=STREAM_INTERVAL),
        "log_vistos": set(),
        "xe_last_ts": datetime(2000, 1, 1),
    }

    # Contadores base para que las tasas de la primera muestra sean reales
    try:
        import psutil
        io = psutil.disk_io_counters()
        net = psutil.net_io_counters()
        if io:
            estado["prev_disk_r"] = io.read_bytes
            estado["prev_disk_w"] = io.write_bytes
        if net:
            estado["prev_net_s"] = net.bytes_sent
            estado["prev_net_r"] = net.bytes_recv
    except Exception:
        pass

    # Setup XE al arranque
    if conn:
        eventos.setup_xe()

    while not _stop.is_set():
        try:
            _spool_replay()
        except Exception:
            pass

        muestra, eventos_list, logs = _construir_muestra(conn, estado)
        if not _publicar(muestra, eventos_list, logs):
            _spool_put(muestra, eventos_list, logs)
            if conn is None:
                conn = _open_sql()

        _stop.wait(STREAM_INTERVAL)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        _stop.set()
        _log.info("Daemon detenido por el usuario")