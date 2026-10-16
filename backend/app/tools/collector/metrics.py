"""
metrics.py
==========
Recolecta métricas del sistema, de SQL Server y de la API de negocio.

Dos modos de uso:
  1. Captura a archivo: `collect_loop(token)` escribe metrics.log.
  2. Muestreo puntual: `get_system_metrics()`, `get_sql_server_metrics()`,
     `get_business_locks()`, `get_api_metrics()` los usa el stream daemon.
"""

import os
import threading
import time
from datetime import datetime

import psutil
import pyodbc
import requests

from app.tools.collector.config import (
    API_URL, DURATION, METRICS_INTERVAL, OUTPUT_DIR, SQL_SERVER_CONN_STR,
)


def log(msg):
    print(f"[METRICS] {msg}", flush=True)


_stop_event = threading.Event()


# ==========================================
# Métricas del sistema (psutil)
# ==========================================
def get_system_metrics(prev_disk_r, prev_disk_w, prev_net_s, prev_net_r, prev_time):
    """Métricas del SO y de la VM. Devuelve (métricas, nuevo_estado)."""
    cpu = psutil.cpu_times_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_io_counters()
    net = psutil.net_io_counters()
    now = time.time()
    dt = max(now - prev_time, 0.001)
    load = psutil.getloadavg()

    metrics = [
        ("cpu_usr", f"{cpu.user:.1f}"),
        ("cpu_sys", f"{cpu.system:.1f}"),
        ("cpu_idl", f"{cpu.idle:.1f}"),
        ("cpu_wai", f"{getattr(cpu, 'iowait', 0.0):.1f}"),
        ("cpu_stl", f"{getattr(cpu, 'steal', 0.0):.1f}"),
        ("memory_percent", f"{mem.percent:.1f}"),
        ("memory_used_mb", f"{mem.used / (1024 * 1024):.0f}"),
        ("memory_available_mb", f"{mem.available / (1024 * 1024):.0f}"),
        ("disk_read_per_sec", f"{(disk.read_bytes - prev_disk_r) / dt:.0f}" if disk else None),
        ("disk_write_per_sec", f"{(disk.write_bytes - prev_disk_w) / dt:.0f}" if disk else None),
        ("net_send_per_sec", f"{(net.bytes_sent - prev_net_s) / dt:.0f}"),
        ("net_recv_per_sec", f"{(net.bytes_recv - prev_net_r) / dt:.0f}"),
        ("load1", f"{load[0]:.2f}"),
        ("load5", f"{load[1]:.2f}"),
        ("load15", f"{load[2]:.2f}"),
    ]
    estado = (
        now,
        disk.read_bytes if disk else 0,
        disk.write_bytes if disk else 0,
        net.bytes_sent,
        net.bytes_recv,
    )
    return metrics, estado


# ==========================================
# Métricas de SQL Server
# ==========================================
CONTADORES_ACUMULATIVOS = [
    ("transactions_per_sec", "Transactions/sec"),
    ("page_reads_per_sec", "Page reads/sec"),
    ("page_writes_per_sec", "Page writes/sec"),
    ("rollbacks_per_sec", "Xact Rollbacks/sec"),
    ("batch_requests_per_sec", "Batch Requests/sec"),
    ("sql_compilations_per_sec", "SQL Compilations/sec"),
]

TABLAS_NEGOCIO = [
    ("venta_locks", "venta"),
    ("detalle_venta_locks", "detalle_venta"),
    ("inventario_locks", "inventario"),
    ("kardex_locks", "kardex"),
    ("caja_locks", "caja"),
    ("movimiento_caja_locks", "movimiento_caja"),
    ("auditoria_locks", "auditoria"),
]


def _cntr_value(cursor, counter, instance="'_Total'"):
    """Lee un contador acumulativo de sys.dm_os_performance_counters."""
    try:
        cursor.execute(
            "SELECT cntr_value FROM sys.dm_os_performance_counters "
            f"WHERE counter_name = ? AND instance_name = {instance}",
            counter,
        )
        v = cursor.fetchval()
        return int(v) if v is not None else None
    except Exception:
        return None


