"""
09_medir_cuando_clasificar.py
=============================
ADITIVO — mide el acierto del clasificador de tipo segun CUANDO se evalue
dentro del fallo. Responde a: la primera ventana alertada (lo que hoy emite la
alerta) todavia contiene la cola del fallo anterior, asi que clasificar ahi es
mucho peor que clasificar el evento completo.

Variantes:
  primera : primera ventana alertada del fallo (lo que emite la alerta hoy).
  pico    : ventana de menor score (mayor anomalia) dentro del fallo.
  evento  : promedio de las probabilidades de todas las ventanas del intervalo.

Salida: output/modelado/indicadores/clasificador_tipo_cuando.json
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np

_AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(_AQUI.parent))
from modelado_config import DIR_MODELADO, VARIABLES_MODELO, log  # noqa: E402

DIR_PRODUCCION = os.path.join(DIR_MODELADO, "produccion")
DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")
os.environ.setdefault("ML_ARTIFACTS_DIR", DIR_PRODUCCION)
os.environ.setdefault("ML_TRAIN_PKL",
                      os.path.join(DIR_PRODUCCION, "dataset_muestras_train.pkl"))
sys.path.insert(0, str(_AQUI.parents[3]))          # backend/

_spec = importlib.util.spec_from_file_location("eval05", _AQUI / "03_evaluar_oe3.py")
e05 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e05)

import pandas as pd                                  # noqa: E402
from app.v2.services import clasificador_tipo        # noqa: E402

VARIANTES = ("primera", "pico", "evento")
VENTANA_CLASIF = 10


def proba_de(modelo, features, pred) -> np.ndarray:
    """Vector de probabilidades de la ventana cruda de ``pred``."""
    filas = np.asarray([[m.get(n, 0.0) or 0.0 for n in features]
                        for _, m in pred["muestras"][-VENTANA_CLASIF:]], dtype=float)
    vector = np.concatenate([filas.mean(axis=0), filas.std(axis=0)])
    return modelo.predict_proba(vector.reshape(1, -1))[0]


def main():
    paquete = clasificador_tipo._cargar()
    if not paquete:
        log("Sin clasificador_tipo.joblib; nada que medir.")
        return
    modelo, features = paquete["modelo"], paquete["features"]
    clases = np.array(list(modelo.classes_))

    tl = e05.cargar_timelines()
    ds = pd.read_parquet(e05.DATASET_PRINCIPALES)
    det = e05.construir_detector()
    log(f"Modo detector: {det.modo} | clasificador: {len(clases)} clases")

    res = {v: {"top1": 0, "top2": 0, "top3": 0} for v in VARIANTES}
    detalle = []
    total = 0
    for run in sorted(tl["run_name"].unique()):
        sub = ds[ds["run_name"] == run].sort_values("timestamp").reset_index(drop=True)
        muestras = []
        for _, fila in sub.iterrows():
            m = {v: (0.0 if pd.isna(fila[v]) else float(fila[v]))
                 for v in VARIABLES_MODELO}
            m["fecha_str"] = str(fila["timestamp"])
            muestras.append(m)
        ventanas = []
        for out in det.evaluar_lote(run, muestras):
            i = out["indice"]
            pred = dict(out)
            pred["muestras"] = [(str(sub.iloc[j]["timestamp"]), muestras[j])
                                for j in range(i - det.ventana + 1, i + 1)]
            ventanas.append({
                "ini": pd.Timestamp(sub.iloc[i - det.ventana + 1]["timestamp"]),
                "fin": pd.Timestamp(sub.iloc[i]["timestamp"]), "pred": pred})
        for _, f in tl[tl["run_name"] == run].iterrows():
            idx = [w for w in ventanas
                   if w["ini"] <= f["fin"] and w["fin"] >= f["inicio"]]
            alerta = sorted([w for w in idx if w["pred"]["es_anomalia"]],
                            key=lambda w: w["fin"])
            if not alerta:
                continue
            total += 1
            probas = {
                "primera": proba_de(modelo, features, alerta[0]["pred"]),
                "pico": proba_de(modelo, features,
                                 min(idx, key=lambda w: w["pred"]["score"])["pred"]),
                "evento": np.mean([proba_de(modelo, features, w["pred"])
                                   for w in idx], axis=0),
            }
            fila = {"run": run, "real": f["tipo"]}
            for v, p in probas.items():
                orden = np.argsort(-p)
                fila[v] = {"top1": clases[orden[0]],
                           "top2": [str(c) for c in clases[orden[:2]]]}
                res[v]["top1"] += int(clases[orden[0]] == f["tipo"])
                res[v]["top2"] += int(f["tipo"] in set(clases[orden[:2]]))
                res[v]["top3"] += int(f["tipo"] in set(clases[orden[:3]]))
            detalle.append(fila)

    resumen = {v: {k: round(x / total, 4) for k, x in m.items()}
               for v, m in res.items()}
    resumen = {"modelo": det.modo, "faults": total, "variantes": resumen,
               "nota": ("'primera' = lo que emite la alerta hoy (alerta_nueva). "
                        "'evento' = promedio de probabilidades del intervalo.")}
    os.makedirs(DIR_VAL, exist_ok=True)
    ruta = os.path.join(DIR_VAL, "clasificador_tipo_cuando.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"resumen": resumen, "detalle": detalle}, fh,
                  ensure_ascii=False, indent=2)

    print("\n=== CUANDO CLASIFICAR (clasificador de tipo) ===")
    print(f"  faults={total}")
    for v, m in res.items():
        print(f"  {v:<8} top1={m['top1'] / total:.3f} "
              f"top2={m['top2'] / total:.3f} top3={m['top3'] / total:.3f}")
    print(f"\nInforme: {ruta}")


if __name__ == "__main__":
    main()