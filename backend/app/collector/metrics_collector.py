import psutil
import pyodbc
import requests
import os
import time
import threading
from datetime import datetime
from app.collector.config import (SQL_SERVER_CONN_STR, METRICS_INTERVAL,
                                  OUTPUT_DIR, API_URL, DURATION)


def log(msg):
    print(f"[METRICS] {msg}", flush=True)


_stop_event = threading.Event()


def get_system_metrics(prev_disk_read, prev_disk_write, prev_net_sent, prev_net_recv, prev_time):
    cpu_times = psutil.cpu_times_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_io_counters()
    net = psutil.net_io_counters()
    now = time.time()
    elapsed = max(now - prev_time, 0.001)

    disk_read_rate = (disk.read_bytes - prev_disk_read) / elapsed if disk else 0
    disk_write_rate = (disk.write_bytes - prev_disk_write) / elapsed if disk else 0
    net_send_rate = (net.bytes_sent - prev_net_sent) / elapsed
    net_recv_rate = (net.bytes_recv - prev_net_recv) / elapsed

    load = psutil.getloadavg()

    return [
        ("cpu_usr", f"{cpu_times.user:.1f}"),
        ("cpu_sys", f"{cpu_times.system:.1f}"),
        ("cpu_idl", f"{cpu_times.idle:.1f}"),
        ("cpu_wai", f"{getattr(cpu_times, 'iowait', 0.0):.1f}"),
        ("cpu_stl", f"{getattr(cpu_times, 'steal', 0):.1f}"),
        ("memory_percent", f"{mem.percent:.1f}"),
        ("memory_used_mb", f"{mem.used / (1024*1024):.0f}"),
        ("memory_available_mb", f"{mem.available / (1024*1024):.0f}"),
        ("disk_read_per_sec", f"{disk_read_rate:.0f}"),
        ("disk_write_per_sec", f"{disk_write_rate:.0f}"),
        ("net_send_per_sec", f"{net_send_rate:.0f}"),
        ("net_recv_per_sec", f"{net_recv_rate:.0f}"),
        ("load1", f"{load[0]:.2f}"),
        ("load5", f"{load[1]:.2f}"),
        ("load15", f"{load[2]:.2f}"),
    ], now, disk.read_bytes if disk else 0, disk.write_bytes if disk else 0, net.bytes_sent, net.bytes_recv