def get_sql_server_metrics(conn, prev_counters=None, dt=None):
    """Métricas de SQL Server.

    prev_counters: dict {contador: valor_crudo} del ciclo anterior.
    dt: segundos entre muestras (para tasas delta/dt).
    Devuelve (métricas, nuevos_contadores).
    """
    prev_counters = prev_counters or {}
    dt = dt or 0.0
    metrics = []
    cursor = conn.cursor()

    # Conteos directos
    conteos = [
        ("active_sessions", "SELECT COUNT(*) FROM sys.dm_exec_sessions WHERE session_id > 50"),
        ("active_requests", "SELECT COUNT(*) FROM sys.dm_exec_requests WHERE session_id > 50"),
        ("long_queries",
         "SELECT COUNT(*) FROM sys.dm_exec_requests "
         "WHERE session_id > 50 AND DATEDIFF(SECOND, start_time, GETDATE()) > 15"),
        ("long_transactions",
         "SELECT COUNT(*) FROM sys.dm_exec_requests "
         "WHERE session_id > 50 AND DATEDIFF(SECOND, start_time, GETDATE()) > 30"),
        ("idle_sessions",
         "SELECT COUNT(*) FROM sys.dm_exec_sessions "
         "WHERE session_id > 50 AND status = 'sleeping'"),
        ("lock_waits", "SELECT COUNT(*) FROM sys.dm_tran_locks WHERE request_status = 'WAIT'"),
        ("total_locks", "SELECT COUNT(*) FROM sys.dm_tran_locks"),
    ]
    for name, sql in conteos:
        try:
            cursor.execute(sql)
            v = cursor.fetchval()
            metrics.append((name, str(v) if v is not None else None))
        except Exception:
            metrics.append((name, None))

    dv = _cntr_value(cursor, "Number of Deadlocks/sec")
    pv = _cntr_value(cursor, "Page life expectancy", "''")
    # Deadlocks y PLE
    metrics.append(("deadlocks_per_sec", str(dv) if dv is not None else None))
    metrics.append(("page_life_expectancy", str(pv) if pv is not None else None))

    # Buffer cache hit ratio (numerador/base * 100)
    try:
        cursor.execute(
            "SELECT cntr_value FROM sys.dm_os_performance_counters "
            "WHERE counter_name = 'Buffer cache hit ratio' AND instance_name = ''"
        )
        num = int(v) if v is not None else None
    except Exception:
        num = None
    try:
        cursor.execute(
            "SELECT cntr_value FROM sys.dm_os_performance_counters "
            "WHERE counter_name = 'Buffer cache hit ratio base' AND instance_name = ''"
        )
        base = int(v) if v is not None else 0
    except Exception:
        base = 0
    ratio = round(num * 100.0 / base, 2) if (base > 0 and num is not None) else None
    metrics.append(("buffer_cache_hit_ratio", str(ratio) if ratio is not None else None))

    # Contadores acumulativos -> tasas (delta/dt)
    nuevos = {}
    for name, counter in CONTADORES_ACUMULATIVOS:
        crudo = _cntr_value(cursor, counter)
        nuevos[name] = crudo
        if name in prev_counters and prev_counters[name] is not None:
            delta = crudo - prev_counters[name] if crudo is not None else None
            tasa = round(delta / dt, 2) if (dt > 0 and delta is not None and delta >= 0) else None
            metrics.append((name, str(tasa) if tasa is not None else None))

    # Tamaño de BD y totales de I/O
    try:
        cursor.execute(
            "SELECT SUM(used_page_count) * 8 / 1024 "
            "FROM sys.dm_db_partition_stats WHERE database_id = DB_ID()"
        )
        v = cursor.fetchval()
        metrics.append(("database_size_mb", str(v) if v is not None else None))
    except Exception:
        metrics.append(("database_size_mb", None))

    try:
        cursor.execute(
            "SELECT SUM(num_of_reads), SUM(num_of_writes) "
            "FROM sys.dm_io_virtual_file_stats(DB_ID(), NULL)"
        )
        row = cursor.fetchone()
        r0 = row[0] if row and row[0] is not None else None
        r1 = row[1] if row and row[1] is not None else None
        metrics.append(("total_reads", str(r0) if r0 is not None else None))
        metrics.append(("total_writes", str(r1) if r1 is not None else None))
    except Exception:
        metrics.append(("total_reads", None))
        metrics.append(("total_writes", None))

    return metrics, nuevos


def get_business_locks(conn):
    """Locks por tabla de negocio (venta, inventario, etc.)."""
    metrics = []
    cursor = conn.cursor()
    for metric_name, table_name in TABLAS_NEGOCIO:
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM sys.dm_tran_locks l "
                "JOIN sys.partitions p ON l.resource_associated_entity_id = p.hobt_id "
                "JOIN sys.tables t ON p.object_id = t.object_id "
                "WHERE l.request_session_id > 50 AND t.name = ?",
                table_name,
            )
            v = cursor.fetchval()
            metrics.append((metric_name, str(v) if v is not None else None))
        except Exception:
            metrics.append((metric_name, None))
    return metrics


def get_sql_server_settings(conn):
    """Configuraciones de SQL Server (se leen 1 vez por minuto)."""
    metrics = []
    cursor = conn.cursor()
    settings = [
        ("max_server_memory",
         "SELECT CAST(value_in_use AS INT) FROM sys.configurations "
         "WHERE name = 'max server memory (MB)'"),
        ("user_connections_setting",
         "SELECT CAST(value_in_use AS INT) FROM sys.configurations "
         "WHERE name = 'user connections'"),
        ("cost_threshold",
         "SELECT CAST(value_in_use AS INT) FROM sys.configurations "
         "WHERE name = 'cost threshold for parallelism'"),
    ]
    for name, sql in settings:
        try:
            cursor.execute(sql)
            v = cursor.fetchval()
            metrics.append((name, str(v) if v is not None else None))
        except Exception:
            metrics.append((name, None))
    return metrics


