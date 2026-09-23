"""
03_deteccion_isolation_forest.py
================================

Detector de anomalías adaptado de DBPA (evaluation/detect.py).

Metodología:
    1. Carga las muestras por ventana (01_muestras.py) usando
       SOLO las variables mantenidas por el análisis de
       correlación (02_correlacion.py).
    2. Entrena IsolationForest únicamente con datos NORMALES
       de referencia (corridas de entrenamiento).
    3. Umbrales derivados de la distribución de scores de
       entrenamiento (q10/q05/q01).
    4. Evalúa sobre la corrida de prueba: al ser también una
       captura normal, la proporción de alertas equivale a la
       TASA DE FALSAS ALARMAS (FPR).
    5. Si se proveen etiquetas reales de anomalía, calcula
       además P / R / F1 por tipo (como DBPA).

Salidas (en <OUTPUT>/modelado/deteccion/):
    modelo_isolation_forest.joblib
    scaler.joblib
    alertas_<test_run>.csv
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
        d = pickle.load(f)
    return d

def seleccionar_features(datos, ruta_features_modelo):
    """
    Usa SOLO las VARIABLES_MODELO definidas en config (poda de
    redundancias: cpu_idl, memory_used_mb, duration_max_ms).
    ``ruta_features_modelo`` se ignora por compatibilidad con el resto
    del pipeline.
    """
    modelo = [
        c for c in config.VARIABLES_MODELO
        if c in datos["features"]
    ]
    indice = [datos["features"].index(c) for c in modelo]
    log(f"Modelo con {len(indice)} variables del motor/apoyo — poda aplicada.")
    return indice

def flat(x, indice):
    """
    Aplana las ventanas a vectores [n, VENTANA * F] usando solo
    las features seleccionadas.
    """

    n = x.shape[0]

    return x[:, :, indice].reshape(n, x.shape[1] * len(indice))

def main():

    ruta_train = os.path.join(
        config.DIR_MODELADO,
        "dataset_muestras_train.pkl"
    )

    ruta_test = os.path.join(
        config.DIR_MODELADO,
        "dataset_muestras_test.pkl"
    )

    if not (os.path.exists(ruta_train) and os.path.exists(ruta_test)):

        log("Faltan las muestras. Ejecuta 01_muestras.py.")

        return

    train = cargar_muestras(ruta_train)

    test = cargar_muestras(ruta_test)

    indice = seleccionar_features(
        train,
        os.path.join(
            config.DIR_CORRELACION,
            "features_modelo.csv"
        )
    )

    X_train = flat(train["X"], indice)

    X_test = flat(test["X"], indice)

    n_feat_ventana = X_train.shape[1]

    log(
        f"Train: {X_train.shape[0]} muestras x {n_feat_ventana} "
        f"características (ventana {train['ventana']})"
    )

    log(
        f"Test:  {X_test.shape[0]} muestras"
    )

    hay_test = X_test.shape[0] > 0
    if not hay_test:
        log("Sin test de anomalias (modo reentrenamiento): solo entrenamiento.")

    modelo = IsolationForest(
        random_state=config.SEED,
        contamination="auto"
    )

    modelo.fit(X_train)

    os.makedirs(config.DIR_DETECCION, exist_ok=True)

    joblib.dump(
        modelo,
        os.path.join(
            config.DIR_DETECCION,
            "modelo_isolation_forest.joblib"
        )
    )

    joblib.dump(
        train["scaler"],
        os.path.join(
            config.DIR_DETECCION,
            "scaler.joblib"
        )
    )

    log("Modelo entrenado y guardado.")

    scores_train = modelo.decision_function(X_train)

    scores_test = (
        modelo.decision_function(X_test)
        if hay_test else np.empty(0)
    )

    umbrales = {
        "q10": np.quantile(scores_train, 0.10),
        "q05": np.quantile(scores_train, 0.05),
        "q01": np.quantile(scores_train, 0.01),
    }

    log(
        "Umbrales (score < umbral => alerta): "
        f"q10={umbrales['q10']:.4f} "
        f"q05={umbrales['q05']:.4f} "
        f"q01={umbrales['q01']:.4f}"
    )

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

            df_alertas[nombre] = (
                df_alertas["score"] < umbral
            ).astype(int)

        ruta_alertas = os.path.join(
            config.DIR_DETECCION,
            "alertas_test.csv"
        )

        df_alertas.to_csv(
            ruta_alertas,
            index=False,
            encoding="utf-8-sig"
        )
    else:
        df_alertas = None

    df_scores = pd.DataFrame({
        "idx": range(len(train["ventanas"])),
        "run": train["runs"],
        "score": scores_train,
        "prediccion": modelo.predict(X_train),
    })

    ruta_scores = os.path.join(
        config.DIR_DETECCION,
        "scores_muestras.csv"
    )

    df_scores.to_csv(
        ruta_scores,
        index=False,
        encoding="utf-8-sig"
    )

    importancias = np.mean(
        [
            tree.feature_importances_
            for tree in modelo.estimators_
        ],
        axis=0
    )

    mant = [train["features"][i] for i in indice]

    v = config.VENTANA

    agg = {
        c: float(
            np.abs(importancias[i * v: (i + 1) * v]).mean()
        )
        for i, c in enumerate(mant)
    }

    df_imp = pd.DataFrame(
        [{"columna": c, "importancia": agg[c]}
         for c in mant]
    ).sort_values("importancia", ascending=False)

    ruta_imp = os.path.join(
        config.DIR_DETECCION,
        "importancia_variables.csv"
    )

    df_imp.to_csv(
        ruta_imp,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n=== IsoForest SOBRE NORMAL (train) / ANOMALIAS (test) ===")

    if df_alertas is not None:

        print("Ventanas de TEST (corrida de anomalias) marcadas por umbral:")

        for nombre in ("q10", "q05", "q01"):

            fpr = float(df_alertas[nombre].mean())

            print(
                f"  umbral {nombre}: "
                f"{int(df_alertas[nombre].sum())} / "
                f"{len(df_alertas)} alertas "
                f"({fpr * 100:.2f}% del test)"
            )

        print("\nNota: TPR/FPR reales se cruzan con anomalias_timeline.csv en "
              "el paso 5 (05_diagnostico).")

        print(
            f"\nPredicción IsoForest (contaminación automática): "
            f"{(df_alertas['prediccion'] == -1).sum()} / "
            f"{len(df_alertas)} en test"
        )
    else:
        print("Sin test de anomalias: solo entrenamiento (modo reentrenamiento).")

    print(
        f"Train: {(df_scores['prediccion'] == -1).sum()} / "
        f"{len(df_scores)} señalados como atípicos"
    )

    print("\n=== IMPORTANCIA DE VARIABLES (top 10) ===")

    print(df_imp.head(10).to_string(index=False))

    if df_alertas is not None:
        log(f"Alertas en: {ruta_alertas}")

    log(f"Scores en: {ruta_scores}")

    log(f"Importancia en: {ruta_imp}")

if __name__ == "__main__":
    main()
