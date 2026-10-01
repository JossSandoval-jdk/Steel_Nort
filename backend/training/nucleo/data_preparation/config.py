# ==========================================
# 1. RUTAS Y DIRECTORIOS
# ==========================================
from pathlib import Path
import os

BASE_PROYECTO = Path(__file__).resolve().parent
_OUTPUT_PROYECTO = Path(__file__).resolve().parents[3] / "training" / "output"
OUTPUT_BASE_DIR = Path(os.getenv("STEELNORT_OUTPUT_DIR", str(_OUTPUT_PROYECTO)))

DIR_DATASETS   = OUTPUT_BASE_DIR / "datasets"
DIR_INVENTARIO = OUTPUT_BASE_DIR / "inventario"
DIR_LIMPIO     = OUTPUT_BASE_DIR / "limpio"
DIR_INTEGRADO  = OUTPUT_BASE_DIR / "integrado"
DIR_BASELINE   = OUTPUT_BASE_DIR / "baseline"
DIR_ANOMALIAS  = OUTPUT_BASE_DIR / "anomalias"
DIR_MODELADO   = OUTPUT_BASE_DIR / "modelado"

# ==========================================
# 1.b MODO PRUEBA — carpetas v2
# ==========================================
# Descomenta estas 4 líneas para probar sin tocar las carpetas originales.
# Al terminar de validar, vuelve a comentarlas y todo vuelve a la normalidad.

DIR_INVENTARIO = OUTPUT_BASE_DIR / "inventario_v2"
DIR_LIMPIO     = OUTPUT_BASE_DIR / "limpio_v2"
DIR_INTEGRADO  = OUTPUT_BASE_DIR / "integrado_v2"
DIR_MODELADO   = OUTPUT_BASE_DIR / "modelado_v2"

# ==========================================
# 2. NOMBRES DE ARCHIVOS
# ==========================================
NOMBRE_METRICAS       = "metrics.log"
NOMBRE_EVENTS         = "events.log"
NOMBRE_SQLSERVER_LOGS = "sqlserver_logs.log"

NOMBRE_METRICAS_LIMPIO       = "metricas_limpio.csv"
NOMBRE_EVENTS_LIMPIO         = "eventos_limpio.csv"
NOMBRE_SQLSERVER_LOGS_LIMPIO = "sqlserver_logs_limpio.csv"

NOMBRE_TRANSFORMADO          = "datos_transformados.csv"

ARCHIVO_INVENTARIO        = "inventario_corridas.csv"
ARCHIVO_VARIABLES         = "variables_seleccionadas.csv"
ARCHIVO_DATASET_INTEGRADO = "dataset_steelnort_preparado.csv"
ARCHIVO_METADATA          = "metadata_transformaciones.json"
ARCHIVO_REPORTE_CALIDAD   = "reporte_calidad_datos.csv"

ENCODING      = "utf-8"
SEPARADOR_CSV = ","

# ==========================================
# 2.b CONSTANTES DE INVENTARIO
# ==========================================
NOMBRE_ORIGEN          = "origen.json"
TIPO_ORIGEN_LEGADO     = "legacy"
TIPO_ORIGEN_CONTENEDOR = "contenedor_sql"

ARCHIVOS_ENTRADA = [
    NOMBRE_METRICAS,
    NOMBRE_EVENTS,
    NOMBRE_SQLSERVER_LOGS,
]

DIRS_ARTEFACTO = {
    DIR_DATASETS.name,
    DIR_INVENTARIO.name,
    DIR_LIMPIO.name,
    DIR_INTEGRADO.name,
    DIR_MODELADO.name,
}

# ==========================================
# 3. CLASIFICACIÓN DE MÉTRICAS
# ==========================================
# Continuas: se imputan con mediana de la corrida
METRICAS_CONTINUAS = [
    "cpu_usr", "cpu_sys", "cpu_wai", "cpu_idl",
    "memory_percent", "memory_used_mb",
    "page_life_expectancy",
    "disk_read_per_sec", "disk_write_per_sec",
    "net_send_per_sec", "net_recv_per_sec",
    "load1",
    "active_sessions", "active_requests",
    "transactions_per_sec",
    "long_queries", "long_transactions",
    "api_latency_ms", "api_status",
]

# Contadores: se imputan con 0 (ausencia = sin evento)
METRICAS_CONTADOR = [
    "lock_waits", "total_locks", "deadlocks_per_sec",
    "venta_locks", "detalle_venta_locks",
    "inventario_locks", "kardex_locks",
    "caja_locks", "movimiento_caja_locks", "auditoria_locks",
    "products_count", "sales_count",
]

