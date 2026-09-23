"""
config.py
=========

Configuración del módulo de modelado para detección de
anomalías OLTP en SteelNort.

Reutiliza el dataset final preparado por data_preparation
(dataset_carga_principales.csv) y escribe sus resultados en
<OUTPUT>/modelado/.
"""

import os

from pathlib import Path

OUTPUT_BASE = os.getenv(
    "STEELNORT_OUTPUT_DIR",
    str(
        Path(__file__).resolve().parents[3]
        / "training" / "output"
    )
)

_CORRIDAS_TRAIN_DEF = os.getenv("STEELNORT_CORRIDAS_TRAIN", "carga7,carga8")

CORRIDAS_ENTRENAMIENTO = [
    c.strip() for c in _CORRIDAS_TRAIN_DEF.split(",") if c.strip()
]

# Corridas que NO son línea base sana aunque no estén en anomalias/.
# Son capturas con la API COLGADA (api_status=0, latencia ~5007ms,
# load1 ~9.5): el mismo patrón de fallo que queremos detectar. Si entran
# al train, el modelo aprende que "el fallo es normal" y el FPR explota
# (medido: 69.6% medio en q10). Se excluyen del entrenamiento.
CORRIDAS_NO_BASE_SANA = [
    "carga1",
    "carga2",
    "carga4",
]

# ---------------------------------------------------------------------------
# Poda del conjunto canónico de data_preparation (VARIABLES_PRINCIPALES).
# El DATASET conserva las 22 columnas para diagnóstico, pero EL MODELO usa
# SOLO estas 19 variables. Se excluyen por redundancia comprobada:
#   - cpu_idl          : complemento de cpu_usr (r=-0.78)
#   - memory_used_mb   : complemento de memory_available_mb (r=-0.75)
#   - duration_max_ms  : idéntica a duration_avg_ms (r=1.00)
# ---------------------------------------------------------------------------
VARIABLES_MODELO = [
    "cpu_usr",
    "cpu_sys",
    "cpu_wai",
    "memory_available_mb",
    "page_life_expectancy",
    "disk_read_per_sec",
    "disk_write_per_sec",
    "total_reads",
    "total_writes",
    "active_sessions",
    "active_requests",
    "transactions_per_sec",
    "long_queries",
    "long_transactions",
    "duration_avg_ms",
    "cpu_time_sum_ms",
    "api_latency_ms",
    "api_status",
    "load1",
]

def _carpetas_con(raiz, archivo):
    """Subcarpetas de raiz que contienen 'archivo'."""
    if not os.path.isdir(raiz):
        return []
    return [
        nombre for nombre in os.listdir(raiz)
        if os.path.isdir(os.path.join(raiz, nombre))
        and os.path.isfile(os.path.join(raiz, nombre, archivo))
    ]

def corridas_anomalia(raiz=None):
    """Carpetas que son corridas de anomalias.

    Por definición TODAS las subcarpetas de anomalias/ con metrics.log
    son corridas de fallo (test), tengan o no anomalias_timeline.csv
    (el timeline puede faltar en capturas incompletas). Se añaden por
    compatibilidad las carpetas con anomalias_timeline.csv directas en
    la raiz. Se ordenan por su timeline más reciente (o mtime de carpeta).
    """
    raiz = Path(raiz) if raiz else OUTPUT_BASE
    dir_anom = os.path.join(raiz, "anomalias")
    carpetas = _carpetas_con(dir_anom, "metrics.log")
    for n in _carpetas_con(raiz, "anomalias_timeline.csv"):
        if n not in carpetas:
            carpetas.append(n)
    carpetas = sorted(set(carpetas))

    def _mtime(n):
        tl = os.path.join(dir_anom, n, "anomalias_timeline.csv")
        if os.path.isfile(tl):
            return os.path.getmtime(tl)
        tl2 = os.path.join(raiz, n, "anomalias_timeline.csv")
        if os.path.isfile(tl2):
            return os.path.getmtime(tl2)
        return os.path.getmtime(os.path.join(dir_anom, n))

    carpetas.sort(key=_mtime, reverse=True)
    return carpetas

def ruta_corrida(raiz, corrida):
    """Ruta de la carpeta de una corrida (busca en anomalias/, baseline/
    y raiz)."""
    raiz = Path(raiz) if raiz else OUTPUT_BASE
    for grupo in ("anomalias", "baseline"):
        p = raiz / grupo / corrida
        if p.is_dir():
            return str(p)
    return str(raiz / corrida)

DATASET_PRINCIPALES = os.path.join(
    OUTPUT_BASE,
    "integrado",
    "dataset_carga_principales.csv"
)

DIR_MODELADO = os.path.join(
    OUTPUT_BASE,
    "modelado"
)

DIR_CORRELACION = os.path.join(
    DIR_MODELADO,
    "correlacion"
)

DIR_DETECCION = os.path.join(
    DIR_MODELADO,
    "deteccion"
)

DIR_CORRIDAS = OUTPUT_BASE

CARPETAS_NO_CORRIDA = {
    "limpio",
    "integrado",
    "inventario",
    "modelado",
    "datasets",
}

DIR_REGLAS = os.path.join(
    DIR_MODELADO,
    "reglas_motor"
)

VENTANA = 10

UMBRAL_CORRELACION = 0.85

# Normalización RELATIVA por corrida (mediana/MAD de la propia corrida).
# DESACTIVADA de forma deliberada: en corridas donde la inyección de fallos
# cubre toda la corrida, el baseline interno YA es el fallo, así que la
# anomalía se expresa como desviación ~0 y el modelo no la ve (TPR ~2%).
# Además la API de producción (app/ml/detector.py) puntúa sin esta
# transformación; entrenar sin ella mantiene entrenamiento == scoring.
NORMALIZACION_RELATIVA = False

COLUMNAS_CONTEXTO = [
    "timestamp",      # etiqueta temporal (contexto, no es variable)
    "run_name",       # a qué corrida pertenece el dato
    "experiment_id",  # id del experimento de captura
]

SEED = 42

UMBRAL_DURATION_MS_ALTO = 500

TOLERANCIA_CPU_DURATION = 0.10

UMBRAL_DESVIO_LOGICAL_READS = 1.5

UMBRAL_DURACION_LENTA_MS = 800

UMBRAL_CPU_ALTO_MS = 80.0
UMBRAL_CPU_CRITICO_MS = 90.0

BUFFER_CACHE_HIT_RATIO_DESEABLE = 90.0
