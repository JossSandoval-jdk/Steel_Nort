"""
modelado_config.py
==================
Configuración del modelado en v2 (entrenamiento, reglas y pruebas).

Lee el dataset preparado por pipeline/ y escribe en output/modelado/.
"""

import os
from pathlib import Path


# ==========================================
# Rutas
# ==========================================
# Este archivo vive en app/tools/modelado/.
# parents[0] = modelado/, parents[1] = tools/.
OUTPUT_BASE = os.getenv(
    "STEELNORT_OUTPUT_DIR",
    str(Path(__file__).resolve().parents[1] / "output"),
)

# El pipeline escribe el dataset en output/preparado/.
DATASET_SET = os.getenv("STEELNORT_DATASET_SET", "preparado")
DATASET_ARCHIVO = os.getenv("STEELNORT_DATASET_FILE", "dataset_steelnort.parquet")
DATASET_PRINCIPALES = os.path.join(OUTPUT_BASE, DATASET_SET, DATASET_ARCHIVO)

MODELADO_SET = os.getenv("STEELNORT_MODELADO_SET", "modelado")
DIR_MODELADO = os.path.join(OUTPUT_BASE, MODELADO_SET)
DIR_CORRELACION = os.path.join(DIR_MODELADO, "correlacion")
DIR_DETECCION = os.path.join(DIR_MODELADO, "deteccion")
DIR_REGLAS = os.path.join(DIR_MODELADO, "reglas_motor")
DIR_CORRIDAS = OUTPUT_BASE

# Carpetas de salida: no son corridas.
CARPETAS_NO_CORRIDA = {"inventario", "preparado", "modelado", "datasets"}


# ==========================================
# Variables del modelo (las 25 que emite el detector)
# ==========================================
VARIABLES_MODELO = [
    "cpu_usr", "cpu_sys", "cpu_wai",
    "memory_percent", "memory_used_mb", "page_life_expectancy",
    "disk_read_per_sec", "disk_write_per_sec",
    "net_send_per_sec", "net_recv_per_sec",
    "load1",
    "active_sessions", "active_requests",
    "transactions_per_sec", "long_queries", "long_transactions",
    "api_latency_ms", "api_status",
    "lock_waits", "total_locks", "deadlocks_per_sec",
    "events_wait_count",
    "batch_count", "batch_duration_avg_ms", "batch_duration_max_ms",
]


# ==========================================
# Corridas excluidas de la línea base sana
# ==========================================
CORRIDAS_NO_BASE_SANA = [
    "carga1", "carga2", "carga4",
    "10", "8", "carga7", "carga11", "carga18", "carga19", "carga20",
    "normal_baja_01", "normal_media_01",
    "normal_prueba_01", "normal_media_02",
    "run1", "run2", "run4", "run7",
]


# ==========================================
# Parámetros
# ==========================================
VENTANA = 10
SEED = 42
UMBRAL_CORRELACION = 0.85
UMBRAL_CORRELACION_INDICADOR = 0.6
COLUMNAS_CONTEXTO = ["timestamp", "run_name", "experiment_id", "carpeta", "etiqueta_manual"]

# Umbrales del motor de reglas R1-R7
UMBRAL_DURATION_MS_ALTO = 500
TOLERANCIA_CPU_DURATION = 0.10
UMBRAL_DESVIO_LOGICAL_READS = 1.5
UMBRAL_DURACION_LENTA_MS = 800
UMBRAL_CPU_ALTO_MS = 80.0
UMBRAL_CPU_CRITICO_MS = 90.0
BUFFER_CACHE_HIT_RATIO_DESEABLE = 90.0


# ==========================================
# Utilidades
# ==========================================
def log(msg):
    print(f"[MODELADO] {msg}", flush=True)


def corridas_anomalia(raiz=None):
    """Corridas de fallo: subcarpetas de anomalias/ con metrics.log."""
    raiz = Path(raiz) if raiz else Path(OUTPUT_BASE)
    dir_anom = raiz / "anomalias"
    if not dir_anom.is_dir():
        return []
    return sorted(
        d for d in os.listdir(dir_anom)
        if (dir_anom / d / "metrics.log").is_file()
    )


def corridas_entrenamiento(runs):
    """Corridas normales para entrenar: fuera anomalías y no-sanas."""
    anom = set(corridas_anomalia())
    no_sana = set(CORRIDAS_NO_BASE_SANA)
    return sorted(r for r in set(runs) if r not in anom and r not in no_sana)


def ruta_corrida(raiz, corrida):
    """Carpeta de una corrida en anomalias/, baseline/ o raíz."""
    raiz = Path(raiz) if raiz else Path(OUTPUT_BASE)
    for grupo in ("anomalias", "baseline"):
        p = raiz / grupo / corrida
        if p.is_dir():
            return str(p)
    return str(raiz / corrida)
