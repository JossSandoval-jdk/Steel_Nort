"""
03_deteccion_isolation_forest.py
================================

Detector de anomalías con IsolationForest:

    1. Carga las muestras por ventana (01_muestras.py) usando SOLO las
       variables del modelo (config.VARIABLES_MODELO).
    2. Entrena IsolationForest con los datos NORMALES del train.
    3. Umbrales q10/q05/q01 = percentiles de los scores de train
       (score < umbral => alerta).
    4. Evalúa el test y guarda alertas, scores e importancia.

Producto idéntico a la validación de experimental/medir_discriminacion.py
para la componente IsolationForest del detector desplegado.

Salidas (en <OUTPUT>/modelado/deteccion/):
    modelo_isolation_forest.joblib
    scaler.joblib
    alertas_test.csv
    scores_muestras.csv
    importancia_variables.csv
"""

import os
import pickle

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

import config


def log(msg):
    print(f"[DETECCION IsoForest] {msg}", flush=True)


def cargar_muestras(ruta):
    with open(ruta, "rb") as f:
        return pickle.load(f)


def seleccionar_features(datos, ruta_features_modelo=None):
    """Índices de las VARIABLES_MODELO presentes en el pkl."""
    modelo = [c for c in config.VARIABLES_MODELO if c in datos["features"]]
    return [datos["features"].index(c) for c in modelo]


def flat(x, indice):
    """Aplana ventanas a vectores [n, VENTANA * F] (features elegidas)."""
    return x[:, :, indice].reshape(x.shape[0], x.shape[1] * len(indice))


def main():
    ruta_train = os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl")
    ruta_test = os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl")
    if not (os.path.exists(ruta_train) and os.path.exists(ruta_test)):
        log("Faltan las muestras. Ejecuta 01_muestras.py.")
        return

    train = cargar_muestras(ruta_train)
    test = cargar_muestras(ruta_test)
    indice = seleccionar_features(train)

    X_train = flat(train["X"], indice)
    X_test = flat(test["X"], indice)
    hay_test = X_test.shape[0] > 0
    log(f"Train: {X_train.shape[0]} x {X_train.shape[1]} características "
        f"(ventana {train['ventana']}) | Test: {X_test.shape[0]}")

    modelo = IsolationForest(random_state=config.SEED, contamination="auto")
    modelo.fit(X_train)

    os.makedirs(config.DIR_DETECCION, exist_ok=True)
    joblib.dump(modelo, os.path.join(config.DIR_DETECCION,
                                     "modelo_isolation_forest.joblib"))
    joblib.dump(train["scaler"], os.path.join(config.DIR_DETECCION,
                                              "scaler.joblib"))
    log("Modelo entrenado y guardado.")

    scores_train = modelo.decision_function(X_train)
    scores_test = modelo.decision_function(X_test) if hay_test else np.empty(0)
    umbrales = {q: np.quantile(scores_train, p)
                for q, p in (("q10", 0.10), ("q05", 0.05), ("q01", 0.01))}
    log(f"Umbrales (score < umbral => alerta): "
        f"q10={umbrales['q10']:.4f} q05={umbrales['q05']:.4f} "
        f"q01={umbrales['q01']:.4f}")

    if hay_test:
        df_alertas = pd.DataFrame({
            "idx": range(len(test["ventanas"])),
            "run": test["runs"],
            "inicio": [w["inicio"] for w in test["ventanas"]],
            "fin": [w["fin"] for w in test["ventanas"]],
            "score": scores_test,
            "prediccion": modelo.predict(X_test),
        })
        for nombre, umbral in umbrales.items():
            df_alertas[nombre] = (df_alertas["score"] < umbral).astype(int)
        df_alertas.to_csv(os.path.join(config.DIR_DETECCION, "alertas_test.csv"),
                          index=False, encoding="utf-8-sig")

    df_scores = pd.DataFrame({
        "idx": range(len(train["ventanas"])),
        "run": train["runs"],
        "score": scores_train,
        "prediccion": modelo.predict(X_train),
    })
    df_scores.to_csv(os.path.join(config.DIR_DETECCION, "scores_muestras.csv"),
                     index=False, encoding="utf-8-sig")

    importancias = np.mean(
        [tree.feature_importances_ for tree in modelo.estimators_], axis=0)
    mant = [train["features"][i] for i in indice]
    v = config.VENTANA
    agg = {c: float(np.abs(importancias[i * v:(i + 1) * v]).mean())
           for i, c in enumerate(mant)}
    df_imp = pd.DataFrame(
        [{"columna": c, "importancia": agg[c]} for c in mant]
    ).sort_values("importancia", ascending=False)
    df_imp.to_csv(os.path.join(config.DIR_DETECCION,
                               "importancia_variables.csv"),
                  index=False, encoding="utf-8-sig")

    print("\n=== IsoForest SOBRE NORMAL (train) / ANOMALIAS (test) ===")
    if hay_test:
        for nombre in ("q10", "q05", "q01"):
            fpr = float(df_alertas[nombre].mean())
            print(f"  umbral {nombre}: {int(df_alertas[nombre].sum())} / "
                  f"{len(df_alertas)} alertas ({fpr * 100:.2f}% del test)")
        print(f"\nPredicción IsoForest (contaminación automática): "
              f"{(df_alertas['prediccion'] == -1).sum()} / "
              f"{len(df_alertas)} en test")
    else:
        print("Sin test de anomalias: solo entrenamiento (modo reentrenamiento).")
    print(f"Train: {(df_scores['prediccion'] == -1).sum()} / "
          f"{len(df_scores)} señalados como atípicos")
    print("\n=== IMPORTANCIA DE VARIABLES (top 10) ===")
    print(df_imp.head(10).to_string(index=False))


if __name__ == "__main__":
    main()