def get_sql_server_metrics(conn, prev_counters=None, dt=None):
    """Recolecta metricas SQL Server.

    `prev_counters` (dict: contador -> valor crudo previo) y `dt` (segundos entre
    muestras) permiten calcular tasas reales (delta/dt) de los contadores
    acumulativos tipicamente emitidos como valor crudo por sys.dm_os_performance_counters.

    Devuelve (metrics, nuevos_contadores) donde nuevos_contadores es el dict de
    los valores crudos actuales de los contadores acumulativos.
    """
    if prev_counters is None:
        prev_counters = {}
    if dt is None or dt <= 0:
        dt = 0.0
    metrics = []
    cursor = conn.cursor()

    queries = [
        ("active_sessions", "SELECT COUNT(*) FROM sys.dm_exec_sessions WHERE session_id > 50"),
        ("active_requests", "SELECT COUNT(*) FROM sys.dm_exec_requests WHERE session_id > 50"),
        ("long_queries", "SELECT COUNT(*) FROM sys.dm_exec_requests WHERE session_id > 50 AND DATEDIFF(SECOND, start_time, GETDATE()) > 15"),
        ("long_transactions", "SELECT COUNT(*) FROM sys.dm_exec_requests WHERE session_id > 50 AND DATEDIFF(SECOND, start_time, GETDATE()) > 30"),
        ("idle_sessions", "SELECT COUNT(*) FROM sys.dm_exec_sessions WHERE session_id > 50 AND status = 'sleeping'"),
        ("lock_waits", "SELECT COUNT(*) FROM sys.dm_tran_locks WHERE request_status = 'WAIT'"),
        ("total_locks", "SELECT COUNT(*) FROM sys.dm_tran_locks"),
    ]
    for name, sql in queries:
        try:
            cursor.execute(sql)
            metrics.append((name, str(cursor.fetchval() or 0)))
        except Exception:
            metrics.append((name, "0"))

    # Deadlocks/sec (contador crudo) y Page life expectancy (lectura directa)
    try:
        cursor.execute(
            "SELECT cntr_value FROM sys.dm_os_performance_counters "
            "WHERE counter_name = 'Number of Deadlocks/sec' AND instance_name = '_Total'"
        )
        metrics.append(("deadlocks_per_sec", str(cursor.fetchval() or 0)))
    except Exception:
        metrics.append(("deadlocks_per_sec", "0"))
    try:
        cursor.execute(
            "SELECT cntr_value FROM sys.dm_os_performance_counters "
            "WHERE counter_name = 'Page life expectancy' AND instance_name = ''"
        )
        metrics.append(("page_life_expectancy", str(cursor.fetchval() or 0)))
    except Exception:
        metrics.append(("page_life_expectancy", "0"))

    # Buffer cache hit ratio real: SQL Server expone dos contadores, el numerador
    # y el "base" (denominador). El ratio = numerador / base * 100.
    # Antes solo se guardaba el numerador, por lo que el valor no era un porcentaje
    # real e irrecuperable a posteriori. Ahora se calcula correctamente.
    try:
        cursor.execute(
            "SELECT cntr_value FROM sys.dm_os_performance_counters "
            "WHERE counter_name = 'Buffer cache hit ratio' AND instance_name = ''"
        )
        buf_ratio_num = int(cursor.fetchval() or 0)
    except Exception:
        buf_ratio_num = 0
    try:
        cursor.execute(
            "SELECT cntr_value FROM sys.dm_os_performance_counters "
            "WHERE counter_name = 'Buffer cache hit ratio base' AND instance_name = ''"
        )
        buf_ratio_base = int(cursor.fetchval() or 0)
    except Exception:
        buf_ratio_base = 0
    if buf_ratio_base > 0:
        buffer_hit_ratio = round(buf_ratio_num * 100.0 / buf_ratio_base, 2)
    else:
        buffer_hit_ratio = 0.0
    metrics.append(("buffer_cache_hit_ratio", str(buffer_hit_ratio)))

    # Contadores acumulativos que DMV emite como valor crudo. Se convierten a
    # tasa real por segundo (delta/dt) para no llegar en 0 / sin escala.
    CONTADORES_ACUMULATIVOS = [
        ("transactions_per_sec", "Transactions/sec"),
        ("page_reads_per_sec", "Page reads/sec"),
        ("page_writes_per_sec", "Page writes/sec"),
        ("rollbacks_per_sec", "Xact Rollbacks/sec"),
        ("batch_requests_per_sec", "Batch Requests/sec"),
        ("sql_compilations_per_sec", "SQL Compilations/sec"),
    ]
    nuevos_contadores = {}
    for name, counter_name in CONTADORES_ACUMULATIVOS:
        try:
            cursor.execute(
                "SELECT cntr_value FROM sys.dm_os_performance_counters "
                "WHERE counter_name = ? AND instance_name = '_Total'",
                counter_name
            )
            crudo = int(cursor.fetchval() or 0)
        except Exception:
            crudo = 0
        nuevos_contadores[name] = crudo
        if name in prev_counters and prev_counters[name] is not None:
            delta = crudo - prev_counters[name]
            tasa = round(delta / dt, 2) if dt > 0 else 0.0
            if tasa < 0:
                # contador reiniciado (ej. servidor reiniciado): sin delta valido
                tasa = 0.0
        else:
            # primera muestra: no hay referencia previa para el delta
            tasa = None
        if tasa is not None:
            metrics.append((name, str(tasa)))

    try:
        cursor.execute(
            "SELECT SUM(used_page_count) * 8 / 1024 "
            "FROM sys.dm_db_partition_stats WHERE database_id = DB_ID()"
        )
        metrics.append(("database_size_mb", str(cursor.fetchval() or 0)))
    except Exception:
        metrics.append(("database_size_mb", "0"))

    try:
        cursor.execute(
            "SELECT SUM(num_of_reads), SUM(num_of_writes) "
            "FROM sys.dm_io_virtual_file_stats(DB_ID(), NULL)"
        )
        row = cursor.fetchone()
        metrics.append(("total_reads", str(row[0] if row and row[0] else 0)))
        metrics.append(("total_writes", str(row[1] if row and row[1] else 0)))
    except Exception:
        metrics.append(("total_reads", "0"))
        metrics.append(("total_writes", "0"))

    return metrics, nuevos_contadores


