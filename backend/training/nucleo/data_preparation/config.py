"""
config.py
=========

Configuración central de la fase de PREPARACIÓN DE DATOS (CRISP-DM)
para la detección de anomalías de rendimiento OLTP de SteelNort.

La preparación trabaja con cargas/corridas independientes.

Cada carga contiene sus propios archivos de captura:

    carga_001/
        metrics.log
        events.log
        sqlserver_logs.log

    carga_002/
        metrics.log
        events.log
        sqlserver_logs.log

Este archivo SOLO define:
    - Rutas
    - Nombres de archivos
    - Variables canónicas
    - Variables principales para el modelo
    - Variables de diagnóstico
    - Variables redundantes
    - Variables que requieren corrección
    - Reglas generales de preparación

NO se etiquetan anomalías aquí.
NO se define una carga normal fija.
NO se define una carga específica a procesar.
"""

from pathlib import Path


# ============================================================
# 1. RUTAS DEL PROYECTO
# ============================================================

BASE_PROYECTO = Path(__file__).resolve().parent

OUTPUT_BASE_DIR = Path(
    __import__("os").getenv(
        "STEELNORT_OUTPUT_DIR",
        BASE_PROYECTO / "output"
    )
)

DIR_DATASETS = OUTPUT_BASE_DIR / "datasets"
DIR_INVENTARIO = OUTPUT_BASE_DIR / "inventario"
DIR_LIMPIO = OUTPUT_BASE_DIR / "limpio"
DIR_INTEGRADO = OUTPUT_BASE_DIR / "integrado"


# ============================================================
# 2. ARCHIVOS DE SALIDA
# ============================================================

ARCHIVO_INVENTARIO = "inventario_corridas.csv"

ARCHIVO_VARIABLES = "variables_seleccionadas.csv"

ARCHIVO_DATASET_INTEGRADO = "dataset_steelnort_preparado.csv"

ARCHIVO_DATASET_MODELO = "dataset_steelnort_preparado_modelo.csv"

ARCHIVO_METADATA = "metadata_transformaciones.json"

ARCHIVO_REPORTE_CALIDAD = "reporte_calidad_datos.csv"

ARCHIVO_VARIABLES_CLAVE = "variables_clave.csv"

ARCHIVO_DATASET_CLAVE = "dataset_carga_clave.csv"

ARCHIVO_VARIABLES_PRINCIPALES = "variables_principales.csv"

ARCHIVO_DATASET_PRINCIPALES = "dataset_carga_principales.csv"

ARCHIVO_DATASET_EVENTOS = "dataset_eventos.csv"

ARCHIVO_DATASET_LOGS = "dataset_logs.csv"


# ============================================================
# 3. ARCHIVOS INTERMEDIOS
# ============================================================

NOMBRE_METRICAS_LIMPIO = "metricas_limpio.csv"

NOMBRE_EVENTS_LIMPIO = "eventos_limpio.csv"

NOMBRE_SQLSERVER_LOGS_LIMPIO = "sqlserver_logs_limpio.csv"

NOMBRE_EVENTOS_PREPARADOS = "eventos_preparados.csv"

NOMBRE_LOGS_PREPARADOS = "logs_preparados.csv"

NOMBRE_TRANSFORMADO = "datos_transformados.csv"


# ============================================================
# 4. ARCHIVOS DE ENTRADA
# ============================================================

"""
Cada carga/corrida debe contener únicamente estos archivos.

Ejemplo:

carga_001/
    metrics.log
    events.log
    sqlserver_logs.log
"""

NOMBRE_METRICAS = "metrics.log"

NOMBRE_EVENTS = "events.log"

NOMBRE_SQLSERVER_LOGS = "sqlserver_logs.log"


ARCHIVOS_ENTRADA = [
    NOMBRE_METRICAS,
    NOMBRE_EVENTS,
    NOMBRE_SQLSERVER_LOGS,
]


# ============================================================
# 5. CONFIGURACIÓN GENERAL
# ============================================================

FORMATO_INTERMEDIO = "csv"

ENCODING = "utf-8"

SEPARADOR_CSV = ","


# ============================================================
# 6. UMBRALES GENERALES
# ============================================================

# Umbral de NAV utilizado durante las validaciones.
UMBRAL_NAV = 50.0

# Número mínimo de valores únicos para considerar
# una variable útil para análisis estadístico.
MIN_UNICOS = 2


# ============================================================
# 7. VARIABLES DEL SISTEMA
# ============================================================

