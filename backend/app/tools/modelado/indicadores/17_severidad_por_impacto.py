"""
17_severidad_por_impacto.py
===========================
Ground truth INDEPENDIENTE para I-3.2 basado en el IMPACTO REAL medido en el
dataset. La severidad se define por CUANTILES de la caida de transactions_per_sec
combinada con deadlocks y latencia (criterio objetivo, reproducible).

Criterio (documentado):
  score_impacto = 0.6 * tx_caida_pct_norm + 0.3 * api_norm + 0.1 * deadlocks_norm
  alta   = score_impacto >= P75
  media  = P25 <= score_impacto < P75
  baja   = score_impacto < P25

Entrada:
  output/preparado/dataset_steelnort.parquet
  output/anomalias/<run>/anomalias_timeline.csv
Salida:
  output/modelado/indicadores/severidad_esperada_por_impacto.json
"""
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelado_config import DATASET_PRINCIPALES, OUTPUT_BASE, DIR_MODELADO  # noqa

DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")
OUT = os.path.join(DIR_VAL, "severidad_esperada_por_impacto.json")

PESO_TX = 0.6
PESO_API = 0.3
PESO_DL = 0.1


def cargar_timelines():
    rutas = glob.glob(os.path.join(OUTPUT_BASE, "anomalias", "*",
                                   "anomalias_timeline.csv"))
    if not rutas:
        return pd.DataFrame(columns=["run_name", "tipo", "inicio", "fin"])
    tl = pd.concat([
        pd.read_csv(r, encoding="utf-8-sig").assign(
            run_name=os.path.basename(os.path.dirname(r)))
        for r in rutas], ignore_index=True)
    tl["inicio"] = pd.to_datetime(tl["inicio"])
    tl["fin"] = pd.to_datetime(tl["fin"])
    return tl


def calcular_baseline(ds):
    """Baseline de transactions_per_sec: ventanas sin etiqueta de anomalia."""
    if "etiqueta_manual" in ds.columns:
        normales = ds[ds["etiqueta_manual"].astype(str).str.lower().isin(
            ("normal", "0", "false", "no"))]
        if not normales.empty:
            return float(normales["transactions_per_sec"].mean())
    return float(ds["transactions_per_sec"].mean())


def normalizar_minmax(valores):
    arr = np.array(valores, dtype=float)
    lo, hi = arr.min(), arr.max()
    if hi - lo < 1e-12:
        return np.zeros_like(arr)
    return (arr - lo) / (hi - lo)


def main():
    if not os.path.isfile(DATASET_PRINCIPALES):
        print(f"Falta {DATASET_PRINCIPALES}")
        return

    ds = pd.read_parquet(DATASET_PRINCIPALES)
    ds["timestamp"] = pd.to_datetime(ds["timestamp"])
    tl = cargar_timelines()
    if tl.empty:
        print("Sin timelines de anomalias.")
        return

    tx_baseline = calcular_baseline(ds)
    print(f"Baseline transactions_per_sec = {tx_baseline:.2f}")
    print(f"Faults en timelines: {len(tl)}")

    crudos = []
    for _, f in tl.iterrows():
        sub = ds[(ds["run_name"] == f["run_name"]) &
                 (ds["timestamp"] >= f["inicio"]) &
                 (ds["timestamp"] <= f["fin"])]
        if sub.empty:
            continue

        tx_min = float(sub["transactions_per_sec"].min())
        tx_caida_pct = max(0.0, (tx_baseline - tx_min) / tx_baseline) if tx_baseline > 0 else 0.0
        api_max = float(sub["api_latency_ms"].max()) if "api_latency_ms" in sub else 0.0
        dl_max = float(sub["deadlocks_per_sec"].max()) if "deadlocks_per_sec" in sub else 0.0

        crudos.append({
            "run": f["run_name"],
            "fault": f["tipo"],
            "inicio": str(f["inicio"]),
            "fin": str(f["fin"]),
            "tx_baseline": round(tx_baseline, 2),
            "tx_min": round(tx_min, 2),
            "tx_caida_pct": round(tx_caida_pct * 100, 2),
            "api_max_ms": round(api_max, 2),
            "deadlocks_max": round(dl_max, 4),
        })

    if not crudos:
        print("Sin fallos con datos en el dataset.")
        return

    tx_norm = normalizar_minmax([c["tx_caida_pct"] for c in crudos])
    api_norm = normalizar_minmax([c["api_max_ms"] for c in crudos])
    dl_norm = normalizar_minmax([c["deadlocks_max"] for c in crudos])

    for i, c in enumerate(crudos):
        score = PESO_TX * tx_norm[i] + PESO_API * api_norm[i] + PESO_DL * dl_norm[i]
        c["score_impacto"] = round(float(score), 4)

    scores = np.array([c["score_impacto"] for c in crudos])
    p25, p75 = np.percentile(scores, [25, 75])

    for c in crudos:
        if c["score_impacto"] >= p75:
            c["severidad_esperada"] = "alta"
        elif c["score_impacto"] >= p25:
            c["severidad_esperada"] = "media"
        else:
            c["severidad_esperada"] = "baja"

    dist = {}
    for c in crudos:
        s = c["severidad_esperada"]
        dist[s] = dist.get(s, 0) + 1

    os.makedirs(DIR_VAL, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({
            "criterio": (
                "Severidad por impacto medido (cuantiles P25/P75 del score compuesto). "
                "score = 0.6*tx_caida + 0.3*api_latency + 0.1*deadlocks (min-max normalizado)."
            ),
            "pesos": {"tx_caida": PESO_TX, "api": PESO_API, "deadlocks": PESO_DL},
            "cuantiles": {"p25": round(float(p25), 4), "p75": round(float(p75), 4)},
            "baseline_tx": round(tx_baseline, 2),
            "distribucion": dist,
            "por_fault": crudos,
        }, fh, ensure_ascii=False, indent=2)

    print(f"\n=== GROUND TRUTH POR IMPACTO (CUANTILES) ===")
    print(f"  faults={len(crudos)}  distribucion={dist}")
    print(f"  P25={p25:.4f}  P75={p75:.4f}")
    print(f"  informe: {OUT}")


if __name__ == "__main__":
    main()