# Sondeo de la API en hilo de fondo: el health probe NO debe estirar el ciclo
# de muestreo de metricas (bajo saturacion las llamadas literalmente al timeout
# de 5s y el intervalo efectivo pasaba de 5s a ~13s). El hilo actualiza una cache
# y collect_loop solo la lee, manteniendo el intervalo real cercano al configurado.
_api_lock = threading.Lock()
_api_cache = {"api_status": "0", "api_latency_ms": "0",
              "products_count": "0", "sales_count": "0"}


def _probe_api_once(token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    status = "0"
    latency = "0"
    products = "0"
    sales = "0"

    start = time.time()
    try:
        resp = requests.get(f"{API_URL}/api/productos", headers=headers, timeout=5)
        latency = f"{(time.time() - start) * 1000:.0f}"
        status = str(resp.status_code)
        if resp.status_code == 200:
            products = str(len(resp.json()))
    except Exception:
        latency = f"{(time.time() - start) * 1000:.0f}"

    try:
        resp = requests.get(f"{API_URL}/api/ventas", headers=headers, timeout=5)
        if resp.status_code == 200:
            sales = str(len(resp.json()))
    except Exception:
        pass

    with _api_lock:
        _api_cache.update(api_status=status, api_latency_ms=latency,
                          products_count=products, sales_count=sales)


def _api_probe_loop(token):
    while not _stop_event.is_set():
        _probe_api_once(token)
        _stop_event.wait(max(METRICS_INTERVAL, 1))


def get_api_metrics(token):
    with _api_lock:
        return [
            ("api_status", _api_cache["api_status"]),
            ("api_latency_ms", _api_cache["api_latency_ms"]),
            ("products_count", _api_cache["products_count"]),
            ("sales_count", _api_cache["sales_count"]),
        ]


def get_sql_server_settings(conn):
    metrics = []
    cursor = conn.cursor()

    settings = [
        ("max_server_memory", "SELECT CAST(value_in_use AS INT) FROM sys.configurations WHERE name = 'max server memory (MB)'"),
        ("user_connections_setting", "SELECT CAST(value_in_use AS INT) FROM sys.configurations WHERE name = 'user connections'"),
        ("cost_threshold", "SELECT CAST(value_in_use AS INT) FROM sys.configurations WHERE name = 'cost threshold for parallelism'"),
    ]
    for name, sql in settings:
        try:
            cursor.execute(sql)
            val = cursor.fetchval()
            metrics.append((name, str(val if val is not None else 0)))
        except Exception:
            metrics.append((name, "0"))

    return metrics


BUSINESS_TABLES = [
    ("venta_locks", "venta"),
    ("detalle_venta_locks", "detalle_venta"),
    ("inventario_locks", "inventario"),
    ("kardex_locks", "kardex"),
    ("caja_locks", "caja"),
    ("movimiento_caja_locks", "movimiento_caja"),
    ("auditoria_locks", "auditoria"),
]


def get_business_locks(conn):
    metrics = []
    cursor = conn.cursor()

    for metric_name, table_name in BUSINESS_TABLES:
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM sys.dm_tran_locks l "
                "JOIN sys.partitions p ON l.resource_associated_entity_id = p.hobt_id "
                "JOIN sys.tables t ON p.object_id = t.object_id "
                "WHERE l.request_session_id > 50 "
                "AND t.name = ?",
                table_name
            )
            metrics.append((metric_name, str(cursor.fetchval() or 0)))
        except Exception:
            metrics.append((metric_name, "0"))

    return metrics