FEATURES_SISTEMA = [
    {
        "columna": "cpu_usr",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de CPU utilizado por procesos de usuario",
    },
    {
        "columna": "cpu_sys",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de CPU utilizado por procesos del sistema",
    },
    {
        "columna": "cpu_idl",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de CPU inactiva",
    },
    {
        "columna": "cpu_wai",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de CPU esperando operaciones de E/S",
    },
    {
        "columna": "cpu_stl",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de CPU en espera por virtualización",
    },
    {
        "columna": "memory_percent",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de memoria utilizada",
    },
    {
        "columna": "memory_used_mb",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Memoria utilizada en MB",
    },
    {
        "columna": "memory_available_mb",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Memoria disponible en MB",
    },
    {
        "columna": "disk_read_per_sec",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Lecturas de disco por segundo",
    },
    {
        "columna": "disk_write_per_sec",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Escrituras de disco por segundo",
    },
    {
        "columna": "net_send_per_sec",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Bytes enviados por segundo",
    },
    {
        "columna": "net_recv_per_sec",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Bytes recibidos por segundo",
    },
    {
        "columna": "load1",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Carga promedio del sistema durante 1 minuto",
    },
    {
        "columna": "load5",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Carga promedio del sistema durante 5 minutos",
    },
    {
        "columna": "load15",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Carga promedio del sistema durante 15 minutos",
    },
]


# ============================================================
# 8. VARIABLES DE SESIONES
# ============================================================

FEATURES_SESIONES = [
    {
        "columna": "active_sessions",
        "fuente": "metrics",
        "dominio": "sesiones",
        "tipo": "numerica",
        "descripcion": "Número de sesiones activas",
    },
    {
        "columna": "active_requests",
        "fuente": "metrics",
        "dominio": "sesiones",
        "tipo": "numerica",
        "descripcion": "Número de solicitudes activas",
    },
    {
        "columna": "long_queries",
        "fuente": "metrics",
        "dominio": "sesiones",
        "tipo": "numerica",
        "descripcion": "Cantidad de consultas de larga duración",
    },
    {
        "columna": "long_transactions",
        "fuente": "metrics",
        "dominio": "sesiones",
        "tipo": "numerica",
        "descripcion": "Cantidad de transacciones de larga duración",
    },
    {
        "columna": "idle_sessions",
        "fuente": "metrics",
        "dominio": "sesiones",
        "tipo": "numerica",
        "descripcion": "Sesiones inactivas",
    },
]


# ============================================================
# 9. VARIABLES DE BLOQUEOS
# ============================================================

FEATURES_LOCKS = [
    {
        "columna": "lock_waits",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Cantidad de esperas por bloqueos",
    },
    {
        "columna": "total_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Cantidad total de bloqueos",
    },
    {
        "columna": "deadlocks_per_sec",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Deadlocks por segundo",
    },
    {
        "columna": "venta_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a venta",
    },
    {
        "columna": "detalle_venta_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a detalle de venta",
    },
    {
        "columna": "inventario_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a inventario",
    },
    {
        "columna": "kardex_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a kardex",
    },
    {
        "columna": "caja_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a caja",
    },
    {
        "columna": "movimiento_caja_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a movimientos de caja",
    },
    {
        "columna": "auditoria_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a auditoría",
    },
]


# ============================================================
# 10. VARIABLES DE BUFFER / SQL SERVER
# ============================================================

FEATURES_BUFFER = [
    {
        "columna": "transactions_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Transacciones por segundo",
    },
    {
        "columna": "total_reads",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Lecturas totales",
    },
    {
        "columna": "total_writes",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Escrituras totales",
    },
    {
        "columna": "page_life_expectancy",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Page Life Expectancy",
    },
    {
        "columna": "buffer_cache_hit_ratio",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Ratio de aciertos de caché del buffer",
    },
    {
        "columna": "page_reads_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Lecturas de páginas por segundo",
    },
    {
        "columna": "page_writes_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Escrituras de páginas por segundo",
    },
    {
        "columna": "rollbacks_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Rollbacks por segundo",
    },
    {
        "columna": "batch_requests_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Solicitudes batch por segundo",
    },
    {
        "columna": "sql_compilations_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Compilaciones SQL por segundo",
    },
]


# ============================================================
# 11. VARIABLES DE API
# ============================================================

FEATURES_API = [
    {
        "columna": "api_status",
        "fuente": "metrics",
        "dominio": "api",
        "tipo": "categorica",
        "descripcion": "Estado de la API",
    },
    {
        "columna": "api_latency_ms",
        "fuente": "metrics",
        "dominio": "api",
        "tipo": "numerica",
        "descripcion": "Latencia de la API en milisegundos",
    },
    {
        "columna": "products_count",
        "fuente": "metrics",
        "dominio": "api",
        "tipo": "numerica",
        "descripcion": "Cantidad de productos procesados",
    },
    {
        "columna": "sales_count",
        "fuente": "metrics",
        "dominio": "api",
        "tipo": "numerica",
        "descripcion": "Cantidad de ventas procesadas",
    },
]