# ==========================================
# API de negocio (probe en hilo de fondo)
# ==========================================
_api_lock = threading.Lock()
_api_cache = {
    "api_status": None, "api_latency_ms": None,
    "products_count": None, "sales_count": None,
}


def _probe_api_once(token):
    """Ping a la API de negocio. Actualiza _api_cache."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    status, latency, products, sales = None, None, None, None

    start = time.time()
    try:
        r = requests.get(f"{API_URL}/api/productos", headers=headers, timeout=5)
        latency = f"{(time.time() - start) * 1000:.0f}" if 'start' in locals() else None
        status = str(r.status_code) if r else None
        if r and r.status_code == 200:
            try:
                products = str(len(r.json()))
            except Exception:
                products = None
    except Exception:
        latency = f"{(time.time() - start) * 1000:.0f}"

    try:
        r = requests.get(f"{API_URL}/api/ventas", headers=headers, timeout=5)
        if r.status_code == 200:
            sales = str(len(r.json())) if r.status_code == 200 else None
    except Exception:
        pass

    with _api_lock:
        _api_cache.update(
            api_status=status, api_latency_ms=latency,
            products_count=products, sales_count=sales,
        )


def _api_probe_loop(token):
    """Probe de la API en hilo de fondo (no bloquea el ciclo de métricas)."""
    while not _stop_event.is_set():
        _probe_api_once(token)
        _stop_event.wait(max(METRICS_INTERVAL, 1))


def get_api_metrics(token=None):
    """Devuelve la última lectura cacheada del probe."""
    with _api_lock:
        return [
            ("api_status", _api_cache["api_status"]),
            ("api_latency_ms", _api_cache["api_latency_ms"]),
            ("products_count", _api_cache["products_count"]),
            ("sales_count", _api_cache["sales_count"]),
        ]


# ==========================================
# Captura a archivo (para entrenamiento)
# ==========================================
def collect_loop(token, duration=DURATION):
    """Escribe metrics.log durante `duration` segundos cada METRICS_INTERVAL."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, "metrics.log")

    # Estado inicial para tasas
    disk = psutil.disk_io_counters()
    net = psutil.net_io_counters()
    prev = (disk.read_bytes, disk.write_bytes, net.bytes_sent, net.bytes_recv, time.time())
    prev_counters = {}
    sql_prev_time = None

    # Conexión SQL
    conn = None
    try:
        conn = pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        log("Conexión SQL Server establecida")
    except Exception as e:
        log(f"ERROR conexión SQL Server: {e}")

    # Probe de API en hilo
    threading.Thread(target=_api_probe_loop, args=(token,),
                     daemon=True, name="api-probe").start()

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("timestamp                 metric                    value\n")
        log(f"Recolección cada {METRICS_INTERVAL}s, duración {duration}s")
        start = time.time()

        while not _stop_event.is_set():
            now = time.time()
            elapsed = now - start
            if duration and elapsed > duration:
                break
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # SO
            sys_metrics, prev = get_system_metrics(*prev)
            for name, val in sys_metrics:
                f.write(f"{ts:<26s}{name:<26s}{val}\n")

            # SQL Server
            if conn:
                ss_now = time.time()
                dt = (ss_now - sql_prev_time) if sql_prev_time else None
                sql_prev_time = ss_now
                try:
                    ss_metrics, prev_counters = get_sql_server_metrics(
                        conn, prev_counters, dt)
                    for name, val in ss_metrics:
                        f.write(f"{ts:<26s}{name:<26s}{val}\n")
                except Exception as e:
                    log(f"Error métricas SS: {e}")

                for name, val in get_business_locks(conn):
                    f.write(f"{ts:<26s}{name:<26s}{val}\n")

                if int(elapsed) % 60 == 0 and int(elapsed) > 0:
                    for name, val in get_sql_server_settings(conn):
                        f.write(f"{ts:<26s}{name:<26s}{val}\n")

            # API
            for name, val in get_api_metrics(token):
                f.write(f"{ts:<26s}{name:<26s}{val}\n")

            f.flush()
            if int(elapsed) % 60 == 0 and int(elapsed) > 0:
                log(f"Recolectado: {int(elapsed)}s / {duration}s")

            _stop_event.wait(METRICS_INTERVAL)

    if conn:
        try:
            conn.close()
        except Exception:
            pass
    log(f"Métricas guardadas en {filepath}")


def start_metrics_collector(token, duration=DURATION):
    """Arranca la captura a archivo en modo bloqueante."""
    _stop_event.clear()
    collect_loop(token, duration=duration)


if __name__ == "__main__":
    start_metrics_collector(None)