"""
01_detectar_candidatos.py
=========================
Entrena detectores candidatos (LOF, Elliptic, OCSVM, COPOD) y evalúa
sobre el mismo train/test del Isolation Forest.

Entrada : output/modelado/artefactos_modelo.pkl
Salida  : output/modelado/candidatos.json

Uso:
    python experimental/01_detectar_candidatos.py
    python experimental/01_detectar_candidatos.py lof ocsvm
"""

import argparse
import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.covariance import EllipticEnvelope
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from pyod.models.copod import COPOD

# Rutas al config del modelado
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelado_config import (                       # noqa: E402
    DIR_MODELADO, VENTANA, SEED, VARIABLES_MODELO, log,
)


# ==========================================
# Detectores disponibles
# ==========================================
# (nombre, constructor, pyod) — pyod=True invierte el signo del score
DETECTORES = {
    "lof":      (lambda: LocalOutlierFactor(n_neighbors=35, novelty=True,
                                            contamination="auto"), False),
    "elliptic": (lambda: EllipticEnvelope(contamination=0.05,
                                          random_state=SEED), False),
    "ocsvm":    (lambda: OneClassSVM(nu=0.05, kernel="rbf", gamma="scale"), False),
    "copod":    (lambda: COPOD(contamination=0.05), True),
}

# Signo de la importancia por permutación (PyOD da alto=anómalo)
SIGNO_IMPORTANCIA = {"ocsvm": -1.0, "copod": -1.0}


# ==========================================
# Carga de artefactos
# ==========================================
def cargar_artefactos():
    ruta = os.path.join(DIR_MODELADO, "artefactos_modelo.pkl")
    if not os.path.exists(ruta):
        log(f"Falta {ruta}. Ejecuta modelado/01_entrenamiento.py.")
        return None
    with open(ruta, "rb") as f:
        return pickle.load(f)


def seleccionar_indices(features):
    """Índices de VARIABLES_MODELO presentes en el artefacto."""
    presentes = [c for c in VARIABLES_MODELO if c in features]
    return [features.index(c) for c in presentes]


def aplanar(X, indice):
    """[n, ventana, F] -> [n, ventana * len(indice)]."""
    return X[:, :, indice].reshape(X.shape[0], -1)


# ==========================================
# Evaluación de un detector
# ==========================================
def puntuar(modelo, X, es_pyod):
    """Score con convención: menor = más anómalo."""
    s = modelo.decision_function(X)
    return -s if es_pyod else s


def predecir(modelo, X, es_pyod):
    """Etiqueta 1=normal, -1=anómalo."""
    if es_pyod:
        return np.where(modelo.predict(X) == 1, -1, 1)
    return modelo.predict(X)


def evaluar_detector(nombre, fab, es_pyod, art):
    """Entrena el detector y devuelve dict con métricas."""
    log(f"== {nombre.upper()}")

    features = art["features"]
    indice = seleccionar_indices(features)
    X_train = aplanar(art["X_train"], indice)
    X_test = aplanar(art["X_test"], indice)

    modelo = fab()
    modelo.fit(X_train)

    s_train = puntuar(modelo, X_train, es_pyod)
    s_test = puntuar(modelo, X_test, es_pyod) if len(X_test) else np.empty(0)

    umbrales = {q: float(np.quantile(s_train, p))
                for q, p in (("q10", 0.10), ("q05", 0.05), ("q01", 0.01))}

    # Alertas por umbral
    alertas = {
        q: {
            "train": int((s_train < u).sum()),
            "test": int((s_test < u).sum()) if len(s_test) else 0,
        }
        for q, u in umbrales.items()
    }

    # Predicción nativa del modelo (contamination propio)
    pred_train = predecir(modelo, X_train, es_pyod)
    pred_test = predecir(modelo, X_test, es_pyod) if len(s_test) else np.empty(0, dtype=int)

    return {
        "modelo": nombre,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "alertas_por_umbral": alertas,
        "scores_train": s_train.tolist(),
        "scores_test": s_test.tolist(),
        "umbrales": umbrales,
        "pred_train": pred_train.tolist(),
        "pred_test": pred_test.tolist(),
    }


# ==========================================
# Main
# ==========================================
def main():
    ap = argparse.ArgumentParser(description="Entrena detectores candidatos.")
    ap.add_argument("detectores", nargs="*", choices=list(DETECTORES),
                    default=None,
                    help="En blanco = todos.")
    args = ap.parse_args()

    art = cargar_artefactos()
    if art is None:
        return

    detectores_a_evaluar = args.detectores if args.detectores else list(DETECTORES)
    resultados = {}
    for nombre in detectores_a_evaluar:
        fab, es_pyod = DETECTORES[nombre]
        try:
            resultados[nombre] = evaluar_detector(nombre, fab, es_pyod, art)
        except Exception as e:
            log(f"{nombre}: ERROR -> {e}")
            resultados[nombre] = {"error": str(e)}

    if not resultados:
        log("Sin resultados.")
        return

    ruta = os.path.join(DIR_MODELADO, "candidatos.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({
            "ventana": VENTANA,
            "variables_modelo": VARIABLES_MODELO,
            "detectores": resultados,
        }, f, ensure_ascii=False, indent=2)
    log(f"Candidatos: {ruta}")

    # Resumen por consola
    print("\n=== ALERTAS EN TEST (por umbral) ===")
    filas = []
    for nombre, r in resultados.items():
        if "error" in r:
            filas.append({"modelo": nombre, "error": r["error"]})
            continue
        filas.append({
            "modelo": nombre,
            "n_test": r["n_test"],
            "q10": r["alertas_por_umbral"]["q10"]["test"],
            "q05": r["alertas_por_umbral"]["q05"]["test"],
            "q01": r["alertas_por_umbral"]["q01"]["test"],
        })
    print(pd.DataFrame(filas).to_string(index=False))


if __name__ == "__main__":
    main()