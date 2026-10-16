"""
08_entrenar_clasificador_tipo.py
================================
ADITIVO — no toca el detector ni los artefactos existentes.

Entrena la capa de apoyo al diagnostico (I-3.1): un RandomForest que estima el
TIPO de fallo a partir de la ventana anomala. Exporta el artefacto a

    output/modelado/produccion/clasificador_tipo.joblib

Representacion de la ventana (identica en entrenamiento e inferencia):
    para cada una de las 25 variables del modelo -> media y desviacion de las
    10 muestras crudas de la ventana  (50 features).

El RandomForest es invariante a la escala por feature, por lo que entrenar con
las muestras crudas y servir con las muestras crudas de ``pred["muestras"]``
da exactamente el mismo modelo. No hace falta el scaler.

Validacion honesta: leave-one-run-out (LORO) sobre las corridas anomalas; la
clase ``normal`` siempre queda en el train. Se miden top-1, top-2 y top-3.

Salida:
    produccion/clasificador_tipo.joblib
    output/modelado/indicadores/clasificador_tipo.json   (metricas honestas + config elegida)
"""

import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

_AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(_AQUI.parent))
from modelado_config import (                       # noqa: E402
    DATASET_PRINCIPALES, DIR_MODELADO, VARIABLES_MODELO, VENTANA, log,
)
from etiquetas import etiquetas_corridas              # noqa: E402

DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")
DIR_PRODUCCION = os.path.join(DIR_MODELADO, "produccion")
RUTA_ARTEFACTO = os.path.join(DIR_PRODUCCION, "clasificador_tipo.joblib")
RUTA_METRICAS = os.path.join(DIR_VAL, "clasificador_tipo.json")

# Etiqueta legible por tipo de fallo (misma que 03_diagnostico.FOOTPRINT).
ETIQUETAS_TIPO = {
    "fault1": "Escrituras al log por INSERTs concurrentes",
    "fault2": "Full scan por falta de indice",
    "fault3": "Carga pesada sobre la API",
    "fault5": "Commits concurrentes",
    "lockwait": "Retencion de lock entre sesiones",
    "normal": "Comportamiento normal",
}

CLASES = sorted(ETIQUETAS_TIPO)


def vector_de(ventana: np.ndarray) -> np.ndarray:
    """Media y desviacion por variable de una ventana [VENTANA, n_vars]."""
    return np.concatenate([ventana.mean(axis=0), ventana.std(axis=0)])


def ventanas_etiquetadas(ds: pd.DataFrame, tl: pd.DataFrame,
                         etiq: dict) -> list[dict]:
    """Ventanas deslizantes etiquetadas: normal o tipo de fallo del timeline."""
    datos = []
    for run, sub in ds.groupby("run_name"):
        sub = sub.sort_values("timestamp").reset_index(drop=True)
        if len(sub) < VENTANA:
            continue
        crudo = sub[VARIABLES_MODELO].astype(float).fillna(0.0).to_numpy()
        ts = pd.to_datetime(sub["timestamp"]).to_numpy()
        es_normal = etiq.get(run, "anomalia") == "normal"
        intervalos = [(np.datetime64(f["inicio"]), np.datetime64(f["fin"]), f["tipo"])
                      for _, f in tl[tl["run_name"] == run].iterrows()]
        for i in range(VENTANA - 1, len(sub)):
            ini, fin = pd.Timestamp(ts[i - VENTANA + 1]), pd.Timestamp(ts[i])
            vec = vector_de(crudo[i - VENTANA + 1:i + 1])
            if es_normal:
                datos.append({"run": run, "vec": vec, "label": "normal"})
                continue
            for ini_f, fin_f, tipo in intervalos:
                if np.datetime64(ini) <= fin_f and np.datetime64(fin) >= ini_f:
                    datos.append({"run": run, "vec": vec, "label": tipo})
                    break
    return datos


