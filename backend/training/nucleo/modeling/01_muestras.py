"""
01_muestras.py
==============

Construye las observaciones (muestras) usadas por el detector:

    1. Deduplica corridas (cargaX/runX repetidos) y descarta corridas
       de anomalia cuyo timeline no solapa sus datos.
    2. Genera ventanas deslizantes de VENTANA muestras temporales
       (por defecto 10) sobre las corridas.
    3. Train = TODAS las corridas normales; Test = las corridas de
       anomalia validas (el split NO es aleatorio, es por corrida).
    4. Normaliza con StandardScaler ajustado SOLO sobre el conjunto
       de entrenamiento.
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

def _deduplicar_corridas(datos):
    """
    Detecta corridas duplicadas (misma cantidad de filas y el mismo rango
    de timestamps, p.ej. carga1/run1, carga3/run3) y devuelve
    (conservadas, descartadas). Se prefiere el nombre no 'run*'.
    """
    ts = pd.to_datetime(datos["timestamp"])
    resumen = pd.DataFrame({
        "run": datos["run_name"].values,
        "ts": ts.values,
    }).groupby("run")["ts"].agg(["size", "min", "max"])
    resumen.columns = ["n", "desde", "hasta"]

    por_fingerprint = {}
    for run, fila in resumen.iterrows():
        clave = (int(fila["n"]), fila["desde"], fila["hasta"])
        por_fingerprint.setdefault(clave, []).append(run)

    conservadas, descartadas = [], []
    for runs in por_fingerprint.values():
        if len(runs) == 1:
            conservadas.append(runs[0])
            continue
        canonical = sorted(runs, key=lambda r: (r.startswith("run"), r))[0]
        conservadas.append(canonical)
        descartadas.extend(r for r in runs if r != canonical)

    return conservadas, descartadas

def _leer_timeline(corrida):
    """Timeline de fallo de una corrida en anomalias/ o en la raiz."""
    for grupo in ("anomalias", ""):
        ruta = os.path.join(config.OUTPUT_BASE, grupo, corrida, "anomalias_timeline.csv")
        if os.path.isfile(ruta):
            tl = pd.read_csv(ruta, encoding="utf-8-sig")
            tl["inicio"] = pd.to_datetime(tl["inicio"])
            tl["fin"] = pd.to_datetime(tl["fin"])
            return tl
    return None

def _corridas_test_validas(datos, candidatas):
    """
    Solo son test válido las corridas cuyo timeline de fallo SOLAPE sus
    datos. Si el timeline 'no existe o no coincide' (captura fantasma),
    la corrida se descarta: sus ventanas no aportan etiquetas de fault
    fiables y solo contaminan FPR/TPR.
    """
    validas = []
    for corrida in candidatas:
        sub = pd.to_datetime(datos.loc[datos["run_name"] == corrida, "timestamp"])
        if sub.empty:
            continue
        tl = _leer_timeline(corrida)
        if tl is None:
            log(f"Test descartado: {corrida} (sin anomalias_timeline.csv)")
            continue
        desde_c, hasta_c = sub.min(), sub.max()
        solapa = any(
            pd.Timestamp(f["inicio"]) <= hasta_c and pd.Timestamp(f["fin"]) >= desde_c
            for _, f in tl.iterrows()
        )
        if not solapa:
            log(
                f"Test descartado: {corrida} "
                f"(datos {desde_c}->{hasta_c}; timeline no solapa)"
            )
            continue
        validas.append(corrida)
    return validas

def ventanas_por_corrida(df_corrida, n=config.VENTANA):
    """
    Genera ventanas deslizantes de n filas consecutivas
    ordenadas por timestamp dentro de una corrida.
    """

    df_corrida = (
        df_corrida
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    if len(df_corrida) < n:
        return []

    ventanas = []

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

    for corrida in corridas:

        if corrida not in datos["run_name"].values:
            continue

        df_c = datos[datos["run_name"] == corrida]

        for w in ventanas_por_corrida(df_c):

            x = w[features].to_numpy(dtype="float64")

            todas_x.append(x)

            todos_run.append(corrida)

            todas_ventanas.append({
                "run": corrida,
                "inicio": str(w["timestamp"].iloc[0]),
                "fin": str(w["timestamp"].iloc[-1]),
                "n": len(w),
            })

    if not todas_x:
        return (np.empty((0, config.VENTANA, len(features))),
                [], [])

    X = np.stack(todas_x)

    return X, todos_run, todas_ventanas

def main():

    if not os.path.exists(config.DATASET_PRINCIPALES):

        log(
            f"Falta el dataset: {config.DATASET_PRINCIPALES}. "
            "Ejecuta data_preparation 00-04."
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

    conservadas, descartadas = _deduplicar_corridas(datos)
    if descartadas:
        log(f"Corridas duplicadas descartadas: {sorted(descartadas)}")
        datos = datos[datos["run_name"].isin(conservadas)]

    if config.NORMALIZACION_RELATIVA:

        datos = util_normalizacion.transformar_relativo(
            datos, features
        )

        log(
            "Normalización RELATIVA por corrida aplicada "
            "(baseline interno por corrida)"
        )

    todas_corridas = set(datos["run_name"].unique())

    corridas_anom = set(config.corridas_anomalia())
    corridas_train = [
        c for c in todas_corridas
        if c not in corridas_anom
        and c not in config.CORRIDAS_NO_BASE_SANA
    ]

    excluidas = sorted(set(config.CORRIDAS_NO_BASE_SANA) & todas_corridas)
    if excluidas:
        log(
            f"Excluidas del train (no línea base sana): {excluidas}"
        )

    corridas_test = _corridas_test_validas(
        datos,
        [c for c in config.corridas_anomalia() if c in todas_corridas],
    )

    log(f"Corridas disponibles: {sorted(todas_corridas)}")
    log(f"Train (solo normal): {corridas_train}")
    log(f"Test  (solo anomalias): {corridas_test}")

    if not corridas_train:
        log("Sin corridas normales de entrenamiento. Verifica "
            "CORRIDAS_ENTRENAMIENTO en config.py.")
        return

    if not corridas_test:
        log("Aviso: no hay corrida de anomalías (con timeline) para test.")

    X_train, runs_train, ventanas_train = construir_muestras(
        datos, corridas_train, features
    )

    X_test, runs_test, ventanas_test = construir_muestras(
        datos, corridas_test, features
    )

    log(f"Train: {len(X_train)} muestras (corridas normales)")
    log(f"Test:  {len(X_test)} muestras (corrida de anomalias)")

    if 0 < len(X_train) < 200:
        log(
            f"ADVERTENCIA: {len(X_train)} ventanas de train es INSUFICIENTE "
            "para unas 190 características. El modelo resultante será débil "
            "(TPR bajo) y NO debe desplegarse. Genera más capturas normales "
            "con tools/simular_carga.py antes de reentrenar."
        )

    if len(X_train) == 0:
        log("No se generaron muestras de entrenamiento.")
        return

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
