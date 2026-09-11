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
    5. Calcula la importancia de variables mediante
       Permutation Importance adaptada al score de decisión.

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
from sklearn.inspection import permutation_importance

import config


def log(msg):
    print(f"[DETECCION IsoForest] {msg}", flush=True)


def cargar_muestras(ruta):
    with open(ruta, "rb") as f:
        d = pickle.load(f)
    return d


def seleccionar_features(datos, ruta_features_modelo):
    """
    Devuelve el índice de las variables mantenidas por 02 dentro
    del conjunto original de features.
    """
    if not os.path.exists(ruta_features_modelo):
        log(
            f"No existe {ruta_features_modelo}. "
            "Se usan todas las variables principales."
        )
        return list(range(len(datos["features"])))

    mantenidas = pd.read_csv(
        ruta_features_modelo,
        encoding="utf-8-sig"
    )["columna"].tolist()

    indice = []
    for m in mantenidas:
        if m in datos["features"]:
            indice.append(datos["features"].index(m))

    return indice


def flat(x, indice):
    """
    Aplana las ventanas a vectores [n, VENTANA * F] usando solo
    las features seleccionadas.
    """
    return x[:, :, indice].reshape(x.shape[0], -1)


def main():

    # --------------------------------------------------------
    # 1. CARGAR MUESTRAS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 2. ENTRENAMIENTO
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 3. SCORES Y UMBRALES
    # --------------------------------------------------------

    scores_train = modelo.decision_function(X_train)
    scores_test = modelo.decision_function(X_test)

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

    # --------------------------------------------------------
    # 4. EVALUACIÓN EN PRUEBA (FPR)
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 5. SCORES DE ENTRENAMIENTO
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 6. IMPORTANCIA POR VARIABLE (Permutation Importance)
    # --------------------------------------------------------

    def custom_scoring(estimator, X, y=None):
        return np.mean(estimator.decision_function(X))

    X_imp = X_test if len(X_test) > 0 else X_train
    perm_result = permutation_importance(
        modelo,
        X_imp,
        y=np.zeros(len(X_imp)),
        scoring=custom_scoring,
        n_repeats=5,
        random_state=config.SEED,
        n_jobs=-1
    )

    mant = [train["features"][i] for i in indice]
    v = config.VENTANA
    raw_importances = perm_result.importances_mean
    agg = {}

    for i, c in enumerate(mant):
        slice_importances = raw_importances[i * v : (i + 1) * v]
        agg[c] = float(np.mean(np.abs(slice_importances)))

    df_imp = pd.DataFrame(
        [{"columna": c, "importancia": agg[c]} for c in mant]
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

    # --------------------------------------------------------
    # 7. RESUMEN
    # --------------------------------------------------------

    print("\n=== IsoForest SOBRE REFERENCIA NORMAL ===")
    print("FPR (tasa de falsas alarmas) en corrida de prueba:")

    for nombre in ("q10", "q05", "q01"):
        fpr = float(df_alertas[nombre].mean())
        print(
            f"  umbral {nombre}: "
            f"{int(df_alertas[nombre].sum())} / "
            f"{len(df_alertas)} alertas "
            f"({fpr * 100:.2f}% del normal)"
        )

    print(
        f"\nPredicción IsoForest (contaminación automática): "
        f"{(df_alertas['prediccion'] == -1).sum()} / "
        f"{len(df_alertas)} en test"
    )

    print(
        f"Train: {(df_scores['prediccion'] == -1).sum()} / "
        f"{len(df_scores)} señalados como atípicos"
    )

    print("\n=== IMPORTANCIA DE VARIABLES (top 10) ===")
    print(df_imp.head(10).to_string(index=False))

    log(f"Alertas en: {ruta_alertas}")
    log(f"Scores en: {ruta_scores}")
    log(f"Importancia en: {ruta_imp}")


if __name__ == "__main__":
    main()