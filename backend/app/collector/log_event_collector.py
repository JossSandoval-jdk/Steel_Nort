import pyodbc
import os
import time
import threading
import json
from datetime import datetime
from app.collector.config import (SQL_SERVER_CONN_STR, OUTPUT_DIR,
                    LOG_TAIL_INTERVAL, AUDIT_POLL_INTERVAL)


def log(msg):
    print(f"[LOG-EVENT] {msg}", flush=True)


_stop_event = threading.Event()


def get_conn():
    for _ in range(10):
        try:
            return pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        except Exception:
            _stop_event.wait(2)
    return None


def classify_errorlog(text):
    t = text.lower()
    if "deadlock" in t:
        return "DEADLOCK"
    if "error" in t:
        return "ERROR"
    if "warning" in t:
        return "WARNING"
    if "backup" in t:
        return "BACKUP"
    if "restore" in t:
        return "RESTORE"
    if "login" in t and "failed" in t:
        return "LOGIN_FAILED"
    if "login" in t:
        return "LOGIN"
    if "online" in t or "offline" in t:
        return "STATE_CHANGE"
    if "starting" in t or "shutdown" in t:
        return "SERVER_LIFECYCLE"
    if "roll back" in t or "rollback" in t:
        return "ROLLBACK"
    return "INFO"


def tail_sql_server_errorlog():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, "sqlserver_logs.log")

    seen = set()
    count = 0
    conn = get_conn()
    if not conn:
        return

    log(f"Leyendo SQL Server error log cada {LOG_TAIL_INTERVAL}s")

    with open(filepath, "w", encoding="utf-8") as f:
        while not _stop_event.is_set():
            try:
                cursor = conn.cursor()
                cursor.execute("EXEC sp_readerrorlog 0")
                rows = cursor.fetchall()

                for row in rows:
                    log_date = row[0] if row[0] else None
                    process_info = str(row[1]).strip() if row[1] else ""
                    text = str(row[2]).strip() if row[2] else ""

                    if not text:
                        continue

                    text_key = (str(log_date), process_info, text)
                    if text_key in seen:
                        continue
                    seen.add(text_key)

                    if log_date:
                        if hasattr(log_date, 'strftime'):
                            ts = log_date.strftime("%Y-%m-%d %H:%M:%S.") + f"{log_date.microsecond // 1000:03d}"
                        else:
                            ts = str(log_date)[:23]
                    else:
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.000")

                    clean = " ".join(text.split())
                    f.write(f"{ts}  {process_info:<15s}{clean}\n")
                    f.flush()
                    count += 1

            except Exception as e:
                log(f"Error errorlog: {e}")
                try:
                    conn.close()
                except Exception:
                    pass
                conn = get_conn()

            _stop_event.wait(LOG_TAIL_INTERVAL)

    if conn:
        try:
            conn.close()
        except Exception:
            pass
    log(f"SQL Server logs: {count}. Output: {filepath}")


