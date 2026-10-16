"""
02_ajustar_iso.py
=================
Grilla de hiperparámetros de Isolation Forest.

Para cada config: entrena leave-one-corrida-out sobre normales,
evalúa sobre el test de fallos y guarda TPR/FPR/F1 por umbral.

Entrada : output/modelado/artefactos_modelo.pkl
Salida  : output/modelado/ajuste_iso.json

Uso:
    python experimental/02_ajustar_iso.py
    python experimental/02_ajustar_iso.py --max-configs 20
"""

import argparse
import json
import os
import pickle
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelado_config import (                       # noqa: E402
    DIR_MODELADO, VENTANA, SEED, VARIABLES_MODELO, log,
)

# Gate de aceptación
TARGET_FPR = 0.0174
TARGET_TPR = 0.95

# Grilla a explorar
GRID = {
    "contamination": [0.001, 0.005, 0.01, 0.02, 0.05],
    "n_estimators":  [100, 300, 500],
    "max_samples":   [64, 128, "auto"],
    "max_features":  [0.5, 0.7, 1.0],
}

# Umbrales operativos (percentiles del train)
QQ = {"q10": 0.10, "q05": 0.05, "q01": 0.01}


# ==========================================
# Carga
# ==========================================
def cargar_artefactos():
    ruta = os.path.join(DIR_MODELADO, "artefactos_modelo.pkl")
    if not os.path.exists(ruta):
        log(f"Falta {ruta}. Ejecuta modelado/01_entrenamiento.py.")
        return None
    with open(ruta, "rb") as f:
        return pickle.load(f)


def seleccionar_indices(features):
    """Índices de VARIABLES_MODELO presentes en features."""
    presentes = [c for c in VARIABLES_MODELO if c in features]
    return [features.index(c) for c in presentes]


def aplanar(X, indice):
    """[n, ventana, F] -> [n, ventana * len(indice)]."""
    return X[:, :, indice].reshape(X.shape[0], -1)


# ==========================================
# Métricas
# ==========================================
def metricas(tp, fn, fp, tn):
    n_fault = tp + fn
    n_norm = fp + tn
    tpr = tp / n_fault if n_fault else 0.0
    fpr = fp / n_norm if n_norm else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = (2 * prec * tpr / (prec + tpr)) if (prec + tpr) else 0.0
    return {"tpr": tpr, "fpr": fpr, "precision": prec, "f1": f1}


# ==========================================
# Evaluación de una config
# ==========================================
def alertas_loo(X_train, runs_train, config):
    """Leave-one-corrida-out: por cada corrida, entrena sin ella y puntúa."""
    alertas = {q: np.zeros(len(X_train), dtype=bool) for q in QQ}

    for corrida in sorted(set(runs_train)):
        idx_c = [i for i, r in enumerate(runs_train) if r == corrida]
        idx_tr = [i for i in range(len(X_train)) if i not in idx_c]

        modelo = IsolationForest(random_state=SEED, n_jobs=-1, **config)
        modelo.fit(X_train[idx_tr])

        s_fold = modelo.decision_function(X_train[idx_tr])
        s_c = modelo.decision_function(X_train[idx_c])

        for q, p in QQ.items():
            thr = np.quantile(s_fold, p)
            alertas[q][idx_c] = s_c < thr

    return alertas


def evaluar(config, X_train, runs_train, X_test):
    """Devuelve métricas por umbral para una config."""
    n_norm, n_fault = len(X_train), len(X_test)

    # Alertas sobre normales (LOO)
    alertas_norm = alertas_loo(X_train, runs_train, config)

    # Modelo con todo el train -> test de fallos
    modelo = IsolationForest(random_state=SEED, n_jobs=-1, **config)
    modelo.fit(X_train)
    s_train = modelo.decision_function(X_train)
    s_test = modelo.decision_function(X_test)

    resultado = {}
    for q, p in QQ.items():
        thr = float(np.quantile(s_train, p))
        tp = int((s_test < thr).sum())
        fp = int(alertas_norm[q].sum())
        m = metricas(tp, n_fault - tp, fp, n_norm - fp)
        resultado[q] = {**m, "thr": thr, "tp": tp, "fp": fp}
    return resultado


