"""
01_entrenamiento.py
===================
Construye muestras, analiza correlación y entrena Isolation Forest.

Entrada : output/preparado/dataset_steelnort.parquet
Salida  : output/modelado/
            - artefactos_modelo.pkl
            - correlacion.json
            - modelo_isolation_forest.joblib
            - scaler.joblib
"""

import json
import os
import pickle

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from modelado_config import (
    DATASET_PRINCIPALES, DIR_MODELADO, VENTANA, SEED,
    VARIABLES_MODELO, COLUMNAS_CONTEXTO,
    UMBRAL_CORRELACION_INDICADOR,
    corridas_entrenamiento, corridas_anomalia, log,
)


# ==========================================
# Ventanas deslizantes
# ==========================================
def ventanas_por_corrida(df, n):
    """Ventanas de n filas consecutivas por corrida."""
    df = df.sort_values("timestamp").reset_index(drop=True)
    if len(df) < n:
        return []
    return [df.iloc[i:i + n] for i in range(len(df) - n + 1)]


def construir_muestras(datos, corridas, features, n):
    """Devuelve (X, runs, ventanas) concatenando todas las corridas."""
    xs, runs, ventanas = [], [], []
    for corrida in corridas:
        sub = datos[datos["run_name"] == corrida]
        for w in ventanas_por_corrida(sub, n):
            xs.append(w[features].to_numpy(dtype="float64"))
            runs.append(corrida)
            ventanas.append({
                "run": corrida,
                "inicio": str(w["timestamp"].iloc[0]),
                "fin": str(w["timestamp"].iloc[-1]),
                "n": len(w),
            })
    if not xs:
        return np.empty((0, n, len(features))), [], []
    return np.stack(xs), runs, ventanas


# ==========================================
# Correlación
# ==========================================
def pares_correlacionados(corr_p, corr_s, umbral):
    """Pares (triangular superior) con |r| >= umbral."""
    cols = list(corr_p.columns)
    return [
        {"var_a": a, "var_b": b,
         "pearson": round(corr_p.loc[a, b], 4),
         "spearman": round(corr_s.loc[a, b], 4)}
        for i, a in enumerate(cols)
        for j, b in enumerate(cols)
        if j > i and (abs(corr_p.loc[a, b]) >= umbral
                      or abs(corr_s.loc[a, b]) >= umbral)
    ]


