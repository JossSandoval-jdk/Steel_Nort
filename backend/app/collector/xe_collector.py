import pyodbc
import os
import re
import time
import threading
import json
from datetime import datetime
from app.collector.config import SQL_SERVER_CONN_STR, OUTPUT_DIR, LOG_TAIL_INTERVAL, XE_FILE_PATH


def log(msg):
    print(f"[XE] {msg}", flush=True)


_stop_event = threading.Event()


def get_conn():
    for _ in range(10):
        try:
            return pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        except Exception:
            _stop_event.wait(2)
    return None


def setup_xe():
    log("Configurando Extended Events...")
    conn = get_conn()
    if not conn:
        log("ERROR: No se pudo conectar para setup XE")
        return False

    try:
        cursor = conn.cursor()

        cursor.execute(
            "IF EXISTS (SELECT 1 FROM sys.server_event_sessions WHERE name = 'SteelNortMonitor') "
            "BEGIN "
            "DROP EVENT SESSION [SteelNortMonitor] ON SERVER; "
            "END"
        )
        conn.commit()

        # Sesion compacta: archivos de max 100 MB y filtro de duracion para no
        # capturar TODOS los batches (evita .xel de 500 MB que ahogan el lector).
        cursor.execute(
            "CREATE EVENT SESSION [SteelNortMonitor] ON SERVER "
            "ADD EVENT sqlserver.sql_batch_completed("
            "ACTION(sqlserver.sql_text, sqlserver.database_name, sqlserver.session_id, "
            "sqlserver.username, sqlserver.client_hostname, sqlserver.client_app_name) "
            "WHERE sqlserver.database_name = N'SteelNort' AND duration >= 500000"
            "), "
            "ADD EVENT sqlserver.rpc_completed("
            "ACTION(sqlserver.sql_text, sqlserver.database_name, sqlserver.session_id, "
            "sqlserver.username) "
            "WHERE sqlserver.database_name = N'SteelNort' AND duration >= 500000"
            "), "
            "ADD EVENT sqlserver.error_reported("
            "ACTION(sqlserver.sql_text, sqlserver.session_id, sqlserver.database_name) "
            "WHERE sqlserver.database_name = N'SteelNort'"
            "), "
            "ADD EVENT sqlserver.xml_deadlock_report, "
            "ADD EVENT sqlserver.login, "
            "ADD EVENT sqlserver.logout "
            "ADD TARGET package0.event_file("
            "SET filename = N'/var/opt/mssql/log/steel_events.xel', "
            "max_file_size = 100, max_rollover_files = 5"
            ") "
            "WITH (MAX_MEMORY = 4096 KB, STARTUP_STATE = ON); "
        )
        conn.commit()
        log("Sesion SteelNortMonitor recreada (max_file_size=100MB, duration>=500ms)")

        cursor.execute(
            "IF NOT EXISTS (SELECT 1 FROM sys.dm_xe_sessions WHERE name = 'SteelNortMonitor') "
            "ALTER EVENT SESSION [SteelNortMonitor] ON SERVER STATE = START"
        )
        conn.commit()
        log("Sesion SteelNortMonitor activa")

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
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM sys.dm_xe_sessions WHERE name = 'SteelNortMonitor'")
        return cursor.fetchone() is not None
    except Exception:
        return False


def _tupla_lectura(conn):
    """Ruta EXACTA del archivo XE activo para lectura incremental.

    ``sys.dm_xe_session_targets.target_data`` expone el nombre del archivo
    actual; leer SOLO ese archivo (sin glob) evita escanear los .xel viejos
    (500 MB+) que provocaban Query timeout. La dedup se hace por timestamp
    en read_xe_events.
    """
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
            return None, None, None, None
        xml = row[0]
        m = re.search(r'<File name="([^"]+\.xel)"', str(xml))
        if not m:
            return None, None, None, None
        archivo = m.group(1)
        return archivo, archivo.rsplit(".", 1)[0] + ".xem", None, None
    except Exception:
        return None, None, None, None


def read_xe_events(conn, last_timestamp):
    patron_files, patron_meta, ini_file, ini_off = _tupla_lectura(conn)
    if not patron_files:
        return []
    sql = """
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
        event_data.value('(event/data[@name="state"]/value)[1]', 'int') AS state
    FROM (
        SELECT CAST(event_data AS XML) AS event_data
        FROM sys.fn_xe_file_target_read_file(
            ?, ?, ?, ?
        )
    ) AS tab
    WHERE event_data.value('(event/@timestamp)[1]', 'datetime2(3)') > ?
    ORDER BY event_data.value('(event/@timestamp)[1]', 'datetime2(3)')
    """
    cursor = conn.cursor()
    cursor.execute(sql, (patron_files, patron_meta, ini_file, ini_off, last_timestamp))
    return cursor.fetchall()


def map_xe_event(row):
    event_name = row[0]
    ts = row[1]
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S.") + f"{ts.microsecond // 1000:03d}" if ts else ""

    base = {
        "event_name": f"xe.{event_name}",
        "timestamp": ts_str,
        "database_name": row[9] or "SteelNort",
        "session_id": row[10],
        "username": row[11] or "unknown",
    }

    if event_name in ("sql_batch_completed", "rpc_completed"):
        base["duration"] = row[2] or 0
        base["cpu_time"] = row[3] or 0
        base["logical_reads"] = row[4] or 0
        base["writes"] = row[5] or 0
        base["row_count"] = row[6] or 0
        base["sql_text"] = (row[7] or row[8] or "")[:500]
        base["client_hostname"] = row[12]
        base["client_app_name"] = row[13]
        base["result"] = row[14]

    elif event_name == "error_reported":
        base["sql_text"] = (row[7] or row[8] or "")[:500]
        base["error_number"] = row[15]
        base["severity"] = row[16]
        base["state"] = row[17]

    elif event_name == "xml_deadlock_report":
        base["message"] = "Deadlock detected via Extended Events"

    elif event_name in ("login", "logout"):
        pass

    return base


def collect_xe_loop(token):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, "events_xe.log")

    conn = get_conn()
    if not conn:
        log("ERROR: No se pudo conectar a SQL Server para XE")
        return

    if not is_xe_available(conn):
        log("WARNING: Extended Events no esta disponible. Omitiendo collector XE.")
        try:
            conn.close()
        except Exception:
            pass
        return

    last_ts = datetime(2000, 1, 1)
    count = 0

    log(f"Leyendo Extended Events cada {LOG_TAIL_INTERVAL}s")

    with open(filepath, "w", encoding="utf-8") as f:
        while not _stop_event.is_set():
            try:
                rows = read_xe_events(conn, last_ts)
                for row in rows:
                    event = map_xe_event(row)
                    f.write(json.dumps(event, default=str) + "\n")
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
                conn = get_conn()
                if conn and not is_xe_available(conn):
                    log("XE no disponible, deteniendo collector")
                    break

            if count > 0 and count % 100 == 0:
                log(f"Eventos XE capturados: {count}")

            _stop_event.wait(LOG_TAIL_INTERVAL)

    if conn:
        try:
            conn.close()
        except Exception:
            pass
    log(f"Eventos XE: {count}. Output: {filepath}")


def start_xe_collector(token):
    _stop_event.clear()
    collect_xe_loop(token)


if __name__ == "__main__":
    setup_xe()
    start_xe_collector(None)