# ============================================================
# 12. VARIABLES DE EVENTOS
# ============================================================

FEATURES_EVENTOS = [
    {
        "columna": "events_login_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos de login",
    },
    {
        "columna": "events_logout_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos de logout",
    },
    {
        "columna": "events_batch_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos batch",
    },
    {
        "columna": "events_lock_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos de bloqueo",
    },
    {
        "columna": "events_wait_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos de espera",
    },
    {
        "columna": "duration_max_ms",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Duración máxima de consultas",
    },
    {
        "columna": "duration_avg_ms",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Duración promedio de consultas",
    },
    {
        "columna": "query_duration_max_ms",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Duración máxima registrada para consultas",
    },
    {
        "columna": "query_duration_avg_ms",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Duración promedio registrada para consultas",
    },
    {
        "columna": "cpu_time_sum_ms",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Tiempo total de CPU utilizado",
    },
    {
        "columna": "logical_reads_sum",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Lecturas lógicas acumuladas",
    },
    {
        "columna": "writes_sum",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Escrituras acumuladas",
    },
    {
        "columna": "wait_lck_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Esperas asociadas a locks",
    },
    {
        "columna": "wait_io_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Esperas asociadas a operaciones de E/S",
    },
    {
        "columna": "wait_log_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Esperas asociadas al log",
    },
    {
        "columna": "distinct_sessions_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de sesiones distintas",
    },
    {
        "columna": "cpu_total",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "CPU total utilizada",
    },
    {
        "columna": "query_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de consultas",
    },
    {
        "columna": "wait_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de esperas",
    },
    {
        "columna": "lock_event_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos de bloqueo",
    },
    {
        "columna": "error_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de errores registrados",
    },
    {
        "columna": "requests_per_session",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Solicitudes promedio por sesión",
    },
]


# ============================================================
# 13. VARIABLES DE CONFIGURACIÓN DE SQL SERVER
# ============================================================

FEATURES_SETTINGS = [
    {
        "columna": "max_server_memory",
        "fuente": "metrics",
        "dominio": "configuracion",
        "tipo": "numerica",
        "descripcion": "Memoria máxima configurada para SQL Server",
    },
    {
        "columna": "user_connections_setting",
        "fuente": "metrics",
        "dominio": "configuracion",
        "tipo": "numerica",
        "descripcion": "Máximo de conexiones de usuario configuradas",
    },
    {
        "columna": "cost_threshold",
        "fuente": "metrics",
        "dominio": "configuracion",
        "tipo": "numerica",
        "descripcion": "Cost Threshold for Parallelism",
    },
]


# ============================================================
# 14. VARIABLES DE LOGS
# ============================================================

FEATURES_LOGS = [
    {
        "columna": "log_error_count",
        "fuente": "sqlserver_logs",
        "dominio": "logs",
        "tipo": "numerica",
        "descripcion": "Cantidad de errores registrados en SQL Server",
    },
    {
        "columna": "log_warning_count",
        "fuente": "sqlserver_logs",
        "dominio": "logs",
        "tipo": "numerica",
        "descripcion": "Cantidad de advertencias registradas",
    },
    {
        "columna": "log_fatal_count",
        "fuente": "sqlserver_logs",
        "dominio": "logs",
        "tipo": "numerica",
        "descripcion": "Cantidad de errores críticos registrados",
    },
]


# ============================================================
# 15. VARIABLE DE TEXTO
# ============================================================

COLUMNA_TEXTO = {
    "columna": "sql_text",
    "fuente": "derivada",
    "dominio": "texto",
    "tipo": "texto",
    "descripcion": "SQL de la consulta más lenta",
}


# ============================================================
# 16. VARIABLES REDUNDANTES
# ============================================================

"""
Estas variables pueden conservarse durante la preparación
para fines de diagnóstico, pero no son necesarias como
variables principales del modelo.
"""

VARIABLES_REDUNDANTES = [
    "cpu_idl",
    "memory_used_mb",
    "memory_available_mb",
    "load5",
    "load15",
    "idle_sessions",
    "cpu_total",
    "requests_per_session",
    "query_duration_max_ms",
    "query_duration_avg_ms",
]


# ============================================================
# 17. VARIABLES QUE REQUIEREN CORRECCIÓN
# ============================================================

"""
Estas métricas son contadores y requieren cálculo correcto
de delta por intervalo antes de utilizarse directamente
como variables de tasa.
"""

