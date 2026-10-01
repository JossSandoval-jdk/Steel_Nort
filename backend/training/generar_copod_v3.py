"""
generar_copod_v3.py
===================

1. Pinea features_modelo.csv a config.VARIABLES_MODELO (paridad exacta
   entrenamiento <-> produccion, igual que se hizo para la v2).
2. Entrena el componente COPOD del ENSEMBLE_Z sobre el dataset de train v3
   y lo guarda en <DIR_DETECCION>/modelo_copod.joblib.

Debe ejecutarse con cwd = nucleo/modeling y con las mismas envs del
pipeline (STEELNORT_DATASET_SET / STEELNORT_MODELADO_SET).
"""

import os
import pickle
import sys

import joblib
import numpy as np
import pandas as pd

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BACKEND, "training", "nucleo", "modeling"))

import config  # noqa: E402


def main():
    ruta_train = os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl")
    if not os.path.exists(ruta_train):
        print(f"[COPOD-V3] Falta {ruta_train}. Ejecuta primero 01_muestras.py")
        return

    with open(ruta_train, "rb") as f:
        train = pickle.load(f)

    features = train["features"]
    modelo = [c for c in config.VARIABLES_MODELO if c in features]
    indice = [features.index(c) for c in modelo]
    X = np.asarray(train["X"], dtype="float64")
    X_sel = X[:, :, indice].reshape(X.shape[0], X.shape[1] * len(indice))
    print(f"[COPOD-V3] train={X_sel.shape[0]} ventanas x "
          f"{X_sel.shape[1]} caracteristicas ({len(indice)} vars)", flush=True)

    from pyod.models.copod import COPOD

    copod = COPOD()
    copod.fit(X_sel)

    os.makedirs(config.DIR_DETECCION, exist_ok=True)
    ruta_sal = os.path.join(config.DIR_DETECCION, "modelo_copod.joblib")
    joblib.dump(copod, ruta_sal)

    s = -np.asarray(copod.decision_function(X_sel))
    print(f"[COPOD-V3] scores train: min={s.min():.4f} mean={s.mean():.4f} "
          f"max={s.max():.4f}", flush=True)

    ruta_feat = os.path.join(config.DIR_CORRELACION, "features_modelo.csv")
    os.makedirs(os.path.dirname(ruta_feat), exist_ok=True)
    pd.DataFrame([{"columna": c} for c in modelo]).to_csv(
        ruta_feat, index=False, encoding="utf-8-sig")
    print(f"[COPOD-V3] features_modelo.csv pineado a {len(modelo)} vars: "
          f"{ruta_feat}", flush=True)
    print(f"[COPOD-V3] LISTO: {ruta_sal}", flush=True)


if __name__ == "__main__":
    main()