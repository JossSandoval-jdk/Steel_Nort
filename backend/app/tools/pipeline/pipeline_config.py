"""
pipeline_config.py
==================
Configuración y utilidades compartidas del pipeline.

Un solo archivo: rutas, nombres, clasificación de métricas,
features del modelo, umbrales y funciones auxiliares.
"""

import json
import os
from pathlib import Path


# ==========================================
# 1. RUTAS
# ==========================================
# Este archivo vive en tools/pipeline/pipeline_config.py
# parents[0] = pipeline/, parents[1] = tools/
BASE_PROYECTO = Path(__file__).resolve().parents[1]
OUTPUT_BASE_DIR = Path(
    os.getenv("STEELNORT_OUTPUT_DIR", str(BASE_PROYECTO / "output"))
)

DIR_INVENTARIO = OUTPUT_BASE_DIR / "inventario"
DIR_PREPARADO  = OUTPUT_BASE_DIR / "preparado"
DIR_BASELINE   = OUTPUT_BASE_DIR / "baseline"
DIR_ANOMALIAS  = OUTPUT_BASE_DIR / "anomalias"
DIR_MODELADO   = OUTPUT_BASE_DIR / "modelado"


# ==========================================
# 2. NOMBRES DE ARCHIVOS
# ==========================================
# Entrada (logs crudos)
NOMBRE_METRICAS       = "metrics.log"
NOMBRE_EVENTS         = "events.log"
NOMBRE_SQLSERVER_LOGS = "sqlserver_logs.log"

# Inventario (3 CSV, documentan la entrada)
ARCHIVO_INVENTARIO = "inventario_corridas.csv"
ARCHIVO_COBERTURA  = "cobertura_fechas.csv"
ARCHIVO_VARIABLES  = "variables_seleccionadas.csv"

# Preparado (dataset final + metadata + calidad)
ARCHIVO_DATASET    = "dataset_steelnort.parquet"
ARCHIVO_METADATA   = "metadata.json"
ARCHIVO_CALIDAD    = "reporte_calidad.csv"

ENCODING = "utf-8"

ARCHIVOS_ENTRADA = [NOMBRE_METRICAS, NOMBRE_EVENTS, NOMBRE_SQLSERVER_LOGS]

DIRS_ARTEFACTO = {
    DIR_INVENTARIO.name,
    DIR_PREPARADO.name,
    DIR_MODELADO.name,
}


# ==========================================
# 3. ORIGEN DE LAS CORRIDAS
# ==========================================
NOMBRE_ORIGEN          = "origen.json"
TIPO_ORIGEN_LEGADO     = "legacy"
TIPO_ORIGEN_CONTENEDOR = "contenedor_sql"


def escribir_origen(ruta_corrida, tipo=TIPO_ORIGEN_CONTENEDOR, **campos):
    """Escribe origen.json con la procedencia de la corrida."""
    ruta = Path(ruta_corrida)
    ruta.mkdir(parents=True, exist_ok=True)
    origen = {"origen": tipo, **campos}
    with open(ruta / NOMBRE_ORIGEN, "w", encoding="utf-8") as f:
        json.dump(origen, f, ensure_ascii=False, indent=2)


# ==========================================
# 4. CLASIFICACIÓN DE MÉTRICAS
# ==========================================
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

METRICAS_CONTADOR = [
    "lock_waits", "total_locks", "deadlocks_per_sec",
    "venta_locks", "detalle_venta_locks",
    "inventario_locks", "kardex_locks",
    "caja_locks", "movimiento_caja_locks", "auditoria_locks",
    "products_count", "sales_count",
]

# Contadores acumulativos: se convierten a tasa (Δ/Δt)
METRICAS_A_TASA = ["total_reads", "total_writes"]

# Corruptas o no representativas: se excluyen siempre
EXCLUIR_MEDICION_CORRUPTA = [
    "buffer_cache_hit_ratio",
    "database_size_mb",
    "max_server_memory",
    "user_connections_setting",
    "cost_threshold",
]

# Redundantes (alta correlación): fuera del modelo
VARIABLES_REDUNDANTES = [
    "load5", "load15",
    "idle_sessions", "cpu_total",
    "requests_per_session",
    "memory_available_mb",
    "page_reads_per_sec", "page_writes_per_sec",
    "rollbacks_per_sec", "batch_requests_per_sec",
    "sql_compilations_per_sec",
]


# ==========================================
# 5. FEATURES DEL MODELO
# ==========================================
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
    "transactions_per_sec", "long_queries", "long_transactions",
    # API (señal clave)
    "api_latency_ms", "api_status",
    # Locks
    "lock_waits", "total_locks", "deadlocks_per_sec",
    # Eventos agregados
    "events_login_count", "events_logout_count",
    "events_lock_acquired_count", "events_lock_released_count",
    "events_wait_count",
    "batch_count", "batch_duration_avg_ms", "batch_duration_max_ms",
    # SQL Server
    "log_error_count", "log_fatal_count",
]


# ==========================================
# 6. TRATAMIENTO
# ==========================================
WINSORIZAR_ACTIVO = os.getenv("STEELNORT_WINSORIZAR", "0") == "1"
WINSORIZAR_PCT    = float(os.getenv("STEELNORT_WINSORIZAR_PCT", "0.995"))
IMPUTAR_MEDIANA_CORRIDA = os.getenv("STEELNORT_IMPUTAR_MEDIANA", "1") == "1"

