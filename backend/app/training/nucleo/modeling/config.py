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

# Raiz de salida del pipeline DENTRO del proyecto web
# (backend/training/output). Se puede redefinir con STEELNORT_OUTPUT_DIR.
# NOTA: config.py vive en backend/app/training/nucleo/modeling, así que
# la raiz de datos es backend/training/output.
OUTPUT_BASE = os.getenv(
    "STEELNORT_OUTPUT_DIR",
    str(
        Path(__file__).resolve().parents[4]
        / "training" / "output"
    )
)

# ---------------------------------------------------------------------
# CORRIDAS DE ENTRENAMIENTO (SOLO NORMALES) Y CORRIDA DE ANOMALIAS
# ---------------------------------------------------------------------
# El modelo se entrena EXCLUSIVAMENTE con corridas normales de carga.
# La corrida de anomalías (la que contiene anomalias_timeline.csv) NUNCA
# entra en el entrenamiento: se usa solo como test para detección.
#
#   STEELNORT_CORRIDAS_TRAIN: lista separada por comas que fija qué
#   corridas normales entrenan (por defecto carga7 y carga8).
_CORRIDAS_TRAIN_DEF = os.getenv("STEELNORT_CORRIDAS_TRAIN", "carga7,carga8")

CORRIDAS_ENTRENAMIENTO = [
    c.strip() for c in _CORRIDAS_TRAIN_DEF.split(",") if c.strip()
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
    """Carpetas que son corridas de anomalias (tienen
    anomalias_timeline.csv). Se buscan dentro de anomalias/ y por
    compatibilidad también en la raiz. Se ordenan por su timeline más
    reciente."""
    raiz = Path(raiz) if raiz else OUTPUT_BASE
    carpetas = _carpetas_con(
        os.path.join(raiz, "anomalias"), "anomalias_timeline.csv")
    carpetas += _carpetas_con(raiz, "anomalias_timeline.csv")
    carpetas = sorted(set(carpetas))
    carpetas.sort(
        key=lambda n: os.path.getmtime(
            os.path.join(raiz, "anomalias", n, "anomalias_timeline.csv"))
        if os.path.isfile(
            os.path.join(raiz, "anomalias", n, "anomalias_timeline.csv"))
        else os.path.getmtime(
            os.path.join(raiz, n, "anomalias_timeline.csv")),
        reverse=True,
    )
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


def corrida_anomalia_principal(raiz=None):
    """La corrida de anomalías a diagnosticar (si hay varias, la más
    reciente). Devuelve None si no existe ninguna."""
    carp = corridas_anomalia(raiz)
    return carp[0] if carp else None

# ---------------------------------------------------------------------
# DATASET DE ENTRADA
# ---------------------------------------------------------------------
# Es el archivo final que produce el pipeline de data_preparation
# (00 → 06): una fila por instante de muestreo, solo variables
# principales, sin NaN. Aquí lo consumimos como "fuente de verdad".
DATASET_PRINCIPALES = os.path.join(
    OUTPUT_BASE,
    "integrado",
    "dataset_carga_principales.csv"
)

# ---------------------------------------------------------------------
# DIRECTORIOS DE SALIDA
# ---------------------------------------------------------------------
# Todo lo que genera este módulo cae dentro de <OUTPUT>/modelado/
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

# Directorio donde viven los logs crudos de cada corrida
# (output/carga1, output/carga2, ...). Allí están los events.log
# con TODAS las columnas (incluidas blocking_session_id,
# signal_wait_time_ms y wait_resource en las capturas nuevas).
DIR_CORRIDAS = OUTPUT_BASE

# Subcarpetas de OUTPUT_BASE que NO son corridas reales (artefactos
# de salida del pipeline/modelado) y deben ignorarse al buscar
# events.log.
CARPETAS_NO_CORRIDA = {
    "limpio",
    "integrado",
    "inventario",
    "modelado",
    "datasets",
}

# Directorio de salida de las reglas de motor.
DIR_REGLAS = os.path.join(
    DIR_MODELADO,
    "reglas_motor"
)

# Ventana temporal de muestras por observación (como DBPA: 10).
VENTANA = 10

# Umbral de correlación para considerar variables redundantes.
UMBRAL_CORRELACION = 0.85

# Normalización RELATIVA por corrida: cada corrida define su
# propio baseline (media/desv. por variable) y las muestras se
# expresan como desviaciones internas. Elimina la deriva de
# entorno entre corridas (carga4 vs carga1-3).
# ---------------------------------------------------------------------
# NORMALIZACIÓN RELATIVA (el paso que elimina la deriva de entorno)
# ---------------------------------------------------------------------
# False → el modelo aprende niveles absolutos (sensible a cambios de
# entorno entre corridas). True → cada corrida se mide contra su propio
# baseline interno y solo se detectan desviaciones dentro de la corrida.
NORMALIZACION_RELATIVA = True

# ---------------------------------------------------------------------
# SPLIT TRAIN / TEST POR MUESTRAS
# ---------------------------------------------------------------------
# Se divide el 70% de TODAS las muestras para entrenamiento y 30% para
# prueba, mezclando aleatoriamente para maximizar la representatividad.
# Split por corrida completa: se eliminó a petición del usuario.
FRACCION_TRAIN = 0.70
FRACCION_TEST = 0.30

COLUMNAS_CONTEXTO = [
    "timestamp",      # etiqueta temporal (contexto, no es variable)
    "run_name",       # a qué corrida pertenece el dato
    "experiment_id",  # id del experimento de captura
]

# Reproducibilidad: misma semilla ⇒ mismos árboles ⇒ mismos resultados.
SEED = 42

# ---------------------------------------------------------------
# PARÁMETROS DE LAS REGLAS DE MOTOR (R1-R7)
# ---------------------------------------------------------------
# Umbral (ms) a partir del cual una espera se considera "alta".
# Se usa en R1 (I/O con duration alto) y como cota de referencia.
UMBRAL_DURATION_MS_ALTO = 500

# Umbral (ms) para considerar que cpu_time ≈ duration (R3).
# Si cpu_time >= duration * (1 - TOL) ya no está esperando casi nada.
TOLERANCIA_CPU_DURATION = 0.10

# Fracción del historial de la misma consulta por encima de la cual
# se dispara R7 (logical_reads muy superior a su media histórica).
UMBRAL_DESVIO_LOGICAL_READS = 1.5

# Duración mínima (ms) para que una consulta sea "lenta" en R7/R1.
UMBRAL_DURACION_LENTA_MS = 800

# ---------------------------------------------------------------------
# UMBRALES DE MÉTRICAS PARA CORROBORACIÓN DE REGLAS
# (referencias explícitas de Microsoft Learn)
# ---------------------------------------------------------------------
# Processor: % Processor Time — señal de necesitar más CPU/procesadores
# si se mantiene sostenido en 80-90% (Microsoft).
UMBRAL_CPU_ALTO_MS = 80.0
UMBRAL_CPU_CRITICO_MS = 90.0

# Buffer Manager: Buffer cache hit ratio — Microsoft: >= 90 es deseable.
BUFFER_CACHE_HIT_RATIO_DESEABLE = 90.0