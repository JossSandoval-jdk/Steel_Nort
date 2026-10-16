"""
etiquetas.py
============
Fuente única de etiquetas (ground truth) para el modelado.

La etiqueta nativa vive en el dataset preparado (`etiqueta_manual`), que el
pipeline deriva de `origen.json` (`es_carga_normal`). Antes de este módulo la
validación usaba solo `anomalias_timeline.csv`, y por eso contaba como
"normales" corridas que son anomalías declaradas (las live, sin timeline).

Regla:
  - Etiqueta por corrida: la del dataset (normal / anomalia).
  - Ventana de test = falla si:
      * su corrida tiene timeline y la ventana cruza un intervalo, o
      * su corrida es anomalía sin timeline usable (live, o timeline que no
        engancha con las ventanas) -> toda la corrida es anomalía.

Con esto, TODAS las ventanas de test resultan anomalías (el test no tiene
corridas sanas); los sanos son las corridas de entrenamiento.
"""

import glob
import os

import numpy as np
import pandas as pd

from modelado_config import DATASET_PRINCIPALES, OUTPUT_BASE, log


def etiquetas_corridas():
    """{corrida: 'normal'|'anomalia'} leído de la etiqueta nativa del dataset."""
    df = pd.read_parquet(DATASET_PRINCIPALES,
                         columns=["run_name", "etiqueta_manual"])
    etiquetas = {}
    for run, grupo in df.groupby("run_name"):
        valores = grupo["etiqueta_manual"].dropna().unique()
        if len(valores) == 1:
            etiquetas[run] = "normal" if bool(valores[0]) else "anomalia"
        else:
            etiquetas[run] = "mixta"
    return etiquetas


def _timelines():
    """Timelines de anomalias: run_name, inicio, fin."""
    rutas = glob.glob(os.path.join(OUTPUT_BASE, "anomalias", "*",
                                   "anomalias_timeline.csv"))
    if not rutas:
        return pd.DataFrame(columns=["run_name", "inicio", "fin"])
    tl = pd.concat([
        pd.read_csv(r, encoding="utf-8-sig").assign(
            run_name=os.path.basename(os.path.dirname(r)))
        for r in rutas], ignore_index=True)
    tl["inicio"] = pd.to_datetime(tl["inicio"])
    tl["fin"] = pd.to_datetime(tl["fin"])
    return tl


def marcar_fault_nativa(art, etiquetas=None):
    """Máscara por ventana de test: True = anomalía (según etiqueta nativa)."""
    etiquetas = etiquetas or etiquetas_corridas()
    tl = _timelines()
    mask = np.zeros(len(art["ventanas_test"]), dtype=bool)

    for i, w in enumerate(art["ventanas_test"]):
        run = w["run"]
        if etiquetas.get(run) != "anomalia":
            continue
        g = tl[tl["run_name"] == run]
        if g.empty:
            mask[i] = True  # anomalía de corrida entera (live)
            continue
        ini, fin = pd.Timestamp(w["inicio"]), pd.Timestamp(w["fin"])
        mask[i] = bool(((ini <= g["fin"]) & (fin >= g["inicio"])).any())

    # Corridas anomalía con timeline que no engancha con sus ventanas:
    # se toman enteras como anomalía (no se las cuenta como normales).
    for i, w in enumerate(art["ventanas_test"]):
        run = w["run"]
        if etiquetas.get(run) != "anomalia":
            continue
        idx = [j for j, x in enumerate(art["ventanas_test"])
               if x["run"] == run]
        if idx and not mask[idx].any():
            mask[idx] = True

    return mask


def resumen(art=None):
    """Resumen de etiquetas para inspección (y para validacion/etiquetas.json)."""
    etiquetas = etiquetas_corridas()
    out = {
        "corridas": etiquetas,
        "normales": sorted(r for r, t in etiquetas.items() if t == "normal"),
        "anomalias": sorted(r for r, t in etiquetas.items() if t == "anomalia"),
    }
    if art is not None:
        mask = marcar_fault_nativa(art, etiquetas)
        out["ventanas_test"] = int(len(mask))
        out["ventanas_test_anomalia"] = int(mask.sum())
        out["ventanas_test_normal"] = int((~mask).sum())
        out["_nota"] = ("El test no incluye corridas sanas por diseño: solo "
                        "ventanas de corridas anómalas. Las ventanas normales "
                        "de entrenamiento se usan para el FPR vía "
                        "leave-one-run-out (ver indicadores/honesto.json).")
    return out


if __name__ == "__main__":
    import pickle
    from modelado_config import DIR_MODELADO

    art = None
    ruta = os.path.join(DIR_MODELADO, "artefactos_modelo.pkl")
    if os.path.exists(ruta):
        with open(ruta, "rb") as f:
            art = pickle.load(f)
    log(str(resumen(art)))
