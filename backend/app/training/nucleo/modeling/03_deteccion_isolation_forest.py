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
Devuelve el índice de las variables mantenidas por 02 dentro
    del conjunto original de features.
    """

    # features_modelo.csv lo escribe 02_correlacion.py: contiene SOLO las
    # variables que sobrevivieron a la poda por correlación. Si no
    # existe, se usan todas (fallback prudente).
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

    # Traducimos NOMBRES de variable → POSICIÓN en la lista de features
    # original (los pkl de 01 guardan X en el mismo orden).
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

    # Cada muestra es [VENTANA, F]; el IsolationForest espera un vector
    # por fila, así que concatenamos la ventana: [VENTANA*F]. El árbol
    # "ve" cada variable en cada instante de la ventana por separado.
    return x[:, :, indice].reshape(x.shape[0], -1)


def metricas(prediccion, etiquetas):
    """
    Calcula TP/FP/TN/FN y P, R, F1 (positivo = anomalía).
    """

    # Convención de sklearn: -1 = ANÓMALO, +1 = NORMAL. Contamos cuántas
    # celdas caen en cada combinación (predicción vs etiqueta real).
    tp = int(np.sum((prediccion == -1) & (etiquetas == -1)))  # acierto en anomalía
    fp = int(np.sum((prediccion == -1) & (etiquetas == 1)))   # falsa alarma
    tn = int(np.sum((prediccion == 1) & (etiquetas == 1)))    # acierto en normal
    fn = int(np.sum((prediccion == 1) & (etiquetas == -1)))   # anomalía no vista

    # Precision = de lo que marcamos, cuánto era real; Recall = de las
    # anomalías reales, cuántas vimos; F1 = media armónica de ambas.
    p = tp / (tp + fp) if (tp + fp) else 0.0

    r = tp / (tp + fn) if (tp + fn) else 0.0

    f1 = (2 * p * r / (p + r)) if (p + r) else 0.0

    return tp, fp, tn, fn, p, r, f1


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

    # -----------------------------------------------------------------
    # PREPARACIÓN
    # -----------------------------------------------------------------
    # Cargamos los pkl que generó 01 (train: 3 corridas normales; test:
    # la corrida retenida) y reducimos X a las variables que sobrevivieron
    # la poda por correlación (02). flat() aplana cada ventana de 10
    # instantes en un único vector.
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

    # Ejemplo real: 16 variables × 10 instantes = 160 características.
    n_feat_ventana = X_train.shape[1]

    log(
        f"Train: {X_train.shape[0]} muestras x {n_feat_ventana} "
        f"características (ventana {train['ventana']})"
    )

    log(
        f"Test:  {X_test.shape[0]} muestras"
    )

    # -----------------------------------------------------------------
    # ENTRENAMIENTO: SOLO datos normales de referencia
    # -----------------------------------------------------------------
    # contamination="auto" → el modelo usa ~10 % del train (los más raros
    # de la referencia normal) como punto de comparación interno al fijar
    # su límite. random_state=SEED ⇒ resultados reproducibles.
    modelo = IsolationForest(
        random_state=config.SEED,
        contamination="auto"
    )

    modelo.fit(X_train)

    # GUARDAR con joblib: es el formato recomendado para objetos de
    # scikit-learn/numpy (rápido y confiable). En producción se cargan
    # estos dos archivos y se puntúan ventanas nuevas sin reentrenar.
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

    # -----------------------------------------------------------------
    # SCORES Y UMBRALES
    # -----------------------------------------------------------------
    # decision_function(): score ALTO = más "normal", score BAJO = más
    # anómalo (un punto suelto se aísla con pocas divisiones del árbol).
    scores_train = modelo.decision_function(X_train)

    scores_test = modelo.decision_function(X_test)

    # Umbrales dinámicos = percentiles de la distribución de scores NORMALES
    # de entrenamiento. Con q01 solo se alerta con los puntos del 1 % más
    # raro respecto al baseline ⇒ muy pocas falsas alarmas.
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

    # -----------------------------------------------------------------
    # EVALUACIÓN EN TEST: corrida de ANOMALIAS
    # -----------------------------------------------------------------
    # El test son las ventanas de la corrida de anomalías (carga5), con su
    # ground truth en carga5/anomalias_timeline.csv. El % de ventanas
    # marcadas aquí NO es un FPR: el TPR/FPR reales los calcula el paso 5
    # (05_diagnostico_resultados.py) cruzando con el timeline.
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
    # 5. SCORES DE ENTRENAMIENTO (referencia)
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
    # 6. IMPORTANCIA POR VARIABLE
    # --------------------------------------------------------

    # -----------------------------------------------------------------
    # IMPORTANCIA DE VARIABLES
    # -----------------------------------------------------------------
    # sklearn ≥ 1.9 ya NO expone feature_importances_ en IsolationForest.
    # Solución: promediar la importancia de cada árbol interno
    # (modelo.estimators_ es la lista de árboles construidos).
    importancias = np.mean(
        [
            tree.feature_importances_
            for tree in modelo.estimators_
        ],
        axis=0
    )

    # Traducimos índices → nombres de variables mantenidas.
    mant = [train["features"][i] for i in indice]

    v = config.VENTANA

    # Cada variable ocupa 10 posiciones CONSECUTIVAS en el vector aplanado
    # (una por instante de la ventana). Agregamos su importancia como
    # promedio de esas 10 posiciones → un número por variable de modelo.
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

    # --------------------------------------------------------
    # 7. RESUMEN
    # --------------------------------------------------------

    print("\n=== IsoForest SOBRE NORMAL (train) / ANOMALIAS (test) ===")

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