"""
01_muestras.py
==============

Construye las observaciones (muestras) del detector:

    1. Deduplica corridas repetidas y descarta corridas de anomalía
       cuyo timeline no solapa sus datos.
    2. Genera ventanas deslizantes de VENTANA muestras (por defecto 10)
       sobre cada corrida, ordenadas por timestamp.
    3. Train = TODAS las corridas normales; Test = las corridas de
       anomalía válidas (el split es por corrida, no aleatorio).
    4. Normaliza con StandardScaler ajustado SOLO sobre el train.
    5. Guarda los pkl de muestras normalizadas + el resumen CSV.

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
    """Corridas duplicadas (mismo nº de filas y mismo rango temporal)
    quedan una sola vez; se prefiere el nombre que NO es 'run*'."""
    ts = pd.to_datetime(datos["timestamp"])
    resumen = datos.assign(ts=ts).groupby("run_name")["ts"].agg([
        "size", "min", "max"])

    conservadas, descartadas = [], []
    for clave, runs in resumen.groupby(["size", "min", "max"]).groups.items():
        runs = list(runs)
        if len(runs) == 1:
            conservadas.append(runs[0])
            continue
        canonical = sorted(runs, key=lambda r: (r.startswith("run"), r))[0]
        conservadas.append(canonical)
        descartadas.extend(r for r in runs if r != canonical)
    return conservadas, descartadas


def _leer_timeline(corrida):
    """Timeline de fallo de una corrida (en anomalias/ o en la raíz)."""
    for grupo in ("anomalias", ""):
        ruta = os.path.join(config.OUTPUT_BASE, grupo, corrida,
                            "anomalias_timeline.csv")
        if os.path.isfile(ruta):
            tl = pd.read_csv(ruta, encoding="utf-8-sig")
            tl["inicio"] = pd.to_datetime(tl["inicio"])
            tl["fin"] = pd.to_datetime(tl["fin"])
            return tl
    return None


def _corridas_test_validas(datos, candidatas):
    """Solo son test válido las corridas cuyo timeline de fallo solape
    sus datos; el resto (capturas fantasma) se descarta."""
    validas = []
    for corrida in candidatas:
        sub = pd.to_datetime(datos.loc[datos["run_name"] == corrida, "timestamp"])
        if sub.empty:
            continue
        tl = _leer_timeline(corrida)
        if tl is None:
            log(f"Test descartado: {corrida} (sin anomalias_timeline.csv)")
            continue
        solapa = any(
            pd.Timestamp(f["inicio"]) <= sub.max()
            and pd.Timestamp(f["fin"]) >= sub.min()
            for _, f in tl.iterrows()
        )
        if not solapa:
            log(f"Test descartado: {corrida} (timeline no solapa sus datos)")
            continue
        validas.append(corrida)
    return validas


def ventanas_por_corrida(df_corrida, n=config.VENTANA):
    """Ventanas deslizantes de n filas consecutivas por corrida."""
    df_corrida = df_corrida.sort_values("timestamp").reset_index(drop=True)
    if len(df_corrida) < n:
        return []
    return [df_corrida.iloc[i:i + n]
            for i in range(len(df_corrida) - n + 1)]


def construir_muestras(datos, corridas, features):
    """Devuelve (X, runs, ventanas) con X de forma [n, VENTANA, F]."""
    todas_x, todos_run, todas_ventanas = [], [], []
    for corrida in corridas:
        if corrida not in datos["run_name"].values:
            continue
        for w in ventanas_por_corrida(datos[datos["run_name"] == corrida]):
            todas_x.append(w[features].to_numpy(dtype="float64"))
            todos_run.append(corrida)
            todas_ventanas.append({
                "run": corrida,
                "inicio": str(w["timestamp"].iloc[0]),
                "fin": str(w["timestamp"].iloc[-1]),
                "n": len(w),
            })
    if not todas_x:
        return np.empty((0, config.VENTANA, len(features))), [], []
    return np.stack(todas_x), todos_run, todas_ventanas


def main():
    if not os.path.exists(config.DATASET_PRINCIPALES):
        log(f"Falta el dataset: {config.DATASET_PRINCIPALES}. "
            "Ejecuta data_preparation 00-04.")
        return

    datos = pd.read_csv(config.DATASET_PRINCIPALES, encoding="utf-8-sig")
    features = [c for c in datos.columns if c not in config.COLUMNAS_CONTEXTO]
    log(f"Dataset cargado: {len(datos)} filas x {len(features)} variables")

    conservadas, descartadas = _deduplicar_corridas(datos)
    if descartadas:
        log(f"Corridas duplicadas descartadas: {sorted(descartadas)}")
        datos = datos[datos["run_name"].isin(conservadas)]

    if config.NORMALIZACION_RELATIVA:
        datos = util_normalizacion.transformar_relativo(datos, features)
        log("Normalización RELATIVA por corrida aplicada")

    todas_corridas = set(datos["run_name"].unique())
    corridas_train = config.corridas_entrenamiento(todas_corridas)
    corridas_test = _corridas_test_validas(
        datos, [c for c in config.corridas_anomalia() if c in todas_corridas])

    log(f"Corridas disponibles: {sorted(todas_corridas)}")
    log(f"Train (solo normal): {corridas_train}")
    log(f"Test  (solo anomalias): {corridas_test}")

    if not corridas_train:
        log("Sin corridas normales de entrenamiento. "
            "Verifica CORRIDAS_ENTRENAMIENTO en config.py.")
        return
    if not corridas_test:
        log("Aviso: no hay corrida de anomalías (con timeline) para test.")

    X_train, runs_train, ventanas_train = construir_muestras(
        datos, corridas_train, features)
    X_test, runs_test, ventanas_test = construir_muestras(
        datos, corridas_test, features)
    log(f"Train: {len(X_train)} muestras | Test: {len(X_test)} muestras")

    if len(X_train) == 0:
        log("No se generaron muestras de entrenamiento.")
        return
    if 0 < len(X_train) < 200:
        log(f"ADVERTENCIA: {len(X_train)} ventanas de train es insuficiente "
            "para ~190 características; el modelo será débil (TPR bajo). "
            "Genera más capturas normales antes de reentrenar.")

    scaler = StandardScaler().fit(X_train.reshape(-1, X_train.shape[2]))
    X_train_n = scaler.transform(X_train.reshape(-1, X_train.shape[2])
                                  ).reshape(X_train.shape)
    if len(X_test):
        X_test_n = scaler.transform(X_test.reshape(-1, X_test.shape[2])
                                    ).reshape(X_test.shape)
    else:
        X_test_n = np.empty((0,) + X_train.shape[1:])

    os.makedirs(config.DIR_MODELADO, exist_ok=True)

    def guardar(nombre, X_n, runs, ventanas):
        with open(os.path.join(config.DIR_MODELADO, nombre), "wb") as f:
            pickle.dump({
                "X": X_n,
                "runs": runs,
                "ventanas": ventanas,
                "features": features,
                "scaler": scaler,
                "ventana": X_train.shape[1],
            }, f)

    guardar("dataset_muestras_train.pkl", X_train_n, runs_train, ventanas_train)
    guardar("dataset_muestras_test.pkl", X_test_n, runs_test, ventanas_test)

    resumen = pd.DataFrame(ventanas_train + ventanas_test)
    resumen.to_csv(os.path.join(config.DIR_MODELADO, "resumen_muestras.csv"),
                   index=False, encoding="utf-8-sig")
    log(f"Muestras guardadas en: {config.DIR_MODELADO}")


if __name__ == "__main__":
    main()