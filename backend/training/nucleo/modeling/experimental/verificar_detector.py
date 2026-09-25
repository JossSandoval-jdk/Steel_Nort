"""
verificar_detector.py
=====================

Verificacion SIMPLE del detector desplegado (app.ml.detector):

  1. Instancia el Detector REAL de produccion en el modo ENSEMBLE_Z
     (IsoForest + COPOD) y en el modo ISOLATION_FOREST (sin COPOD).
  2. Puntua las 108 ventanas de FALLO del test con el mismo codigo que
     corre el backend (_score_ensamble) -> TPR por umbral.
  3. Puntua las 230 ventanas NORMALES del train -> FPR de sana-cordura
     (por construccion debe dar ~el percentil elegido).
  4. Pide el FPR de GENERALIZACION (leave-one-run-out) al informe ya
     guardado por experimental/medir_discriminacion.py y calcula el F1
     final por umbral.

Salidas por consola.
"""

from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "training" / "nucleo" / "modeling"))

import joblib
import numpy as np
import pandas as pd

import config
from app.ml.detector import Detector, ML_ARTIFACTS, TRAIN_PKL

QQ = {"q10": 0.10, "q05": 0.05, "q01": 0.01}
ART = Path(ML_ARTIFACTS)


def cargar(r):
    with open(r, "rb") as f:
        return pickle.load(f)


def puntuar(det, X):
    return np.asarray([det._score_ensamble(X[i:i + 1]) for i in range(len(X))])


def main():
    train = cargar(TRAIN_PKL)
    test = cargar(os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl"))

    feats = pd.read_csv(ART / "features_modelo.csv").iloc[:, 0].astype(str).str.strip().tolist()
    indice = [train["features"].index(c) for c in feats]
    F_sel = len(indice)

    # Entero pkl ya escalado (scaler desplegado == scaler del pkl).
    X_tr = np.asarray(train["X"], dtype="float64")[:, :, indice].reshape(len(train["runs"]), -1)
    # Test: reconstruir a crudo y re-escalar con el scaler desplegado.
    raw_te = (np.asarray(test["X"], dtype="float64") * test["scaler"].scale_
              + test["scaler"].mean_)[:, :, indice]
    sc = joblib.load(ART / "scaler.joblib")
    X_te = ((raw_te - np.asarray(sc.mean_)[indice])
            / np.asarray(sc.scale_)[indice]).reshape(len(test["runs"]), -1)

    print(f"[VERIFICAR] normales train={len(X_tr)} | fallos test={len(X_te)} "
          f"| features={F_sel} | puntos de operacion={list(QQ)}")

    informe = pd.read_csv(os.path.join(config.DIR_DETECCION, "informe_discriminacion.csv"))
    informe = informe[informe["esquema"].isin(["ISOLATION_FOREST", "ENSEMBLE_Z"])]
    informe = informe.set_index(["esquema", "umbral"])["fpr"]

    filas = []
    for usar_copod in (False, True):
        modo = "ENSEMBLE_Z" if usar_copod else "ISOLATION_FOREST"
        det = Detector(
            ruta_modelo=str(ART / "modelo_isolation_forest.joblib"),
            ruta_modelo_copod=str(ART / "modelo_copod.joblib") if usar_copod else None,
            ruta_scaler=str(ART / "scaler.joblib"),
            ruta_features=str(ART / "features_modelo.csv"),
            ruta_train_pkl=TRAIN_PKL, ventana=10, umbral_nombre="q01",
        )
        s_tr = puntuar(det, X_tr)
        s_te = puntuar(det, X_te)
        print(f"  modo={modo:<14} | estado: {det.estado()['modo']} "
              f"| umbrales: { {q: round(v,4) for q, v in det.umbrales.items()} }")
        for q in QQ:
            tpr = float((s_te < det.umbrales[q]).mean())   # 108 fallos
            fpr_train = float((s_tr < det.umbrales[q]).mean())  # sana-cordura
            fpr_loo = float(informe.loc[(modo, q)])
            prec = tpr / (tpr + fpr_loo) if (tpr + fpr_loo) else 0.0
            f1 = 2 * prec * tpr / (prec + tpr) if (prec + tpr) else 0.0
            filas.append({
                "modo": modo, "umbral": q,
                "tpr_test": round(tpr, 4), "fpr_train": round(fpr_train, 4),
                "fpr_generalizacion_loo": round(fpr_loo, 4),
                "f1": round(f1, 4),
            })

    df = pd.DataFrame(filas)
    print("\n=== COMPARACION: ISO SOLO vs ENSAMBLE (COPOD + ISO) ===")
    print(df.to_string(index=False))
    print("\nTPR_test: proporcion de fallos detectados con el detector DESPLEGADO.")
    print("fpr_train: sana-cordura (~percentil). fpr_loo: falsas alarmas sobre")
    print("corridas normales NUEVAS (informe_discriminacion). f1: balance final.")


if __name__ == "__main__":
    main()