def evaluar_loro(datos: list[dict], con_normal: bool) -> dict:
    """LORO sobre las corridas anomalas; devuelve top-1/2/3 y confusion."""
    normales = [d for d in datos if d["label"] == "normal"]
    fallos = [d for d in datos if d["label"] != "normal"]
    runs_anom = sorted({d["run"] for d in fallos})
    aciertos = {"top1": 0, "top2": 0, "top3": 0}
    total = 0
    conf = {}
    for run in runs_anom:
        train = (normales if con_normal else []) + \
                [d for d in fallos if d["run"] != run]
        test = [d for d in fallos if d["run"] == run]
        if not test or len({d["label"] for d in train}) < 2:
            continue
        clf = RandomForestClassifier(n_estimators=300, random_state=0,
                                     class_weight="balanced")
        clf.fit(np.array([d["vec"] for d in train]), [d["label"] for d in train])
        clases = clf.classes_
        for d in test:
            proba = clf.predict_proba(d["vec"].reshape(1, -1))[0]
            orden = np.argsort(-proba)
            top1 = clases[orden[0]]
            total += 1
            aciertos["top1"] += int(top1 == d["label"])
            aciertos["top2"] += int(d["label"] in set(clases[orden[:2]]))
            aciertos["top3"] += int(d["label"] in set(clases[orden[:3]]))
            conf.setdefault(d["label"], {}).setdefault(top1, 0)
            conf[d["label"]][top1] += 1
    metricas = ({k: round(v / total, 4) for k, v in aciertos.items()} if total
                else {"top1": None, "top2": None, "top3": None})
    metricas["ventanas"] = total
    metricas["matriz_confusion"] = conf
    return metricas


def main():
    ds = pd.read_parquet(DATASET_PRINCIPALES)
    etiq = etiquetas_corridas()

    # Timelines: misma carga que usan los prototipos (una carpeta por corrida).
    registros = []
    for ruta in glob.glob(os.path.join(
            os.path.dirname(DATASET_PRINCIPALES), "..", "anomalias", "*",
            "anomalias_timeline.csv")):
        run = Path(ruta).parent.name
        filas = pd.read_csv(ruta, parse_dates=["inicio", "fin"])
        filas["run_name"] = run
        registros.append(filas)
    tl = pd.concat(registros, ignore_index=True) if registros else pd.DataFrame(
        columns=["tipo", "inicio", "fin", "run_name"])

    datos = ventanas_etiquetadas(ds, tl, etiq)
    n_norm = sum(1 for d in datos if d["label"] == "normal")
    log(f"Ventanas: {n_norm} normales | {len(datos) - n_norm} de fallo")

    comparacion = {}
    for nombre, con_normal in (("con_normal", True), ("solo_tipos", False)):
        m = evaluar_loro(datos, con_normal)
        comparacion[nombre] = m
        log(f"LORO {nombre}: top1={m['top1']} top2={m['top2']} top3={m['top3']} "
            f"({m['ventanas']} ventanas)")

    # Ship la configuracion con mejor top-2 (desempate por top-1).
    elegida = max(comparacion, key=lambda k: (comparacion[k]["top2"] or 0,
                                              comparacion[k]["top1"] or 0))
    con_normal = elegida == "con_normal"
    log(f"Configuracion elegida: {elegida}")

    train = (datos if con_normal
             else [d for d in datos if d["label"] != "normal"])
    clf = RandomForestClassifier(n_estimators=400, random_state=0,
                                 class_weight="balanced")
    clf.fit(np.array([d["vec"] for d in train]), [d["label"] for d in train])

    paquete = {
        "modelo": clf,
        "features": list(VARIABLES_MODELO),
        "ventana": int(VENTANA),
        "clases": clf.classes_.tolist(),
        "etiquetas": ETIQUETAS_TIPO,
        "con_normal": con_normal,
        "metricas_loro": comparacion,
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "nota": ("Clasificador supervisado de tipo (RandomForest sobre media y "
                 "desviacion de la ventana cruda). Metrica honesta = LORO."),
    }
    os.makedirs(DIR_PRODUCCION, exist_ok=True)
    os.makedirs(DIR_VAL, exist_ok=True)
    joblib.dump(paquete, RUTA_ARTEFACTO)

    resumen = {
        "artefacto": RUTA_ARTEFACTO,
        "features": len(VARIABLES_MODELO),
        "ventana": int(VENTANA),
        "elegida": elegida,
        "metricas_loro": comparacion,
        "ventanas_normales": n_norm,
        "ventanas_fallo": len(datos) - n_norm,
    }
    with open(RUTA_METRICAS, "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)

    print("\n=== CLASIFICADOR DE TIPO (LORO honesto) ===")
    for nombre, m in comparacion.items():
        print(f"  {nombre:<11} top1={m['top1']} top2={m['top2']} "
              f"top3={m['top3']} ({m['ventanas']} ventanas)")
    print(f"  elegida={elegida} | clases={clf.classes_.tolist()}")
    print(f"\nArtefacto : {RUTA_ARTEFACTO}")
    print(f"Metricas  : {RUTA_METRICAS}")


if __name__ == "__main__":
    main()