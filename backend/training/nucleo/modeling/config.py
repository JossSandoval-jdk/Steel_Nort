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


OUTPUT_BASE = os.getenv(
    "STEELNORT_OUTPUT_DIR",
    r"D:\Steel_Nort\output"
)

# ---------------------------------------------------------------------
# DATASET DE ENTRADA
# ---------------------------------------------------------------------
DATASET_PRINCIPALES = os.path.join(
    OUTPUT_BASE,
    "integrado",
    "dataset_carga_principales.csv"
)

# ---------------------------------------------------------------------
# DIRECTORIOS DE SALIDA
# ---------------------------------------------------------------------
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

NORMALIZACION_RELATIVA = True

FRACCION_TRAIN = 0.70
FRACCION_TEST = 0.30

COLUMNAS_CONTEXTO = [
    "timestamp",
    "run_name",
    "experiment_id",
]

SEED = 42

# ---------------------------------------------------------------
# PARÁMETROS DE LAS REGLAS DE MOTOR (R1-R7)
# ---------------------------------------------------------------
UMBRAL_DURATION_MS_ALTO = 500

TOLERANCIA_CPU_DURATION = 0.10

UMBRAL_DESVIO_LOGICAL_READS = 1.5

UMBRAL_DURACION_LENTA_MS = 800

# Umbral mínimo de compilaciones por segundo para disparar sospecha en R7
UMBRAL_COMPILACIONES_POR_SEG = 50.0

# ---------------------------------------------------------------------
# UMBRALES DE MÉTRICAS PARA CORROBORACIÓN DE REGLAS
# (referencias explícitas de Microsoft Learn)
# ---------------------------------------------------------------------
# Processor: % Processor Time — Corregido sufijo a _PORCENTAJE
UMBRAL_CPU_ALTO_PORCENTAJE = 80.0
UMBRAL_CPU_CRITICO_PORCENTAJE = 90.0

# Buffer Manager: Buffer cache hit ratio — Microsoft: >= 90 es deseable.
BUFFER_CACHE_HIT_RATIO_DESEABLE = 90.0