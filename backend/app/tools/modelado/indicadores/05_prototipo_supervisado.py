"""
05_prototipo_supervisado.py
===========================
PROTOTIPO — solo medicion, NO toca produccion.

Mide si un clasificador SUPERVISADO multiclase (RandomForest) sobre las 25
variables del modelo puede predecir el TIPO de fallo, usando las etiquetas de
los timelines. Validacion honesta: leave-one-run-out (LORO), se entrena sin la
corrida que se evalua (evita que memorice la corrida).

Escenarios:
  - con_normal : clasifica {fault1, fault2, fault3, fault5, lockwait, normal}
  - solo_tipos : clasifica solo entre tipos de fallo (quita la clase normal),
                 que es lo que de verdad mide I-3.1.

Representaciones de la ventana (10 muestras):
  - cruda : media de las 25 variables.
  - z     : media del z por muestra (recortado a +-Z_MAX).
  - zstd  : media y desviacion del z por muestra (50 valores).

Entrada : output/preparado/dataset_steelnort.parquet
          output/anomalias/<run>/anomalias_timeline.csv
          output/modelado/produccion/*        (scaler del bundle)
Salida  : output/modelado/indicadores/prototipo_supervisado.json
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
Z_MAX = 10.0
VENTANA = 10
CLAVES = ("cruda", "z", "zstd")


def ventanas_de(sub, scaler, posiciones):
    """Ventanas deslizantes con features cruda / z / zstd."""
    sub = sub.sort_values("timestamp").reset_index(drop=True)
    crudo = sub[VARIABLES_MODELO].astype(float).to_numpy()
    ts = pd.to_datetime(sub["timestamp"]).to_numpy()

    z = np.zeros_like(crudo)
    for idx, v in enumerate(VARIABLES_MODELO):
        p = posiciones.get(v, -1)
        if p < 0 or scaler is None or p >= len(scaler.mean_):
            continue
        escala = float(scaler.scale_[p]) or 1.0
        z[:, idx] = (crudo[:, idx] - float(scaler.mean_[p])) / escala
    z = np.clip(z, -Z_MAX, Z_MAX)

    salida = []
    for i in range(VENTANA - 1, len(sub)):
        wc = crudo[i - VENTANA + 1:i + 1]
        wz = z[i - VENTANA + 1:i + 1]
        salida.append({
            "ini": pd.Timestamp(ts[i - VENTANA + 1]),
            "fin": pd.Timestamp(ts[i]),
            "cruda": wc.mean(axis=0),
            "z": wz.mean(axis=0),
            "zstd": np.concatenate([wz.mean(axis=0), wz.std(axis=0)]),
        })
    return salida


def main():
    tl = _eval05.cargar_timelines()
    if tl.empty:
        log("Sin timelines.")
        return
    ds = pd.read_parquet(DATASET_PRINCIPALES)
    det = _eval05.construir_detector()
    scaler = getattr(det, "_scaler", None)
    posiciones = getattr(det, "_posiciones", {}) or {}
    etiq = etiquetas_corridas()
    log(f"Detector/scaler del bundle: {det.modo}")

    normales, fallos = [], []
    for run, sub in ds.groupby("run_name"):
        if sub.empty:
            continue
        ventanas = ventanas_de(sub, scaler, posiciones)
        es_normal = etiq.get(run, "anomalia") == "normal"
        for w in ventanas:
            fila = {"run": run, **{k: w[k] for k in CLAVES}}
            if es_normal:
                normales.append({**fila, "label": "normal"})
                continue
            for _, f in tl[tl["run_name"] == run].iterrows():
                if w["ini"] <= f["fin"] and w["fin"] >= f["inicio"]:
                    fallos.append({**fila, "label": f["tipo"]})
                    break

    runs_anom = sorted(tl["run_name"].unique())
    log(f"Ventanas: {len(normales)} normales, {len(fallos)} de fallo | "
        f"corridas anomalas: {len(runs_anom)}")

    def evaluar(clave, con_normal):
        aciertos = total = 0
        conf, por_clase = {}, {}
        for run in runs_anom:
            train = (normales if con_normal else []) + \
                    [p for p in fallos if p["run"] != run]
            test = [p for p in fallos if p["run"] == run]
            if not test or len({p["label"] for p in train}) < 2:
                continue
            Xtr = np.array([p[clave] for p in train], dtype=float)
            ytr = [p["label"] for p in train]
            Xte = np.array([p[clave] for p in test], dtype=float)
            clf = RandomForestClassifier(n_estimators=300, random_state=0,
                                         class_weight="balanced")
            clf.fit(Xtr, ytr)
            for p, yhat in zip(test, clf.predict(Xte)):
                total += 1
                ok = int(yhat == p["label"])
                aciertos += ok
                conf.setdefault(p["label"], {}).setdefault(yhat, 0)
                conf[p["label"]][yhat] += 1
                c = por_clase.setdefault(p["label"], [0, 0])
                c[0] += ok
                c[1] += 1
        recall = {k: round(v[0] / v[1], 3) for k, v in por_clase.items()}
        return (round(aciertos / total, 4) if total else None), total, conf, recall

    metricas = {}
    for clave in CLAVES:
        for nombre, con_normal in (("con_normal", True), ("solo_tipos", False)):
            acc, total, conf, recall = evaluar(clave, con_normal)
            metricas[f"{clave}_{nombre}"] = {
                "accuracy_tipo": acc, "ventanas": total,
                "recall_por_clase": recall, "matriz_confusion": conf,
            }
            log(f"LORO {nombre} ({clave}): {acc} sobre {total} ventanas")

    # Firma aprendida por clase (solo fallos) vs huella esperada (proxy I-3.3).
    firma = {}
    for label in sorted({p["label"] for p in fallos}):
        puntos = [p for p in fallos if p["label"] == label]
        zmedio = np.mean(np.array([p["z"] for p in puntos], dtype=float), axis=0)
        firma[label] = [VARIABLES_MODELO[i] for i in np.argsort(-np.abs(zmedio))[:3]]
    huella = _eval05.FOOTPRINT
    firma_ok = {lab: sorted(set(top) & set(huella[lab]["vars"]))
                for lab, top in firma.items() if lab in huella}

    resumen = {
        "modelo": det.modo,
        "clasificador": "RandomForest(300, balanced)",
        "validacion": "leave-one-run-out (corridas anomalas)",
        "ventanas_normales": len(normales),
        "ventanas_fallo": len(fallos),
        "metricas": metricas,
        "firma_top3_por_clase": firma,
        "firma_vs_huella": firma_ok,
        "nota": ("Prototipo de medicion: no modifica produccion. I-3.1 = accuracy "
                 "del tipo con la corrida dejada fuera. I-3.3 proxy = firma "
                 "aprendida por clase vs huella esperada."),
    }

    os.makedirs(DIR_VAL, exist_ok=True)
    ruta = os.path.join(DIR_VAL, "prototipo_supervisado.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"resumen": resumen}, fh, ensure_ascii=False, indent=2, default=str)

    print("\n=== PROTOTIPO SUPERVISADO (LORO) ===")
    print(f"  normales={len(normales)} fallos={len(fallos)}")
    print(f"  {'variante':<16} {'accuracy':>9} {'ventanas':>9}")
    for k, m in metricas.items():
        print(f"  {k:<16} {str(m['accuracy_tipo']):>9} {m['ventanas']:>9}")
    print("  I-3.3 firma top-3 vs huella:")
    for lab, ok in firma_ok.items():
        print(f"    {lab:<8} top3={firma[lab]} coincide={ok}")
    print(f"\nInforme: {ruta}")


if __name__ == "__main__":
    main()
