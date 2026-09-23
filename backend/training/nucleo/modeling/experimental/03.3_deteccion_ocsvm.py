"""
03_deteccion_ocsvm.py
======================
Detector de anomalías usando One-Class SVM (Support Vector Machine).
Aprende una frontera de decisión en un espacio de alta dimensión para aislar los datos normales.
"""

import os
import pickle
import joblib
import numpy as np
import pandas as pd
from sklearn.svm import OneClassSVM
from sklearn.inspection import permutation_importance
import config

def log(msg):
    print(f"[DETECCION OCSVM] {msg}", flush=True)

def cargar_muestras(ruta):
    with open(ruta, "rb") as f:
        d = pickle.load(f)
    return d

def seleccionar_features(datos, ruta_features_modelo):
    """
    Usa SOLO las VARIABLES_MODELO definidas en config (igual que
    03_deteccion_isolation_forest.py). ``ruta_features_modelo`` se ignora
    por compatibilidad con el resto del pipeline.
    """
    modelo = [
        c for c in config.VARIABLES_MODELO
        if c in datos["features"]
    ]
    indice = [datos["features"].index(c) for c in modelo]
    log(f"Modelo con {len(indice)} variables del motor/apoyo — poda aplicada.")
    return indice

def flat(x, indice):
    return x[:, :, indice].reshape(x.shape[0], -1)

def main():
    ruta_train = os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl")
    ruta_test = os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl")

    if not (os.path.exists(ruta_train) and os.path.exists(ruta_test)):
        log("Faltan las muestras. Ejecuta 01_muestras.py.")
        return

    train = cargar_muestras(ruta_train)
    test = cargar_muestras(ruta_test)
    indice = seleccionar_features(train, os.path.join(config.DIR_CORRELACION, "features_modelo.csv"))

    X_train = flat(train["X"], indice)
    X_test = flat(test["X"], indice)

    log(f"Train: {X_train.shape[0]} muestras x {X_train.shape[1]} características")
    log(f"Test: {X_test.shape[0]} muestras")

    # 1. Entrenamiento del modelo
    # nu equivale aproximadamente a la proporción de valores atípicos admitidos (ej. 0.05)
    modelo = OneClassSVM(nu=0.05, kernel='rbf', gamma='scale')
    modelo.fit(X_train)

    os.makedirs(config.DIR_DETECCION, exist_ok=True)
    joblib.dump(modelo, os.path.join(config.DIR_DETECCION, "modelo_ocsvm.joblib"))
    log("Modelo One-Class SVM entrenado y guardado (sin tocar scaler.joblib de producción).")

    # 2. Scores y Umbrales
    # decision_function es la distancia con signo al hiperplano:
    # mayor = normal, menor = anomalia (misma convención que IsolationForest),
    # asi que NO se invierte.
    scores_train = modelo.decision_function(X_train)
    scores_test = modelo.decision_function(X_test)

    umbrales = {
        "q10": np.quantile(scores_train, 0.10),
        "q05": np.quantile(scores_train, 0.05),
        "q01": np.quantile(scores_train, 0.01),
    }

    # 3. Evaluación en prueba (FPR)
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

    df_alertas.to_csv(os.path.join(config.DIR_DETECCION, "alertas_test_ocsvm.csv"), index=False, encoding="utf-8-sig")

    # 4. Scores de entrenamiento
    df_scores = pd.DataFrame({
        "idx": range(len(train["ventanas"])),
        "run": train["runs"],
        "score": scores_train,
        "prediccion": modelo.predict(X_train),
    })
    df_scores.to_csv(os.path.join(config.DIR_DETECCION, "scores_muestras_ocsvm.csv"), index=False, encoding="utf-8-sig")

    # 5. Importancia de variables (Permutation Importance)
    def custom_scoring(estimator, X, y=None):
        return np.mean(-estimator.decision_function(X))

    X_imp = X_test if len(X_test) > 0 else X_train
    perm_result = permutation_importance(
        modelo, X_imp, y=np.zeros(len(X_imp)),
        scoring=custom_scoring, n_repeats=5, random_state=config.SEED, n_jobs=-1
    )

    mant = [train["features"][i] for i in indice]
    v = config.VENTANA
    raw_importances = perm_result.importances_mean
    agg = {c: float(np.mean(np.abs(raw_importances[i * v : (i + 1) * v]))) for i, c in enumerate(mant)}

    df_imp = pd.DataFrame([{"columna": c, "importancia": agg[c]} for c in mant]).sort_values("importancia", ascending=False)
    df_imp.to_csv(os.path.join(config.DIR_DETECCION, "importancia_variables_ocsvm.csv"), index=False, encoding="utf-8-sig")

    # 6. Resumen por consola
    print("\n=== ONE-CLASS SVM SOBRE REFERENCIA NORMAL ===")
    for nombre in ("q10", "q05", "q01"):
        fpr = float(df_alertas[nombre].mean())
        print(f"  umbral {nombre}: {int(df_alertas[nombre].sum())} / {len(df_alertas)} alertas ({fpr * 100:.2f}%)")

if __name__ == "__main__":
    main()