# events.log reporta duration en microsegundos
DURACION_EVENTOS_EN_MICROSEGUNDOS = True


# ==========================================
# 7. MODELADO — ISOLATION FOREST
# ==========================================
IF_N_ESTIMATORS    = 100
IF_CONTAMINATION   = 0.05
IF_RANDOM_STATE    = 42
IF_MAX_SAMPLES     = 256
IF_UMBRAL_ANOMALIA = None


# ==========================================
# 8. CONTEXTO Y VALIDACIÓN
# ==========================================
COLUMNAS_CONTEXTO  = ["run_name", "experiment_id"]
COLUMNA_VALIDACION = "es_carga_normal"


# ==========================================
# 9. CALIDAD DE DATOS
# ==========================================
N_MUESTRAS_WARMUP = 1

CALIDAD_MIN_COMPLETITUD   = 0.95
CALIDAD_MIN_CONSISTENCIA  = 0.95
CALIDAD_MIN_VALIDEZ       = 0.95
CALIDAD_MIN_INDICE        = 0.95
CALIDAD_MAX_NULOS_COLUMNA = 0.5

RANGOS_VALIDEZ = {
    "cpu_usr": (0, 100), "cpu_sys": (0, 100), "cpu_wai": (0, 100),
    "cpu_idl": (0, 100),
    "memory_percent": (0, 100),
    "memory_used_mb": (0, 1e6), "memory_available_mb": (0, 1e6),
    "load1": (0, 1000), "load5": (0, 1000), "load15": (0, 1000),
    "api_latency_ms": (0, 60000),
    "active_sessions": (0, 10000), "active_requests": (0, 10000),
    "idle_sessions": (0, 10000),
    "transactions_per_sec": (0, 1e6),
    "long_queries": (0, 100000), "long_transactions": (0, 100000),
    "lock_waits": (0, 1e9), "total_locks": (0, 1e12),
    "deadlocks_per_sec": (0, 1e6),
    "disk_read_per_sec": (0, 1e12), "disk_write_per_sec": (0, 1e12),
    "net_send_per_sec": (0, 1e12), "net_recv_per_sec": (0, 1e12),
    "page_reads_per_sec": (0, 1e12), "page_writes_per_sec": (0, 1e12),
    "page_life_expectancy": (0, 1e9),
    "rollbacks_per_sec": (0, 1e6), "sql_compilations_per_sec": (0, 1e6),
}

# Corridas en baseline/ que NO son sanas (API colgada, entorno viejo, etc.)
CORRIDAS_NO_BASE_SANA = [
    "carga1", "carga2", "carga4",
    "10", "8", "carga7", "carga11", "carga18", "carga19", "carga20",
    "normal_baja_01", "normal_media_01",
    "normal_prueba_01", "normal_media_02",
]


# ==========================================
# 10. UTILIDADES COMPARTIDAS
# ==========================================
def log(msg):
    """Log simple con prefijo."""
    print(f"[UTILS] {msg}", flush=True)


def _subcarpetas_con_logs(carpeta):
    """Subcarpetas que contienen al menos un log de entrada."""
    if not os.path.isdir(carpeta):
        return []
    return [
        d for d in sorted(os.listdir(carpeta))
        if os.path.isdir(os.path.join(carpeta, d))
        and any(
            os.path.isfile(os.path.join(carpeta, d, f))
            for f in ARCHIVOS_ENTRADA
        )
    ]


def descubrir_corridas(raiz=None):
    """
    Devuelve {corrida: {grupo, ruta}}.

    Busca en baseline/, anomalias/ y cualquier subcarpeta suelta
    de output/ que contenga logs.
    """
    raiz = Path(raiz) if raiz else OUTPUT_BASE_DIR
    corridas = {}

    def _marcar(carpeta, grupo):
        for d in _subcarpetas_con_logs(carpeta):
            corridas.setdefault(
                d, {"grupo": grupo, "ruta": str(Path(carpeta) / d)}
            )

    _marcar(DIR_ANOMALIAS, "anomalias")
    _marcar(DIR_BASELINE, "baseline")

    # Corridas sueltas en output/ (grupo "raiz")
    for d in sorted(os.listdir(raiz)):
        p = raiz / d
        if not p.is_dir():
            continue
        if d in DIRS_ARTEFACTO or d in ("anomalias", "baseline"):
            continue
        if _subcarpetas_con_logs(p):
            _marcar(p, "legacy")
        elif any(os.path.isfile(p / f) for f in ARCHIVOS_ENTRADA):
            corridas.setdefault(d, {"grupo": "raiz", "ruta": str(p)})

    return corridas


def leer_origen(ruta_corrida, grupo=None):
    """Lee origen.json; si no existe, infiere es_carga_normal del grupo."""
    origen = {"origen": TIPO_ORIGEN_LEGADO}
    p = Path(ruta_corrida) / NOMBRE_ORIGEN
    if p.is_file():
        try:
            with open(p, encoding="utf-8") as f:
                origen.update(json.load(f))
        except Exception as e:
            log(f"Advertencia leyendo {p}: {e}")

    if "es_carga_normal" not in origen and grupo:
        origen["es_carga_normal"] = (grupo == "baseline")
    return origen


# ==========================================
# 11. COMPATIBILIDAD DE IMPORTACIÓN
# ==========================================
# Los scripts del pipeline hacen "from pipeline_config import config, utils".
# config = este módulo (constantes); utils = este módulo (helpers).
import sys as _sys

config = _sys.modules[__name__]
utils = _sys.modules[__name__]