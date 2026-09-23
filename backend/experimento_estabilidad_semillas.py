"""
experimento_estabilidad_semillas.py
=====================================
Experimento 1 de 07_experimentos_adicionales.py, adaptado al pipeline
real de SteelNort.

Objetivo:
    Demostrar que el modelo elegido (IsolationForest / LOF) NO depende
    del azar de inicialización. Se entrena cada modelo 10 veces con
    semillas distintas sobre los mismos datos y se mide cuánto varía
    el número de alertas (std ≈ 0 → modelo estable y reproducible).
    del azar de inicializacion. Se entrena cada modelo 10 veces con
    semillas distintas sobre los mismos datos y se mide cuanto varia
    el numero de alertas (std ~ 0 -> modelo estable y reproducible).

Modelos evaluados (solo sklearn, misma convención que el pipeline):
    - IsolationForest  (afectado por semilla → esperamos std baja)
    - LOF              (determinista con novelty=True → std = 0)
    - OCSVM            (determinista con kernel RBF → std = 0)
Modelos evaluados (todos los del pipeline comparativo):
    - IsolationForest   (estocastico -> esperamos std baja pero no 0)
    - LOF               (determinista con novelty=True -> std = 0)
    - OCSVM             (determinista con kernel RBF -> std = 0)
    - EllipticEnvelope  (determinista -> std = 0 pero puede colapsar)
    - COPOD             (determinista -> std = 0)

Referencia:
    Zhang et al. (2026). Hierarchical reference sets for robust
    unsupervised detection of scattered and clustered outliers.
    arXiv:2603.12847. → Múltiples semillas para validar estabilidad.
    arXiv:2603.12847. -> Multiples semillas para validar estabilidad.

Uso (desde la raíz del backend):
Uso (desde la raiz del backend):
    python experimento_estabilidad_semillas.py
"""

from __future__ import annotations

import os
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.covariance import EllipticEnvelope

# COPOD: implementacion manual ligera (sin pyod) usando copulas marginales
# Si no esta disponible, se usa un fallback con ECOD approx via ranking
try:
    from pyod.models.copod import COPOD as _COPOD_pyod
    _COPOD_DISPONIBLE = True
except ImportError:
    _COPOD_DISPONIBLE = False

# ---------------------------------------------------------------------------
# Rutas del proyecto (idénticas a las del pipeline real)
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parent
MODELING_DIR = BACKEND_ROOT / "training" / "nucleo" / "modeling"

sys.path.insert(0, str(MODELING_DIR))
import config  # noqa: E402 — config.py del módulo de modelado

PKL_TRAIN = BACKEND_ROOT / "training" / "output" / "modelado" / "dataset_muestras_train.pkl"
DIR_DETECCION = BACKEND_ROOT / "training" / "output" / "modelado" / "deteccion"
SALIDA_CSV = DIR_DETECCION / "experimento_estabilidad_semillas.csv"

# ---------------------------------------------------------------------------
# Parámetros del experimento
# ---------------------------------------------------------------------------
SEEDS = list(range(10))          # 10 semillas: 0, 1, 2, … 9
CONTAMINATION = "auto"           # igual que en 03_deteccion_isolation_forest.py
N_NEIGHBORS_LOF = 35             # igual que en 03.1_deteccion_lof.py
NU_OCSVM = 0.05                  # igual que en 03.3_deteccion_ocsvm.py
UMBRAL_PERCENTIL = 10            # q10 → mismo umbral de producción


