"""
eventos.py
==========
Captura eventos de SQL Server:

  1. tail_errorlog()   → sp_readerrorlog cada N segundos → sqlserver_logs.log
  2. setup_xe()        → crea la sesión SteelNortMonitor
  3. collect_xe_loop() → lee .xel incremental → events_xe.log

Las funciones de lectura puntual (read_xe_events, map_xe_event) las usa
también el stream daemon para enviar eventos a la API v2.
"""

import json
import os
import re
import threading
import time
from datetime import datetime

import pyodbc

from app.tools.collector.config import (
    LOG_TAIL_INTERVAL, OUTPUT_DIR, SQL_SERVER_CONN_STR,
)


def log(msg):
    print(f"[EVENTOS] {msg}", flush=True)


_stop_event = threading.Event()


# ==========================================
# Conexión
# ==========================================
def _get_conn():
    """Reintenta la conexión a SQL Server."""
    for _ in range(10):
        try:
            return pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        except Exception:
            _stop_event.wait(2)
    return None


# ==========================================
# Error log
# ==========================================
def tail_errorlog():
    """Lee sp_readerrorlog cada LOG_TAIL_INTERVAL y escribe sqlserver_logs.log."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, "sqlserver_logs.log")

    conn = _get_conn()
    if not conn:
        log("Sin conexión para errorlog")
        return

    vistos = set()
    count = 0
    log(f"Leyendo errorlog cada {LOG_TAIL_INTERVAL}s")

    with open(filepath, "w", encoding="utf-8") as f:
        while not _stop_event.is_set():
            try:
                cursor = conn.cursor()
                cursor.execute("EXEC sp_readerrorlog 0")
                for row in cursor.fetchall():
                    fecha, proceso, texto = row[0], row[1], row[2]
                    if not texto:
                        continue

                    proceso = str(proceso or "").strip()
                    texto = " ".join(str(texto).split())
                    clave = (str(fecha), proceso, texto)
                    if clave in vistos:
                        continue
                    vistos.add(clave)

                    # Formato: "YYYY-MM-DD HH:MM:SS.mmm  proceso  mensaje"
                    if fecha and hasattr(fecha, "strftime"):
                        ts = fecha.strftime("%Y-%m-%d %H:%M:%S.") + \
                            f"{fecha.microsecond // 1000:03d}"
                    else:
                        ts = str(fecha)[:23] if fecha else \
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S.000")

                    f.write(f"{ts}  {proceso:<15s}{texto}\n")
                    f.flush()
                    count += 1
            except Exception as e:
                log(f"Error errorlog: {e}")
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _get_conn()

            _stop_event.wait(LOG_TAIL_INTERVAL)

    if conn:
        try:
            conn.close()
        except Exception:
            pass
    log(f"Errorlog: {count} líneas -> {filepath}")


# ==========================================
# Extended Events — setup
# ==========================================
def setup_xe():
    """Crea/recrea la sesión SteelNortMonitor con los eventos disponibles."""
    log("Configurando Extended Events...")
    conn = _get_conn()
    if not conn:
        log("ERROR: sin conexión para setup XE")
        return False

    try:
        cursor = conn.cursor()

        # Borrar sesión previa
        cursor.execute(
            "IF EXISTS (SELECT 1 FROM sys.server_event_sessions "
            "WHERE name = 'SteelNortMonitor') "
            "DROP EVENT SESSION [SteelNortMonitor] ON SERVER"
        )
        conn.commit()

        # Sesión base: sql_batch_completed con filtro de duración >= 500ms
        cursor.execute(
            "CREATE EVENT SESSION [SteelNortMonitor] ON SERVER "
            "ADD EVENT sqlserver.sql_batch_completed("
            "ACTION(sqlserver.sql_text, sqlserver.database_name, "
            "sqlserver.session_id, sqlserver.username, "
            "sqlserver.client_hostname, sqlserver.client_app_name) "
            "WHERE sqlserver.database_name = N'SteelNort' AND duration >= 500000"
            ") "
            "ADD TARGET package0.event_file("
            "SET filename = N'/var/opt/mssql/log/steel_events.xel', "
            "max_file_size = 100, max_rollover_files = 5"
            ") "
            "WITH (MAX_MEMORY = 4096 KB, STARTUP_STATE = ON)"
        )
        conn.commit()

        # Eventos opcionales (algunos no están disponibles en todas las ediciones)
        opcionales = [
            ("rpc_completed",
             "ADD EVENT sqlserver.rpc_completed("
             "ACTION(sqlserver.sql_text, sqlserver.database_name, "
             "sqlserver.session_id, sqlserver.username) "
             "WHERE sqlserver.database_name = N'SteelNort' AND duration >= 500000)"),
            ("error_reported",
             "ADD EVENT sqlserver.error_reported("
             "ACTION(sqlserver.sql_text, sqlserver.session_id, sqlserver.database_name) "
             "WHERE sqlserver.database_name = N'SteelNort')"),
            ("xml_deadlock_report", "ADD EVENT sqlserver.xml_deadlock_report"),
            ("locks_lock_waits",
             "ADD EVENT sqlserver.locks_lock_waits(ACTION(sqlserver.session_id))"),
            ("blocked_process_report", "ADD EVENT sqlserver.blocked_process_report"),
            ("login",
             "ADD EVENT sqlserver.login(ACTION(sqlserver.session_id, sqlserver.username, "
             "sqlserver.client_hostname, sqlserver.client_app_name))"),
            ("logout",
             "ADD EVENT sqlserver.logout(ACTION(sqlserver.session_id, sqlserver.username, "
             "sqlserver.client_hostname, sqlserver.client_app_name))"),
        ]
        activos = ["sql_batch_completed"]
        for nombre, ddl in opcionales:
            try:
                cursor.execute("ALTER EVENT SESSION [SteelNortMonitor] ON SERVER " + ddl)
                conn.commit()
                activos.append(nombre)
            except Exception as exc:
                log(f"Evento omitido ({nombre}): {exc}")

        # Arrancar si no está corriendo
        cursor.execute(
            "IF NOT EXISTS (SELECT 1 FROM sys.dm_xe_sessions "
            "WHERE name = 'SteelNortMonitor') "
            "ALTER EVENT SESSION [SteelNortMonitor] ON SERVER STATE = START"
        )
        conn.commit()
        log(f"Sesión activa con eventos: {', '.join(activos)}")

        conn.close()
        return True
    except Exception as e:
        log(f"Error setup XE: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return False


def is_xe_available(conn):
    """¿La sesión SteelNortMonitor está corriendo?"""
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM sys.dm_xe_sessions WHERE name = 'SteelNortMonitor'")
        return c.fetchone() is not None
    except Exception:
        return False


# ==========================================
# Extended Events — lectura
# ==========================================
def _ruta_xel(conn):
    """Ruta exacta del .xel activo (evita escanear archivos viejos)."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT CAST(s.target_data AS XML) "
            "FROM sys.dm_xe_session_targets s "
            "JOIN sys.dm_xe_sessions e ON e.address = s.event_session_address "
            "WHERE e.name = 'SteelNortMonitor' AND s.target_name = 'event_file'"
        )
        row = cur.fetchone()
        if not row:
            return None
        m = re.search(r'<File name="([^"]+\.xel)"', str(row[0]))
        return m.group(1) if m else None
    except Exception:
        return None