def vif(df):
    """VIF por variable (>10 = colinealidad fuerte)."""
    cols = list(df.columns)
    n, p = df.shape
    if p <= 1:
        return {c: 1.0 for c in cols}
    X = df.to_numpy(dtype=float)
    out = {}
    for k, c in enumerate(cols):
        y = X[:, k]
        Xo = np.column_stack([np.ones(n)] + [X[:, j] for j in range(p) if j != k])
        beta, *_ = np.linalg.lstsq(Xo, y, rcond=None)
        ss_res = float(np.sum((y - Xo @ beta) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot else 0
        out[c] = round(1 / (1 - r2) if r2 < 1 else np.inf, 2)
    return out


def analizar_correlacion(train, features):
    """Pares correlacionados + VIF + reglas de referencia (p90/p95/p99)."""
    num = train[features].apply(pd.to_numeric, errors="coerce").fillna(0)
    corr_p = num.corr(method="pearson")
    corr_s = num.corr(method="spearman")
    pares = pares_correlacionados(corr_p, corr_s, UMBRAL_CORRELACION_INDICADOR)
    vifs = vif(num[VARIABLES_MODELO])
    reglas = pd.DataFrame({
        "columna": VARIABLES_MODELO,
        "p90": np.percentile(num[VARIABLES_MODELO], 90, axis=0),
        "p95": np.percentile(num[VARIABLES_MODELO], 95, axis=0),
        "p99": np.percentile(num[VARIABLES_MODELO], 99, axis=0),
    }).to_dict(orient="records")
    return {
        "pares": pares,
        "vif": [{"columna": c, "vif": vifs[c]} for c in VARIABLES_MODELO],
        "reglas_umbrales": reglas,
        "variables_modelo": VARIABLES_MODELO,
    }


# ==========================================
# Importancia de variables
# ==========================================
def calcular_importancias(modelo, variables, n_features, ventana):
    """Importancia media por variable (agregando sus posiciones en la ventana)."""
    imps = np.mean([t.feature_importances_ for t in modelo.estimators_], axis=0)
    filas = []
    for i, c in enumerate(variables):
        if i >= n_features:
            break
        bloque = imps[i * ventana:(i + 1) * ventana]
        filas.append({"columna": c, "importancia": float(np.abs(bloque).mean())})
    return sorted(filas, key=lambda x: x["importancia"], reverse=True)


# ==========================================
# Main
# ==========================================
def main():
    if not os.path.exists(DATASET_PRINCIPALES):
        log(f"Falta {DATASET_PRINCIPALES}. Ejecuta pipeline/03_preparacion.py.")
        return

    datos = pd.read_parquet(DATASET_PRINCIPALES)
    features = [c for c in datos.columns if c not in COLUMNAS_CONTEXTO]
    log(f"Dataset: {len(datos)} filas × {len(features)} variables")

    # Split por corrida
    todas = set(datos["run_name"].unique())
    train_runs = corridas_entrenamiento(todas)
    test_runs = sorted(set(corridas_anomalia()) & todas)
    log(f"Train: {train_runs}")
    log(f"Test : {test_runs}")

    if not train_runs:
        log("Sin corridas de entrenamiento.")
        return

    # --- Correlación sobre train ---
    train_df = datos[datos["run_name"].isin(train_runs)]
    correlacion = analizar_correlacion(train_df, features)
    os.makedirs(DIR_MODELADO, exist_ok=True)
    with open(os.path.join(DIR_MODELADO, "correlacion.json"), "w",
              encoding="utf-8") as f:
        json.dump(correlacion, f, ensure_ascii=False, indent=2)
    log(f"Correlación: {len(correlacion['pares'])} pares con |r| >= "
        f"{UMBRAL_CORRELACION_INDICADOR}")

    # --- Ventanas ---
    X_train, runs_train, vent_train = construir_muestras(
        datos, train_runs, features, VENTANA)
    X_test, runs_test, vent_test = construir_muestras(
        datos, test_runs, features, VENTANA)
    log(f"Ventanas train: {len(X_train)} | test: {len(X_test)}")

    if len(X_train) == 0:
        log("Sin ventanas de entrenamiento.")
        return

    # --- Scaler ---
    scaler = StandardScaler().fit(X_train.reshape(-1, X_train.shape[2]))

    def norm(X):
        return scaler.transform(X.reshape(-1, X.shape[2])).reshape(X.shape)

    X_train_n = norm(X_train)
    X_test_n = norm(X_test) if len(X_test) else np.empty((0,) + X_train.shape[1:])

    # --- Isolation Forest (solo variables del modelo) ---
    idx = [features.index(c) for c in VARIABLES_MODELO if c in features]
    def flat(X):
        return X[:, :, idx].reshape(X.shape[0], X.shape[1] * len(idx))

    modelo = IsolationForest(random_state=SEED, contamination="auto")
    modelo.fit(flat(X_train_n))
    log("Isolation Forest entrenado.")

    # Scores y umbrales
    s_train = modelo.decision_function(flat(X_train_n))
    s_test = modelo.decision_function(flat(X_test_n)) if len(X_test) else np.empty(0)
    umbrales = {q: float(np.quantile(s_train, p))
                for q, p in (("q10", 0.10), ("q05", 0.05), ("q01", 0.01))}
    log(f"Umbrales: q10={umbrales['q10']:.4f} "
        f"q05={umbrales['q05']:.4f} q01={umbrales['q01']:.4f}")

    # Importancias
    importancia = calcular_importancias(modelo, VARIABLES_MODELO, len(idx), VENTANA)

    # --- Guardar ---
    joblib.dump(modelo, os.path.join(DIR_MODELADO, "modelo_isolation_forest.joblib"))
    joblib.dump(scaler, os.path.join(DIR_MODELADO, "scaler.joblib"))

    with open(os.path.join(DIR_MODELADO, "artefactos_modelo.pkl"), "wb") as f:
        pickle.dump({
            "X_train": X_train_n, "X_test": X_test_n,
            "runs_train": runs_train, "runs_test": runs_test,
            "ventanas_train": vent_train, "ventanas_test": vent_test,
            "features": features, "variables_modelo": VARIABLES_MODELO,
            "scaler": scaler, "modelo": modelo,
            "scores_train": s_train, "scores_test": s_test,
            "umbrales": umbrales, "importancia": importancia,
            "ventana": VENTANA,
        }, f)
    log(f"Artefactos guardados en: {DIR_MODELADO}")


if __name__ == "__main__":
    main()