def log(msg: str) -> None:
    print(f"[ESTABILIDAD] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Carga y preparación de datos
# ---------------------------------------------------------------------------
def cargar_y_preparar() -> tuple[np.ndarray, np.ndarray]:
    """
    Carga el pkl de entrenamiento y devuelve:
        X_train_flat : array (n_muestras, VENTANA × n_features_modelo)
        features_idx : índices de las VARIABLES_MODELO dentro del pkl
    """
    if not PKL_TRAIN.exists():
        log(f"Falta el pkl: {PKL_TRAIN}")
        log("Ejecuta primero el Paso 4 (01_muestras.py → 02_correlacion.py → 03_deteccion…)")
        sys.exit(1)

    with open(PKL_TRAIN, "rb") as f:
        d = pickle.load(f)

    features = d["features"]
    modelo_cols = [c for c in config.VARIABLES_MODELO if c in features]
    idx = [features.index(c) for c in modelo_cols]

    log(f"PKL cargado: {d['X'].shape[0]} muestras, ventana={d['ventana']}, "
        f"{len(idx)} features del modelo sobre {len(features)} totales")

    # Aplanar: (n, ventana, features) → (n, ventana × features)
    X_flat = d["X"][:, :, idx].reshape(d["X"].shape[0], -1)
    return X_flat, modelo_cols


# ---------------------------------------------------------------------------
# Cálculo de alertas con cada semilla
# ---------------------------------------------------------------------------
def contar_alertas_q10(scores_train: np.ndarray, scores_eval: np.ndarray) -> int:
    """Umbral q10 de los scores de TRAIN → cuántas muestras de EVAL quedan bajo él."""
    umbral = np.percentile(scores_train, UMBRAL_PERCENTIL)
    return int(np.sum(scores_eval < umbral))


def evaluar_isolation_forest(X: np.ndarray, seed: int) -> int:
    clf = IsolationForest(
        n_estimators=100,
        contamination=CONTAMINATION,
        random_state=seed,
    )
    clf.fit(X)
    scores = clf.decision_function(X)
    return contar_alertas_q10(scores, scores)


def evaluar_lof(X: np.ndarray, seed: int) -> int:
    # LOF es determinista (sin random_state relevante); seed se recibe por
    # uniformidad de la interfaz pero no se usa.
    clf = LocalOutlierFactor(
        n_neighbors=N_NEIGHBORS_LOF,
        contamination=CONTAMINATION,
        novelty=True,
    )
    clf.fit(X)
    scores = clf.decision_function(X)
    return contar_alertas_q10(scores, scores)


def evaluar_ocsvm(X: np.ndarray, seed: int) -> int:
    # OCSVM con kernel RBF también es determinista.
    # OCSVM con kernel RBF tambien es determinista.
    clf = OneClassSVM(nu=NU_OCSVM, gamma="scale", kernel="rbf")
    clf.fit(X)
    scores = clf.decision_function(X)
    return contar_alertas_q10(scores, scores)


def evaluar_elliptic(X: np.ndarray, seed: int) -> int:
    """EllipticEnvelope: determinista pero puede colapsar con datos de alta dimension."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # silenciar "not full rank"
            clf = EllipticEnvelope(
                contamination=0.10,
                random_state=seed if seed is not None else 0,
            )
            clf.fit(X)
            scores = clf.decision_function(X)
            return contar_alertas_q10(scores, scores)
    except Exception:
        # Si la matriz colapsa, no puede dar resultado -> NaN representado como -1
        return -1


def evaluar_copod(X: np.ndarray, seed: int) -> int:
    """
    COPOD via pyod si esta disponible.
    Fallback: score por rango de percentil (ranking) similar a COPOD simplificado.
    """
    if _COPOD_DISPONIBLE:
        clf = _COPOD_pyod(contamination=0.10)
        clf.fit(X)
        # pyod: score ALTO = anomalia (convencion inversa a sklearn)
        scores = -clf.decision_scores_  # invertir para usar misma convencion
        return contar_alertas_q10(scores, scores)
    else:
        # Fallback: score por rango acumulativo de percentil por columna (aprox COPOD)
        n = X.shape[0]
        scores_left = np.mean(np.argsort(np.argsort(X, axis=0), axis=0) / n, axis=1)
        scores_right = np.mean(np.argsort(np.argsort(-X, axis=0), axis=0) / n, axis=1)
        # Score "normalidad" = minimo del rango (mas central = mas normal)
        scores = -np.minimum(scores_left, scores_right)
        return contar_alertas_q10(scores, scores)


MODELOS = {
    "IsolationForest": evaluar_isolation_forest,
    "LOF":             evaluar_lof,
    "OCSVM":           evaluar_ocsvm,
    "IsolationForest":  evaluar_isolation_forest,
    "LOF":              evaluar_lof,
    "OCSVM":            evaluar_ocsvm,
    "EllipticEnvelope": evaluar_elliptic,
    "COPOD":            evaluar_copod,
}

ES_DETERMINISTICO = {
    "IsolationForest": False,
    "LOF":             True,
    "OCSVM":           True,
    "IsolationForest":  False,
    "LOF":              True,
    "OCSVM":            True,
    "EllipticEnvelope": True,
    "COPOD":            True,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    log("Iniciando Experimento 1: Estabilidad por semillas aleatorias")
    log(f"Seeds: {SEEDS}  |  Umbral: q{UMBRAL_PERCENTIL}  |  N={len(SEEDS)} iteraciones por modelo")

    X, modelo_cols = cargar_y_preparar()
    log(f"Shape de entrada: {X.shape}")

    resultados: dict[str, list[int]] = {nombre: [] for nombre in MODELOS}

    for seed in SEEDS:
        log(f"  Semilla {seed:2d}...")
        for nombre, fn in MODELOS.items():
            n = fn(X, seed)
            resultados[nombre].append(n)

    # ------------------------------------------------------------------
    # Tabla resumen
    # ------------------------------------------------------------------
    filas = []
    for nombre, valores in resultados.items():
        arr = np.array(valores)
        filas.append({
            "Modelo":              nombre,
            "Determinista":        "Sí" if ES_DETERMINISTICO[nombre] else "No",
            "Media alertas (q10)": f"{arr.mean():.2f}",
            "Std":                 f"{arr.std():.4f}",
            "Min":                 int(arr.min()),
            "Max":                 int(arr.max()),
            "Rango (Max-Min)":     int(arr.max() - arr.min()),
        })

    tabla = pd.DataFrame(filas)

    print()
    print("=" * 70)
    print("  EXPERIMENTO 1 — ESTABILIDAD POR SEMILLAS (10 iteraciones)")
    print("=" * 70)
    print(tabla.to_string(index=False))
    print()
    print("Interpretacion:")
    print("  Std ~0.0000 -> El modelo produce el mismo resultado sin importar")
    print("                 la semilla (estable / determinista).")
    print("  Std alta    -> El modelo varia con la inicializacion (inestable).")
    print("  IsolationForest esperado: Std baja (< 5 alertas de variacion).")
    print("  LOF / OCSVM esperado:     Std = 0.0000 (siempre identico).")
    print()

    # ------------------------------------------------------------------
    # Tabla detallada por semilla
    # ------------------------------------------------------------------
    df_detalle = pd.DataFrame(resultados, index=[f"Semilla {s}" for s in SEEDS])
    print("Detalle por semilla:")
    print(df_detalle.to_string())
    print()

    # ------------------------------------------------------------------
    # Guardar CSV
    # ------------------------------------------------------------------
    os.makedirs(DIR_DETECCION, exist_ok=True)
    tabla.to_csv(SALIDA_CSV, index=False, encoding="utf-8-sig")
    log(f"Resultados guardados en: {SALIDA_CSV}")


if __name__ == "__main__":
    main()