def poll_real_events():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, "events.log")

    conn = get_conn()
    if not conn:
        return

    prev_sessions = set()
    prev_requests = {}
    prev_locks = set()
    prev_deadlocks = 0
    prev_rollbacks = 0
    first_poll = True
    count = 0

    log(f"Capturando eventos reales cada {AUDIT_POLL_INTERVAL}s")

    with open(filepath, "w", encoding="utf-8") as f:
        while not _stop_event.is_set():
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.") + f"{datetime.now().microsecond // 1000:03d}"

            try:
                cursor = conn.cursor()

                try:
                    cursor.execute(
                        "SELECT cntr_value FROM sys.dm_os_performance_counters "
                        "WHERE counter_name = 'Number of Deadlocks/sec' "
                        "AND instance_name = '_Total'"
                    )
                    cur_deadlocks = cursor.fetchval() or 0
                    if cur_deadlocks > prev_deadlocks:
                        for _ in range(cur_deadlocks - prev_deadlocks):
                            event = {
                                "event_name": "xml_deadlock_report",
                                "timestamp": ts,
                                "database_name": "SteelNort",
                                "severity": 13,
                                "error_number": 1205,
                                "message": "Deadlock detected"
                            }
                            f.write(json.dumps(event) + "\n")
                            f.flush()
                            count += 1
                    prev_deadlocks = cur_deadlocks
                except Exception:
                    pass

                try:
                    cursor.execute(
                        "SELECT cntr_value FROM sys.dm_os_performance_counters "
                        "WHERE counter_name = 'Xact Rollbacks/sec' "
                        "AND instance_name = '_Total'"
                    )
                    cur_rollbacks = cursor.fetchval() or 0
                    if cur_rollbacks > prev_rollbacks:
                        for _ in range(cur_rollbacks - prev_rollbacks):
                            event = {
                                "event_name": "error_reported",
                                "timestamp": ts,
                                "database_name": "SteelNort",
                                "error_number": 3930,
                                "severity": 16,
                                "message": "Transaction was rolled back"
                            }
                            f.write(json.dumps(event) + "\n")
                            f.flush()
                            count += 1
                    prev_rollbacks = cur_rollbacks
                except Exception:
                    pass

                try:
                    cursor.execute(
                        "SELECT session_id, login_name, program_name "
                        "FROM sys.dm_exec_sessions WHERE session_id > 50"
                    )
                    cur_sessions = {}
                    for row in cursor.fetchall():
                        cur_sessions[row[0]] = (row[1], row[2])

                    new_sessions = set(cur_sessions.keys()) - prev_sessions
                    if not first_poll:
                        for sid in new_sessions:
                            login, prog = cur_sessions[sid]
                            event = {
                                "event_name": "login",
                                "timestamp": ts,
                                "session_id": sid,
                                "login_name": login or "unknown",
                                "program_name": prog or "unknown",
                                "database_name": "SteelNort"
                            }
                            f.write(json.dumps(event) + "\n")
                            f.flush()
                            count += 1

                        closed_sessions = prev_sessions - set(cur_sessions.keys())
                        for sid in closed_sessions:
                            event = {
                                "event_name": "logout",
                                "timestamp": ts,
                                "session_id": sid
                            }
                            f.write(json.dumps(event) + "\n")
                            f.flush()
                            count += 1

                    prev_sessions = set(cur_sessions.keys())
                except Exception:
                    pass

                try:
                    cursor.execute(
                        "SELECT r.session_id, r.command, r.wait_type, "
                        "r.blocking_session_id, r.cpu_time, r.reads, r.writes, "
                        "r.start_time, DB_NAME(r.database_id), "
                        "r.signal_wait_time_ms, r.wait_resource "
                        "FROM sys.dm_exec_requests r WHERE r.session_id > 50"
                    )
                    cur_requests = {}
                    for row in cursor.fetchall():
                        sid = row[0]
                        cur_requests[sid] = {
                            "cmd": row[1], "wait": row[2], "blocking": row[3],
                            "cpu": row[4], "reads": row[5], "writes": row[6],
                            "start": row[7], "db": row[8],
                            "signal_wait_ms": row[9], "wait_resource": row[10]
                        }

                    for sid, req in cur_requests.items():
                        if sid not in prev_requests:
                            if not first_poll:
                                elapsed_ms = 0
                                if req['start']:
                                    delta = datetime.now() - req['start']
                                    elapsed_ms = int(delta.total_seconds() * 1000)
                                event = {
                                    "event_name": "sql_batch_completed",
                                    "timestamp": ts,
                                    "database_name": req['db'] or "SteelNort",
                                    "session_id": sid,
                                    "command": req['cmd'],
                                    "duration": elapsed_ms,
                                    "cpu_time": req['cpu'] or 0,
                                    "logical_reads": req['reads'] or 0,
                                    "writes": req['writes'] or 0,
                                    "signal_wait_time_ms": req['signal_wait_ms'] or 0,
                                    "wait_resource": req['wait_resource'] or None
                                }
                                if req['wait'] and req['wait'] != 'NONE':
                                    event["wait_type"] = req['wait']
                                if req['blocking']:
                                    event["blocking_session_id"] = req['blocking']
                                f.write(json.dumps(event) + "\n")
                                f.flush()
                                count += 1
                        else:
                            prev_req = prev_requests[sid]
                            if req['wait'] != prev_req['wait'] and req['wait'] and req['wait'] != 'NONE':
                                # Duración transcurrida hasta ahora (puede ser 0 si no hay start_time).
                                w_elapsed = 0
                                if req['start']:
                                    w_elapsed = int((datetime.now() - req['start']).total_seconds() * 1000)
                                event = {
                                    "event_name": "wait_info",
                                    "timestamp": ts,
                                    "session_id": sid,
                                    "wait_type": req['wait'],
                                    "database_name": req['db'] or "SteelNort",
                                    "signal_wait_time_ms": req['signal_wait_ms'] or 0,
                                    "wait_resource": req['wait_resource'] or None,
                                    "cpu_time": req['cpu'] or 0,
                                    "duration": w_elapsed
                                }
                                if req['blocking']:
                                    event["blocking_session_id"] = req['blocking']
                                f.write(json.dumps(event) + "\n")
                                f.flush()
                                count += 1
                            if req['blocking'] and req['blocking'] != prev_req.get('blocking'):
                                event = {
                                    "event_name": "blocked_process_report",
                                    "timestamp": ts,
                                    "session_id": sid,
                                    "blocking_session_id": req['blocking'],
                                    "database_name": req['db'] or "SteelNort"
                                }
                                f.write(json.dumps(event) + "\n")
                                f.flush()
                                count += 1

                    closed_requests = set(prev_requests.keys()) - set(cur_requests.keys())
                    for sid in closed_requests:
                        prev_req = prev_requests[sid]
                        elapsed_ms = 0
                        if prev_req['start']:
                            delta = datetime.now() - prev_req['start']
                            elapsed_ms = int(delta.total_seconds() * 1000)
                        event = {
                            "event_name": "sql_batch_completed",
                            "timestamp": ts,
                            "database_name": prev_req['db'] or "SteelNort",
                            "session_id": sid,
                            "command": prev_req['cmd'],
                            "duration": elapsed_ms,
                            "cpu_time": prev_req['cpu'] or 0,
                            "logical_reads": prev_req['reads'] or 0,
                            "writes": prev_req['writes'] or 0,
                            "signal_wait_time_ms": prev_req['signal_wait_ms'] or 0,
                            "wait_resource": prev_req['wait_resource'] or None,
                            "status": "completed"
                        }
                        f.write(json.dumps(event) + "\n")
                        f.flush()
                        count += 1

                    prev_requests = cur_requests
                except Exception:
                    pass

                try:
                    cursor.execute(
                        "SELECT request_session_id, resource_type, "
                        "request_mode, request_status "
                        "FROM sys.dm_tran_locks "
                        "WHERE request_session_id > 50 AND request_status = 'GRANT'"
                    )
                    cur_locks = set()
                    for row in cursor.fetchall():
                        cur_locks.add((row[0], row[1], row[2]))

                    new_locks = cur_locks - prev_locks
                    if not first_poll:
                        for lock in new_locks:
                            event = {
                                "event_name": "lock_acquired",
                                "timestamp": ts,
                                "session_id": lock[0],
                                "resource_type": lock[1],
                                "mode": lock[2]
                            }
                            f.write(json.dumps(event) + "\n")
                            f.flush()
                            count += 1

                        released_locks = prev_locks - cur_locks
                        for lock in released_locks:
                            event = {
                                "event_name": "lock_released",
                                "timestamp": ts,
                                "session_id": lock[0],
                                "resource_type": lock[1],
                                "mode": lock[2]
                            }
                            f.write(json.dumps(event) + "\n")
                            f.flush()
                            count += 1

                    prev_locks = cur_locks
                except Exception:
                    pass

            except Exception as e:
                log(f"Error eventos: {e}")
                try:
                    conn.close()
                except Exception:
                    pass
                conn = get_conn()

            if count > 0 and count % 200 == 0:
                log(f"Eventos reales capturados: {count}")

            first_poll = False
            _stop_event.wait(AUDIT_POLL_INTERVAL)

    if conn:
        try:
            conn.close()
        except Exception:
            pass
    log(f"Eventos reales: {count}. Output: {filepath}")


def start_log_event_collector():
    _stop_event.clear()

    t1 = threading.Thread(target=tail_sql_server_errorlog, daemon=True, name="sqlserver-logs")
    t2 = threading.Thread(target=poll_real_events, daemon=True, name="sqlserver-events")

    t1.start()
    t2.start()

    t2.join()
    t1.join(timeout=5)

    log("Log/Event collector completado")


if __name__ == "__main__":
    start_log_event_collector()
