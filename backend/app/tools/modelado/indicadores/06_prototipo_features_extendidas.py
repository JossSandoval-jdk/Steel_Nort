"""
06_prototipo_features_extendidas.py
===================================
PROTOTIPO — solo medicion, NO toca produccion.

Hipotesis: el tipo de fallo NO se aprende porque las 25 features del modelo
NO incluyen las variables que definen cada fallo (wait_lck_count, wait_io_count,
wait_log_count, page_reads, total_reads/writes, query_count...). El dataset
preparado SI trae columnas relacionadas (locks por tabla, page_reads_per_sec,
rollbacks_per_sec, sql_compilations_per_sec...).

Se re-mide lo mismo que 07 (LORO, RandomForest) cambiando solo el conjunto de
features: base25 vs extendida. Si la extendida sube fuerte, la causa raiz es la
instrumentacion del feature set, no el algoritmo.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

_AQUI = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("eval05", _AQUI / "03_evaluar_oe3.py")
_eval05 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_eval05)

sys.path.insert(0, str(_AQUI.parent))
from modelado_config import (                       # noqa: E402
    DATASET_PRINCIPALES, DIR_MODELADO, VARIABLES_MODELO, log,
)
from etiquetas import etiquetas_corridas              # noqa: E402

DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")
VENTANA = 10
META = {"timestamp", "run_name", "experiment_id", "carpeta", "etiqueta_manual"}


def columnas_extendidas(ds):
    """Numericas utiles: sin metadatos y sin las interacciones ``_x``."""
    return [c for c in ds.columns
            if c not in META and not c.endswith("_x")
            and pd.api.types.is_numeric_dtype(ds[c])]


def ventanas_de(sub, cols):
    sub = sub.sort_values("timestamp").reset_index(drop=True)
    crudo = sub[cols].astype(float).to_numpy()
    ts = pd.to_datetime(sub["timestamp"]).to_numpy()
    salida = []
    for i in range(VENTANA - 1, len(sub)):
        salida.append({
            "ini": pd.Timestamp(ts[i - VENTANA + 1]),
            "fin": pd.Timestamp(ts[i]),
            "feat": crudo[i - VENTANA + 1:i + 1].mean(axis=0),
        })
    return salida


def main():
    tl = _eval05.cargar_timelines()
    ds = pd.read_parquet(DATASET_PRINCIPALES)
    etiq = etiquetas_corridas()
    ext_cols = columnas_extendidas(ds)
    log(f"Features: base={len(VARIABLES_MODELO)} | extendida={len(ext_cols)}")

    conjuntos = {"base25": VARIABLES_MODELO, "extendida": ext_cols}
    datos = {}
    for nombre, cols in conjuntos.items():
        normales, fallos = [], []
        for run, sub in ds.groupby("run_name"):
            ventanas = ventanas_de(sub, cols)
            es_normal = etiq.get(run, "anomalia") == "normal"
            for w in ventanas:
                fila = {"run": run, "feat": w["feat"]}
                if es_normal:
                    normales.append({**fila, "label": "normal"})
                    continue
                for _, f in tl[tl["run_name"] == run].iterrows():
                    if w["ini"] <= f["fin"] and w["fin"] >= f["inicio"]:
                        fallos.append({**fila, "label": f["tipo"]})
                        break
        datos[nombre] = (normales, fallos)

    runs_anom = sorted(tl["run_name"].unique())

    def evaluar(normales, fallos, con_normal):
        aciertos = total = 0
        conf = {}
        for run in runs_anom:
            train = (normales if con_normal else []) + \
                    [p for p in fallos if p["run"] != run]
            test = [p for p in fallos if p["run"] == run]
            if not test or len({p["label"] for p in train}) < 2:
                continue
            Xtr = np.array([p["feat"] for p in train], dtype=float)
            ytr = [p["label"] for p in train]
            Xte = np.array([p["feat"] for p in test], dtype=float)
            clf = RandomForestClassifier(n_estimators=300, random_state=0,
                                         class_weight="balanced")
            clf.fit(Xtr, ytr)
            for p, yhat in zip(test, clf.predict(Xte)):
                total += 1
                ok = int(yhat == p["label"])
                aciertos += ok
                conf.setdefault(p["label"], {}).setdefault(yhat, 0)
                conf[p["label"]][yhat] += 1
        return (round(aciertos / total, 4) if total else None), total, conf

    metricas = {}
    for nombre, (normales, fallos) in datos.items():
        for esc, con_normal in (("con_normal", True), ("solo_tipos", False)):
            acc, total, conf = evaluar(normales, fallos, con_normal)
            metricas[f"{nombre}_{esc}"] = {
                "accuracy_tipo": acc, "ventanas": total, "matriz_confusion": conf,
            }
            log(f"LORO {nombre}_{esc}: {acc} sobre {total} ventanas")

    resumen = {
        "clasificador": "RandomForest(300, balanced)",
        "validacion": "leave-one-run-out (corridas anomalas)",
        "features_base": list(VARIABLES_MODELO),
        "features_extendidas": ext_cols,
        "metricas": metricas,
        "nota": ("Prototipo de medicion: no modifica produccion. Mide el impacto "
                 "de AGREGAR las variables que definen cada fallo."),
    }
    os.makedirs(DIR_VAL, exist_ok=True)
    ruta = os.path.join(DIR_VAL, "prototipo_features_extendidas.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"resumen": resumen}, fh, ensure_ascii=False, indent=2, default=str)

    print("\n=== PROTOTIPO: features base vs extendida (LORO) ===")
    for k, m in metricas.items():
        print(f"  {k:<26} accuracy={str(m['accuracy_tipo']):>7} "
              f"ventanas={m['ventanas']}")
    print(f"\nInforme: {ruta}")


if __name__ == "__main__":
    main()