def collect_loop(token):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, "metrics.log")

    prev_disk_read = psutil.disk_io_counters().read_bytes
    prev_disk_write = psutil.disk_io_counters().write_bytes
    prev_net_sent = psutil.net_io_counters().bytes_sent
    prev_net_recv = psutil.net_io_counters().bytes_recv
    prev_time = time.time()
    # Estado para tasas de contadores SQL Server acumulativos (delta/dt)
    prev_counters = {}
    sql_prev_time = None

    conn = None
    try:
        conn = pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        log("Conexion SQL Server establecida")
    except Exception as e:
        log(f"ERROR conexion SQL Server: {e}")

    t_api = threading.Thread(target=_api_probe_loop, args=(token,),
                             daemon=True, name="api-probe")
    t_api.start()

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("timestamp                 metric                    value\n")

        log(f"Recoleccion cada {METRICS_INTERVAL}s, duracion {DURATION}s")
        start_time = time.time()

        while not _stop_event.is_set():
            now = time.time()
            elapsed = now - start_time
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sys_result = get_system_metrics(prev_disk_read, prev_disk_write, prev_net_sent, prev_net_recv, prev_time)
            sys_metrics = sys_result[0]
            prev_time = sys_result[1]
            prev_disk_read = sys_result[2]
            prev_disk_write = sys_result[3]
            prev_net_sent = sys_result[4]
            prev_net_recv = sys_result[5]

            for name, val in sys_metrics:
                f.write(f"{ts:<26s}{name:<26s}{val}\n")

            if conn:
                # Delta de tiempo para tasas de contadores SS acumulativos
                ss_now = time.time()
                if sql_prev_time is not None:
                    dt_ss = ss_now - sql_prev_time
                else:
                    dt_ss = None
                sql_prev_time = ss_now
                try:
                    ss_metrics, nuevos_contadores = get_sql_server_metrics(
                        conn, prev_counters=prev_counters, dt=dt_ss
                    )
                    prev_counters = nuevos_contadores
                    for name, val in ss_metrics:
                        f.write(f"{ts:<26s}{name:<26s}{val}\n")
                except Exception as e:
                    log(f"Error metricas SS: {e}")
                    try:
                        conn = pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
                        ss_metrics, nuevos_contadores = get_sql_server_metrics(
                            conn, prev_counters=prev_counters, dt=dt_ss
                        )
                        prev_counters = nuevos_contadores
                        for name, val in ss_metrics:
                            f.write(f"{ts:<26s}{name:<26s}{val}\n")
                    except Exception:
                        pass

                try:
                    for name, val in get_business_locks(conn):
                        f.write(f"{ts:<26s}{name:<26s}{val}\n")
                except Exception:
                    pass

                if int(elapsed) % 60 == 0 and int(elapsed) > 0:
                    try:
                        for name, val in get_sql_server_settings(conn):
                            f.write(f"{ts:<26s}{name:<26s}{val}\n")
                    except Exception:
                        pass

            for name, val in get_api_metrics(token):
                f.write(f"{ts:<26s}{name:<26s}{val}\n")

            f.flush()

            if int(elapsed) % 60 == 0 and int(elapsed) > 0:
                log(f"Recolectado: {int(elapsed)}s / {DURATION}s")

            _stop_event.wait(METRICS_INTERVAL)

    if conn:
        try:
            conn.close()
        except Exception:
            pass
    log(f"Metricas guardadas en {filepath}")


def start_metrics_collector(token):
    _stop_event.clear()
    collect_loop(token)


if __name__ == "__main__":
    start_metrics_collector(None)