_SQL_LECTURA_XE = """
SELECT
    event_data.value('(event/@name)[1]', 'varchar(50)') AS event_name,
    event_data.value('(event/@timestamp)[1]', 'datetime2(3)') AS timestamp,
    event_data.value('(event/data[@name="duration"]/value)[1]', 'bigint') AS duration,
    event_data.value('(event/data[@name="cpu_time"]/value)[1]', 'bigint') AS cpu_time,
    event_data.value('(event/data[@name="logical_reads"]/value)[1]', 'bigint') AS logical_reads,
    event_data.value('(event/data[@name="writes"]/value)[1]', 'bigint') AS writes,
    event_data.value('(event/data[@name="row_count"]/value)[1]', 'bigint') AS row_count,
    event_data.value('(event/data[@name="batch_text"]/value)[1]', 'nvarchar(MAX)') AS sql_text,
    event_data.value('(event/data[@name="statement"]/value)[1]', 'nvarchar(MAX)') AS statement,
    event_data.value('(event/action[@name="database_name"]/value)[1]', 'nvarchar(128)') AS database_name,
    event_data.value('(event/action[@name="session_id"]/value)[1]', 'int') AS session_id,
    event_data.value('(event/action[@name="username"]/value)[1]', 'nvarchar(128)') AS username,
    event_data.value('(event/action[@name="client_hostname"]/value)[1]', 'nvarchar(128)') AS client_hostname,
    event_data.value('(event/action[@name="client_app_name"]/value)[1]', 'nvarchar(128)') AS client_app_name,
    event_data.value('(event/data[@name="result"]/value)[1]', 'varchar(50)') AS result,
    event_data.value('(event/data[@name="error"]/value)[1]', 'int') AS error_number,
    event_data.value('(event/data[@name="severity"]/value)[1]', 'int') AS severity,
    event_data.value('(event/data[@name="state"]/value)[1]', 'int') AS state,
    event_data.value('(event/data[@name="wait_type"]/text)[1]', 'varchar(60)') AS wait_type_text,
    event_data.value('(event/data[@name="wait_type"]/value)[1]', 'varchar(40)') AS wait_type_value,
    event_data.value('(event/data[@name="signal_duration"]/value)[1]', 'bigint') AS signal_duration,
    event_data.value('(event/data[@name="wait_resource"]/value)[1]', 'nvarchar(128)') AS wait_resource,
    event_data.value('(event/data[@name="blocking_session_id"]/value)[1]', 'int') AS blocking_session_id
FROM (
    SELECT CAST(event_data AS XML) AS event_data
    FROM sys.fn_xe_file_target_read_file(?, ?, ?, ?)
) AS tab
WHERE event_data.value('(event/@timestamp)[1]', 'datetime2(3)') > ?
ORDER BY event_data.value('(event/@timestamp)[1]', 'datetime2(3)')
"""