# Contadores acumulativos: requieren Δt
METRICAS_A_TASA = [
    "total_reads", "total_writes",
]

# Corruptas o no representativas: excluir siempre
EXCLUIR_MEDICION_CORRUPTA = [
    "buffer_cache_hit_ratio",   # siempre 100.0
    "database_size_mb",         # siempre 0
    "max_server_memory",        # aparece 1 vez
    "user_connections_setting", # aparece 1 vez
    "cost_threshold",           # aparece 1 vez
]

# Redundantes (alta correlación con otras): excluir del modelo
VARIABLES_REDUNDANTES = [
    "load5", "load15",
    "idle_sessions",
    "cpu_total",
    "requests_per_session",
    "memory_available_mb",
    "page_reads_per_sec", "page_writes_per_sec",
    "rollbacks_per_sec", "batch_requests_per_sec",
    "sql_compilations_per_sec",
]

# ==========================================
# 4. FEATURES DEL MODELO
# ==========================================
# Features que entran al Isolation Forest
FEATURES_MODELO = [
    # CPU
    "cpu_usr", "cpu_sys", "cpu_wai",
    # Memoria
    "memory_percent", "memory_used_mb", "page_life_expectancy",
    # Disco / red
    "disk_read_per_sec", "disk_write_per_sec",
    "net_send_per_sec", "net_recv_per_sec",
    # Carga
    "load1",
    # Sesiones
    "active_sessions", "active_requests",
    # Transacciones
    "transactions_per_sec",
    "long_queries", "long_transactions",
    # API (la señal clave)
    "api_latency_ms", "api_status",
    # Locks
    "lock_waits", "total_locks", "deadlocks_per_sec",
    # Eventos agregados (desde events.log)
    "events_login_count", "events_logout_count",
    "events_lock_acquired_count", "events_lock_released_count",
    "events_wait_count",
    "batch_count", "batch_duration_avg_ms", "batch_duration_max_ms",
    # Logs SQL Server (si aportan)
    "log_error_count", "log_fatal_count",
]

# ==========================================
# 5. TRATAMIENTO
# ==========================================
# Sin winsorización: Isolation Forest es invariante a outliers.
# Si en el futuro se quiere activar, se usa WINSORIZAR_ACTIVO.
WINSORIZAR_ACTIVO = os.getenv("STEELNORT_WINSORIZAR", "0") == "1"
WINSORIZAR_PCT    = float(os.getenv("STEELNORT_WINSORIZAR_PCT", "0.995"))

IMPUTAR_MEDIANA_CORRIDA = os.getenv("STEELNORT_IMPUTAR_MEDIANA", "1") == "1"

# Conversión de unidades para events.log
DURACION_EVENTOS_EN_MICROSEGUNDOS = True
UMBRAL_LONG_QUERY_MS       = 15000
UMBRAL_LONG_TRANSACTION_MS = 30000

# Umbral de locks / severidad
UMBRAL_LOCK_WAITS = 0

# ==========================================
# 6. MODELADO — ISOLATION FOREST
# ==========================================
IF_N_ESTIMATORS   = 100
IF_CONTAMINATION  = 0.05      # fijo, justificar en tesis
IF_RANDOM_STATE   = 42
IF_MAX_SAMPLES    = 256
# Umbral sobre decision_function. Si None, se usa el que da contamination.
IF_UMBRAL_ANOMALIA = None

# ==========================================
# 7. CONTEXTO Y VALIDACIÓN
# ==========================================
# Contexto: información que acompaña a la muestra pero NO entra al modelo
COLUMNAS_CONTEXTO = ["run_name", "experiment_id"]

# Etiqueta solo para evaluación post-hoc. NO usar en entrenamiento.
COLUMNA_VALIDACION = "es_carga_normal"

# ==========================================
# 8. CALIDAD DE DATOS
# ==========================================
# Warm-up: descartar las primeras N muestras de cada corrida
N_MUESTRAS_WARMUP = 1

# Criterios de calidad
CALIDAD_MIN_COMPLETITUD = 0.95
CALIDAD_MIN_CONSISTENCIA = 0.95
CALIDAD_MIN_VALIDEZ = 0.95

# ==========================================
# 9. CORRIDAS EXCLUIDAS DEL ENTRENAMIENTO
# ==========================================
# Corridas en baseline/ que NO son sanas (API colgada, entorno viejo, etc.)
CORRIDAS_NO_BASE_SANA = [
    "carga1", "carga2", "carga4",
    "10", "8", "carga7", "carga11", "carga18", "carga19", "carga20",
    "normal_baja_01", "normal_media_01",
    "normal_prueba_01", "normal_media_02",
]