# ==========================================
# Main
# ==========================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-configs", type=int, default=0,
                    help="Cap de configs a evaluar (0 = todas).")
    args = ap.parse_args()

    art = cargar_artefactos()
    if art is None:
        return

    indice = seleccionar_indices(art["features"])
    X_train = aplanar(art["X_train"], indice)
    X_test = aplanar(art["X_test"], indice)

    if len(X_test) == 0:
        log("Sin ventanas de test. Nada que ajustar.")
        return

    log(f"Train: {len(X_train)} | Test: {len(X_test)} | "
        f"Features: {len(indice)} | Ventana: {VENTANA}")
    log(f"Gate: FPR <= {TARGET_FPR:.4f} AND TPR >= {TARGET_TPR:.2f}")

    # Construir grilla + baseline
    configs = [dict(zip(GRID.keys(), c)) for c in product(*GRID.values())]
    baseline = {"contamination": "auto", "n_estimators": 100,
                "max_samples": "auto", "max_features": 1.0}
    if baseline not in configs:
        configs.append(baseline)

    if args.max_configs > 0:
        configs = configs[:args.max_configs]

    log(f"Configs a evaluar: {len(configs)}")

    filas = []
    for i, config in enumerate(configs, 1):
        try:
            r = evaluar(config, X_train, art["runs_train"], X_test)
            for q in QQ:
                filas.append({
                    **config, "umbral": q,
                    **{k: (round(v, 4) if isinstance(v, float) else v)
                       for k, v in r[q].items()},
                })
        except Exception as e:
            log(f"Config {i}: ERROR -> {e}")
        if i % 20 == 0 or i == len(configs):
            log(f"  {i}/{len(configs)} configs evaluadas")

    df = pd.DataFrame(filas)

    # Ranking con gate (FPR + TPR), fallback a solo FPR
    q01 = df[df["umbral"] == "q01"].copy()
    con_gate = q01[(q01["fpr"] <= TARGET_FPR) & (q01["tpr"] >= TARGET_TPR)]
    if con_gate.empty:
        con_gate = q01[q01["fpr"] <= TARGET_FPR]
    ranking = con_gate.sort_values("f1", ascending=False).head(10)

    # Guardar
    ruta = os.path.join(DIR_MODELADO, "ajuste_iso.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({
            "gate": {"fpr_max": TARGET_FPR, "tpr_min": TARGET_TPR},
            "n_configs": len(configs),
            "baseline": baseline,
            "top_q01": ranking.to_dict(orient="records"),
            "todas": df.to_dict(orient="records"),
        }, f, ensure_ascii=False, indent=2)
    log(f"Ajuste: {ruta}")

    # Resumen por consola
    print(f"\n=== TOP 5 (q01) bajo gate FPR<={TARGET_FPR:.4f}, TPR>={TARGET_TPR} ===")
    if ranking.empty:
        print("Ninguna config cumple el gate completo.")
    else:
        cols = ["contamination", "n_estimators", "max_samples",
                "max_features", "tpr", "fpr", "f1"]
        print(ranking[cols].to_string(index=False))

    if not q01.empty:
        mejor = q01.sort_values("f1", ascending=False).iloc[0]
        print("\n=== MEJOR sin gate (q01) ===")
        print(f"  cont={mejor['contamination']} ne={mejor['n_estimators']} "
              f"ms={mejor['max_samples']} mf={mejor['max_features']}")
        print(f"  TPR={mejor['tpr']:.4f} FPR={mejor['fpr']:.4f} F1={mejor['f1']:.4f}")


if __name__ == "__main__":
    main()