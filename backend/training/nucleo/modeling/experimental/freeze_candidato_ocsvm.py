"""
freeze_candidato_ocsvm.py
=========================
Congela el candidato simple OCSVM (un solo detector, sin ensamble) sobre el
train corregido de VARIABLES_MODELO.

Entrena con TODAS las corridas normales del train pkl (config de despliegue),
calcula umbrales q10/q05/q01 sobre sus propios scores y guarda:
    deteccion/candidato_ocsvm.joblib  (bundle: modelo + scaler + features + umbrales)
    deteccion/registro_candidato_ocsvm.json
"""

import json
import os
import sys

import joblib
import numpy as np
from sklearn.preprocessing import StandardScaler
from pyod.models.ocsvm import OCSVM

import config

QQ = {"q01": 0.01, "q05": 0.05, "q10": 0.10}


def log(msg):
    print(f"[FREEZE] {msg}", flush=True)


def cargar(archivo):
    with open(archivo, "rb") as f:
        import pickle
        return pickle.load(f)


def main():
    train = cargar(os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl"))
    X = train["X"] * train["scaler"].scale_ + train["scaler"].mean_
    features = train["features"]
    V = train["ventana"]

    indice = [features.index(c) for c in config.VARIABLES_MODELO if c in features]
    F = len(indice)
    if F == 0:
        log("Sin interseccion VARIABLES_MODELO x pkl.")
        return

    rawv = X[:, :, indice]
    sc = StandardScaler().fit(rawv.reshape(-1, F))
    Xf = sc.transform(rawv.reshape(-1, F)).reshape(len(train["runs"]), -1)

    modelo = OCSVM(contamination=0.05).fit(Xf)
    s = -modelo.decision_function(Xf)  # mayor = normal

    umbrales = {q: float(np.quantile(s, v)) for q, v in QQ.items()}
    bundle = {
        "modelo": "OCSVM",
        "ventana": int(V),
        "contamination": 0.05,
        "ocsvm": modelo,
        "scaler": sc,
        "features": [features[i] for i in indice],
        "indice_54": indice,
        "umbrales": umbrales,
        "hiperparametros": {"kernel": "rbf", "contamination": 0.05,
                            "scaler": "standard",
                            "n_train_windows": int(len(train["runs"]))},
    }
    ruta_bundle = os.path.join(config.DIR_DETECCION, "candidato_ocsvm.joblib")
    joblib.dump(bundle, ruta_bundle)

    registro = {
        "modelo": "OCSVM",
        "fecha_validacion": np.datetime64("now").astype("datetime64[s]").astype(str),
        "umbrales": umbrales,
        "n_train_windows": int(len(train["runs"])),
        "features": bundle["features"],
        "artefacto": "deteccion/candidato_ocsvm.joblib",
        "nota": ("Modelo simple (sin ensamble). Entrenado con las corridas "
                 "normales corregidas del train pkl."),
    }
    ruta_reg = os.path.join(config.DIR_DETECCION, "registro_candidato_ocsvm.json")
    with open(ruta_reg, "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)

    log(f"OCSVM congelado: {len(bundle['features'])} features, "
        f"umbrales={ {k: round(u, 4) for k, u in umbrales.items()} }")
    log(f"Bundle -> {ruta_bundle}")


if __name__ == "__main__":
    main()