VARIABLES_REQUIEREN_CORRECCION = [
    "page_reads_per_sec",
    "page_writes_per_sec",
    "rollbacks_per_sec",
    "batch_requests_per_sec",
    "sql_compilations_per_sec",
]


# ============================================================
# 18. MEDICIONES NO CONFIABLES
# ============================================================

"""
buffer_cache_hit_ratio no debe utilizarse actualmente
porque el colector registra el cntr_value sin disponer
del contador base necesario para calcular correctamente
el porcentaje.
"""

EXCLUIR_MEDICION_CORRUPTA = [
    "buffer_cache_hit_ratio",
]


# ============================================================
# 19. VARIABLES PRINCIPALES PARA EL MODELO
# ============================================================

"""
Conjunto reducido de variables con mayor relación con
el rendimiento OLTP.

Estas son las variables candidatas para el modelo de
detección de anomalías.
"""

VARIABLES_PRINCIPALES = [
    "cpu_usr",
    "cpu_sys",
    "cpu_wai",
    "load1",

    "memory_percent",

    "page_life_expectancy",

    "disk_read_per_sec",
    "disk_write_per_sec",

    "total_reads",
    "total_writes",

    "active_sessions",
    "active_requests",
    "long_queries",
    "long_transactions",

    "lock_waits",
    "deadlocks_per_sec",

    "transactions_per_sec",

    "query_count",
    "duration_avg_ms",
    "duration_max_ms",

    "cpu_time_sum_ms",

    "wait_lck_count",
    "wait_io_count",
    "wait_log_count",

    "api_latency_ms",

    "error_count",
]


# ============================================================
# 20. VARIABLES DE DIAGNÓSTICO
# ============================================================

"""
Variables que pueden ayudar a explicar una anomalía,
pero que no necesariamente forman parte del conjunto
principal utilizado por el modelo.
"""

VARIABLES_DIAGNOSTICO = [
    "api_status",

    "products_count",
    "sales_count",

    "events_login_count",
    "events_logout_count",
    "events_batch_count",
    "events_lock_count",
    "events_wait_count",

    "logical_reads_sum",
    "writes_sum",
    "distinct_sessions_count",

    "wait_count",
    "lock_event_count",

    "log_error_count",
    "log_warning_count",
    "log_fatal_count",

    "max_server_memory",
    "user_connections_setting",
    "cost_threshold",

    "venta_locks",
    "detalle_venta_locks",
    "inventario_locks",
    "kardex_locks",
    "caja_locks",
    "movimiento_caja_locks",
    "auditoria_locks",
]


# ============================================================
# 21. INVENTARIO CANÓNICO DE VARIABLES
# ============================================================

_FEATURES = (
    FEATURES_SISTEMA
    + FEATURES_SESIONES
    + FEATURES_LOCKS
    + FEATURES_BUFFER
    + FEATURES_API
    + FEATURES_EVENTOS
    + FEATURES_SETTINGS
    + FEATURES_LOGS
)


# ============================================================
# 22. VARIABLES CANÓNICAS SELECCIONADAS
# ============================================================

FEATURES_SELECCIONADAS = [
    feature
    for feature in _FEATURES
    if feature["columna"] not in EXCLUIR_MEDICION_CORRUPTA
]


# ============================================================
# 23. COLUMNAS DE CONTEXTO
# ============================================================

"""
Estas columnas identifican la corrida/carga y permiten
mantener trazabilidad sin formar parte del modelo.
"""

COLUMNAS_CONTEXTO = [
    "run_name",
    "experiment_id",
]


# ============================================================
# 24. FUNCIONES AUXILIARES
# ============================================================

def columnas_features():
    """
    Devuelve las columnas de las variables canónicas.
    """
    return [
        feature["columna"]
        for feature in FEATURES_SELECCIONADAS
    ]


def columnas_principales():
    """
    Devuelve las columnas seleccionadas como variables
    principales para el modelo.
    """
    return VARIABLES_PRINCIPALES.copy()


def columnas_contexto():
    """
    Devuelve las columnas utilizadas para identificar
    y contextualizar cada corrida.
    """
    return COLUMNAS_CONTEXTO.copy()


def columnas_diagnostico():
    """
    Devuelve las variables utilizadas para diagnóstico.
    """
    return VARIABLES_DIAGNOSTICO.copy()


def columnas_redundantes():
    """
    Devuelve las variables consideradas redundantes.
    """
    return VARIABLES_REDUNDANTES.copy()


def columnas_requieren_correccion():
    """
    Devuelve las variables que requieren una transformación
    o cálculo correcto antes de utilizarse.
    """
    return VARIABLES_REQUIEREN_CORRECCION.copy()