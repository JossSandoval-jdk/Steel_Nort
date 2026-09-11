"""
01_muestras.py
==============

Construye las observaciones (muestras) usadas por el detector,
adaptando la metodología de DBPA (dataset.py):

    1. Genera ventanas deslizantes de VENTANA muestras temporales
       (por defecto 10) sobre TODAS las corridas.
    2. Mezcla aleatoriamente todas las muestras generadas.
    3. Divide 70% train / 30% test de TODAS las muestras.
    4. Normaliza con StandardScaler ajustado SOLO sobre el
       conjunto de entrenamiento.
    5. Guarda un pickle con las muestras normalizadas.

Salidas (en <OUTPUT>/modelado/):
    dataset_muestras_train.pkl
    dataset_muestras_test.pkl
    resumen_muestras.csv
"""

import os
import pickle

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

import config
import util_normalizacion


def log(msg):
    print(f"[MUESTRAS] {msg}", flush=True)


def ventanas_por_corrida(df_corrida, n=config.VENTANA):
    """
    Genera ventanas deslizantes de n filas consecutivas
    ordenadas por timestamp dentro de una corrida.
    """

    # Ordenamos por timestamp para que la secuencia tenga sentido
    # (una fila = un instante de muestreo) y reseteamos el índice,
    # porque la ventana deslizante trabaja por POSICIÓN (iloc).
    df_corrida = (
        df_corrida
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    # Una ventana necesita n filas consecutivas. Si la corrida tiene
    # menos de n muestras, no se puede formar ni una sola ventana.
    if len(df_corrida) < n:
        return []

    ventanas = []

    # Desplazamos un "marco" de n filas de a una posición:
    #   inicio=0 → filas 0..n-1 ; inicio=1 → filas 1..n ; ...
    # Número de ventanas posibles = len(df) - n + 1.
    for inicio in range(len(df_corrida) - n + 1):

        ventanas.append(df_corrida.iloc[inicio:inicio + n])

    return ventanas


def construir_muestras(datos, corridas, features):
    """
    Devuelve (X, runs, ventanas) donde X tiene forma [n, VENTANA, F]
    y ventanas es la lista de sub-dataframes con su timestamp.
    """

    todas_x = []
    todos_run = []
    todas_ventanas = []

    # CLAVE ANTIFUGA: las ventanas NUNCA cruzan entre corridas, porque
    # ventanas_por_corrida() trabaja sobre UNA corrida a la vez. Así el
    # split train/test por corrida no deja filtraciones de información
    # temporal entre muestras vecinas.
    for corrida in corridas:

        if corrida not in datos["run_name"].values:
            continue

        df_c = datos[datos["run_name"] == corrida]

        for w in ventanas_por_corrida(df_c):

            # Cada ventana w es un mini-dataframe de n filas; extraemos
            # SOLO las variables (sin timestamp/run_name).
            x = w[features].to_numpy(dtype="float64")

            todas_x.append(x)

            todos_run.append(corrida)

            # Guardamos además la metadata temporal de la ventana para
            # poder localizar cada observación en las alertas.
            todas_ventanas.append({
                "run": corrida,
                "inicio": str(w["timestamp"].iloc[0]),
                "fin": str(w["timestamp"].iloc[-1]),
                "n": len(w),
            })

    if not todas_x:
        return (np.empty((0, config.VENTANA, len(features))),
                [], [])

    # np.stack une todas las ventanas en UN array 3D:
    # forma final = [n_muestras, VENTANA, F] → (muestra, instante, variable)
    X = np.stack(todas_x)

    return X, todos_run, todas_ventanas


def main():

    # --------------------------------------------------------
    # 1. CARGAR DATASET FINAL
    # --------------------------------------------------------

    if not os.path.exists(config.DATASET_PRINCIPALES):

        log(
            f"Falta el dataset: {config.DATASET_PRINCIPALES}. "
            "Ejecuta data_preparation 00-06."
        )

        return

    datos = pd.read_csv(
        config.DATASET_PRINCIPALES,
        encoding="utf-8-sig"
    )

    features = [
        c
        for c in datos.columns
        if c not in config.COLUMNAS_CONTEXTO
    ]

    log(
        f"Dataset cargado: {len(datos)} filas x "
        f"{len(features)} variables principales"
    )

    if config.NORMALIZACION_RELATIVA:

        datos = util_normalizacion.transformar_relativo(
            datos, features
        )

        log(
            "Normalización RELATIVA por corrida aplicada "
            "(baseline interno por corrida)"
        )

    # --------------------------------------------------------
    # 2. VENTANAS DE TODAS LAS CORRIDAS
    # --------------------------------------------------------

    todas_corridas = sorted(
        datos["run_name"].unique()
    )

    log(
        f"Corridas disponibles: {todas_corridas}"
    )

    X_all, runs_all, ventanas_all = construir_muestras(
        datos, todas_corridas, features
    )

    log(
        f"Total de muestras generadas: {len(X_all)}"
    )

    if len(X_all) == 0:

        log("No se generaron muestras.")
        return

    # --------------------------------------------------------
    # 3. SPLIT 70/30 ALEATORIO
    # --------------------------------------------------------

    rng = np.random.RandomState(config.SEED)

    indices = rng.permutation(len(X_all))

    n_train = int(len(X_all) * config.FRACCION_TRAIN)

    idx_train = indices[:n_train]
    idx_test = indices[n_train:]

    X_train = X_all[idx_train]
    X_test = X_all[idx_test]

    runs_train = [runs_all[i] for i in idx_train]
    runs_test = [runs_all[i] for i in idx_test]

    ventanas_train = [ventanas_all[i] for i in idx_train]
    ventanas_test = [ventanas_all[i] for i in idx_test]

    log(
        f"Train: {len(X_train)} muestras "
        f"({len(X_train)/len(X_all)*100:.1f}%)"
    )

    log(
        f"Test:  {len(X_test)} muestras "
        f"({len(X_test)/len(X_all)*100:.1f}%)"
    )

    # --------------------------------------------------------
    # 4. NORMALIZACIÓN (solo sobre train)
    # --------------------------------------------------------

    n_train_dim, n_ventana, n_feat = X_train.shape

    scaler = StandardScaler()

    scaler.fit(
        X_train.reshape(-1, n_feat)
    )

    X_train_n = (
        scaler.transform(X_train.reshape(-1, n_feat))
        .reshape(n_train_dim, n_ventana, n_feat)
    )

    n_test = len(X_test)

    if n_test:

        X_test_n = (
            scaler.transform(X_test.reshape(-1, n_feat))
            .reshape(n_test, n_ventana, n_feat)
        )

    else:

        X_test_n = np.empty((0, n_ventana, n_feat))

    # --------------------------------------------------------
    # 5. GUARDAR
    # --------------------------------------------------------

    os.makedirs(config.DIR_MODELADO, exist_ok=True)

    with open(
        os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl"),
        "wb"
    ) as f:

        pickle.dump({
            "X": X_train_n,
            "runs": runs_train,
            "ventanas": ventanas_train,
            "features": features,
            "scaler": scaler,
            "ventana": n_ventana,
        }, f)

    with open(
        os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl"),
        "wb"
    ) as f:

        pickle.dump({
            "X": X_test_n,
            "runs": runs_test,
            "ventanas": ventanas_test,
            "features": features,
            "scaler": scaler,
            "ventana": n_ventana,
        }, f)

    resumen = (
        pd.DataFrame(ventanas_train + ventanas_test)
    )

    resumen.to_csv(
        os.path.join(config.DIR_MODELADO, "resumen_muestras.csv"),
        index=False,
        encoding="utf-8-sig"
    )

    log(f"Muestras guardadas en: {config.DIR_MODELADO}")


if __name__ == "__main__":
    main()