def read_xe_events(conn, last_timestamp):
    """Lee los eventos XE desde `last_timestamp`."""
    archivo = _ruta_xel(conn)
    if not archivo:
        return []
    meta = archivo.rsplit(".", 1)[0] + ".xem"
    cur = conn.cursor()
    cur.execute(_SQL_LECTURA_XE, (archivo, meta, None, None, last_timestamp))
    return cur.fetchall()


def map_xe_event(row):
    """Convierte una fila XE al dict que espera el motor de reglas."""
    nombre = row[0]
    ts = row[1]
    ts_str = (ts.strftime("%Y-%m-%d %H:%M:%S.") + f"{ts.microsecond // 1000:03d}"
              if ts else "")

    base = {
        "event_name": f"xe.{nombre}",
        "timestamp": ts_str,
        "database_name": row[9] or "SteelNort",
        "session_id": row[10],
        "username": row[11] or "unknown",
        "client_hostname": row[12],
        "client_app_name": row[13],
    }

    if nombre in ("sql_batch_completed", "rpc_completed"):
        base.update({
            "duration": row[2] or 0,
            "cpu_time": row[3] or 0,
            "logical_reads": row[4] or 0,
            "writes": row[5] or 0,
            "row_count": row[6] or 0,
            "sql_text": row[7] or row[8] or "",
            "result": row[14],
        })
    elif nombre in ("wait_info", "wait_completed", "locks_lock_waits"):
        wt_text = (row[18] or "").strip() if row[18] is not None else ""
        base.update({
            "wait_type": wt_text or (str(row[19]) if row[19] is not None else None),
            "duration": row[2] or 0,
            "signal_duration": row[20],
            "wait_resource": row[21],
            "blocking_session_id": row[22],
        })
    elif nombre == "error_reported":
        base.update({
            "sql_text": row[7] or row[8] or "",
            "error_number": row[15],
            "severity": row[16],
            "state": row[17],
        })
    elif nombre in ("xml_deadlock_report", "lock_deadlock"):
        base["message"] = "Deadlock detectado por Extended Events"

    return base


# ==========================================
# Captura a archivo (para entrenamiento)
# ==========================================
def collect_xe_loop():
    """Lee XE incremental y escribe events_xe.log."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, "events_xe.log")

    conn = _get_conn()
    if not conn:
        log("ERROR: sin conexión para XE")
        return

    if not is_xe_available(conn):
        log("XE no disponible; se omite el colector")
        try:
            conn.close()
        except Exception:
            pass
        return

    last_ts = datetime(2000, 1, 1)
    count = 0
    log(f"Leyendo XE cada {LOG_TAIL_INTERVAL}s")

    with open(filepath, "w", encoding="utf-8") as f:
        while not _stop_event.is_set():
            try:
                for row in read_xe_events(conn, last_ts):
                    f.write(json.dumps(map_xe_event(row), default=str) + "\n")
                    f.flush()
                    count += 1
                    if row[1] and row[1] > last_ts:
                        last_ts = row[1]
            except Exception as e:
                log(f"Error XE: {e}")
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _get_conn()
                if conn and not is_xe_available(conn):
                    log("XE dejó de estar disponible; se detiene")
                    break

            if count and count % 100 == 0:
                log(f"Eventos XE capturados: {count}")

            _stop_event.wait(LOG_TAIL_INTERVAL)

    if conn:
        try:
            conn.close()
        except Exception:
            pass
    log(f"Eventos XE: {count} -> {filepath}")


# ==========================================
# Arranque
# ==========================================
def start_xe_collector(token=None):
    """Arranca el colector XE (bloqueante)."""
    _stop_event.clear()
    collect_xe_loop()


def start_event_collector(token=None):
    """Arranca errorlog + XE en hilos paralelos (bloqueante)."""
    _stop_event.clear()
    h_errorlog = threading.Thread(target=tail_errorlog, daemon=True,
                                  name="errorlog")
    h_xe = threading.Thread(target=collect_xe_loop, daemon=True,
                            name="xe")
    h_errorlog.start()
    h_xe.start()
    h_xe.join()
    h_errorlog.join(timeout=5)
    log("Colector de eventos detenido")


if __name__ == "__main__":
    setup_xe()
    start_event_collector()