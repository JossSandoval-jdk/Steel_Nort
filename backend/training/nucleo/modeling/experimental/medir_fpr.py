"""
medir_fpr.py
============

FPR (tasa de falsas alarmas) del detector sobre tráfico NORMAL nunca visto,
mediante leave-one-corrida-out.

Motivación:
    El test del pipeline (dataset_muestras_test.pkl) solo contiene ventanas
    de FALLO, por lo que la tabla comparativa no puede reportar FPR.
    Medir FPR sobre las mismas corridas de entrenamiento sería circular:
    los umbrales q10/q05/q01 son percentiles de ese mismo train y por
    construcción marcarían ~10%/~5%/~1%.

Método:
    Para cada corrida normal C:
        - Reconstruye las ventanas CRUDAS (se invierte el StandardScaler
          global del pkl: X_raw = X * scale_ + mean_).
        - Escala y entrena IsolationForest SOLO con el resto de corridas.
        - Umbrales q10/q05/q01 derivados de ese fold-train.
        - Cuenta % de ventanas de C por debajo de cada umbral -> FPR_C.

    Reporta FPR medio por umbral. Un valor cercano al percentil (p.ej. q10
    -> ~10%) significa que el detector se comporta igual sobre normal nunca
    visto; muy por encima indica perfil distinto / sobre-ajuste del umbral.

    Se evalúa por defecto el pkl de modelado; para medir el modelo
    DESPLEGADO, apuntar STEELNORT_TRAIN_PKL al pkl de training/datasets/.

Salidas:
    training/output/modelado/deteccion/fpr_leave_one_out.csv
"""

import os
import pickle

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

import config

def cargar_muestras(ruta):
    with open(ruta, "rb") as f:
        return pickle.load(f)

def main():

    ruta_pkl = os.getenv(
        "STEELNORT_TRAIN_PKL",
        os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl"),
    )

    if not os.path.exists(ruta_pkl):
        print(f"[FPR] Falta {ruta_pkl}. Ejecuta 01_muestras.py.")
        return

    print(f"[FPR] Midiendo sobre: {ruta_pkl}")

    d = cargar_muestras(ruta_pkl)

    X = d["X"]
    runs = d["runs"]
    features = d["features"]
    scaler_g = d["scaler"]
    V = d["ventana"]
    F = len(features)

    if X.ndim != 3 or X.shape[1] != V:
        print(f"[FPR] Formato inesperado del pkl: {X.shape}. Cancela.")
        return

    raw = X * scaler_g.scale_ + scaler_g.mean_

    corridas = sorted(set(runs))

    filas = []

    for c in corridas:

        idx_c = [i for i, r in enumerate(runs) if r == c]

        if len(idx_c) < 1:
            continue

        idx_train_fold = [i for i in range(len(runs)) if i not in idx_c]

        Xc_raw = raw[idx_c]
        Xt_raw = raw[idx_train_fold]

        sc = StandardScaler()
        sc.fit(Xt_raw.reshape(-1, F))

        Xt = sc.transform(Xt_raw.reshape(-1, F)).reshape(-1, V, F)
        Xc = sc.transform(Xc_raw.reshape(-1, F)).reshape(-1, V, F)

        modelo = IsolationForest(
            random_state=config.SEED,
            contamination="auto",
            n_jobs=-1
        )
        modelo.fit(Xt.reshape(len(Xt), V * F))

        s_train = modelo.decision_function(Xt.reshape(len(Xt), V * F))

        umbrales = {
            "q10": np.quantile(s_train, 0.10),
            "q05": np.quantile(s_train, 0.05),
            "q01": np.quantile(s_train, 0.01),
        }

        s_c = modelo.decision_function(Xc.reshape(len(Xc), V * F))

        filas.append({
            "corrida": c,
            "ventanas": len(Xc),
            "fpr_q10": float((s_c < umbrales["q10"]).mean()),
            "fpr_q05": float((s_c < umbrales["q05"]).mean()),
            "fpr_q01": float((s_c < umbrales["q01"]).mean()),
        })

        print(
            f"  {c}: {len(Xc):3d} ventanas  ->  "
            f"FPR q10={filas[-1]['fpr_q10']:.1%}  "
            f"q05={filas[-1]['fpr_q05']:.1%}  "
            f"q01={filas[-1]['fpr_q01']:.1%}"
        )

    df = pd.DataFrame(filas)

    print("\n=== FPR MEDIO (sobre normal nunca visto) ===")

    medias = df[["fpr_q10", "fpr_q05", "fpr_q01"]].mean()

    for q, v in medias.items():
        print(f"  {q}: {v:.1%}")

    df.loc[len(df)] = {
        "corrida": "MEDIA",
        "ventanas": int(df["ventanas"].sum()),
        "fpr_q10": medias["fpr_q10"],
        "fpr_q05": medias["fpr_q05"],
        "fpr_q01": medias["fpr_q01"],
    }

    ruta_salida = os.path.join(
        config.DIR_DETECCION,
        "fpr_leave_one_out.csv"
    )

    os.makedirs(config.DIR_DETECCION, exist_ok=True)

    df.to_csv(ruta_salida, index=False, encoding="utf-8-sig")

    print(f"\n[FPR] Resultado en: {ruta_salida}")

if __name__ == "__main__":
    main()