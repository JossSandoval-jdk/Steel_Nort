"""
11_indice_calidad.py
====================
Calcula el indice de calidad de datos del indicador I-1.2 (meta >= 95 %):

    Calidad = (Completitud + Consistencia + Validez) / 3

  Completitud : 1 - celdas_nulas / celdas_totales
  Consistencia: 1 - filas_duplicadas / filas_totales
  Validez     : % de valores dentro de su rango permitido (CPU 0-100, etc.)

Ademas comprueba que las marcas de tiempo esten ordenadas por corrida
(criterio complementario de consistencia que menciona el indicador).

Entrada : output/preparado/dataset_steelnort.parquet
Salida  : output/modelado/indicadores/calidad_indice.json

Uso:
    python indicadores/11_indice_calidad.py
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Config del modelado (parents[1] = tools/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelado_config import (                       # noqa: E402
    DATASET_PRINCIPALES, DIR_MODELADO, log,
)

DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")

# Rangos permitidos por variable (None = sin cota superior). Solo las que
# tienen un rango fisico claro limitan la validez; el resto solo exige >= 0.
RANGOS = {
    "cpu_usr": (0, 100),
    "cpu_sys": (0, 100),
    "cpu_wai": (0, 100),
    "memory_percent": (0, 100),
    "memory_used_mb": (0, None),
    "page_life_expectancy": (0, None),
    "disk_read_per_sec": (0, None),
    "disk_write_per_sec": (0, None),
    "net_send_per_sec": (0, None),
    "net_recv_per_sec": (0, None),
    "load1": (0, None),
    "active_sessions": (0, None),
    "active_requests": (0, None),
    "transactions_per_sec": (0, None),
    "long_queries": (0, None),
    "long_transactions": (0, None),
    "api_latency_ms": (0, None),
    "api_status": (0, None),
    "lock_waits": (0, None),
    "total_locks": (0, None),
    "deadlocks_per_sec": (0, None),
    "events_wait_count": (0, None),
    "batch_count": (0, None),
    "batch_duration_avg_ms": (0, None),
    "batch_duration_max_ms": (0, None),
}


def validez_columna(serie, lo, hi):
    """Fraccion de valores dentro de [lo, hi] (hi None = sin cota)."""
    hi = np.inf if hi is None else hi
    return float(serie.between(lo, hi).mean())


def timestamps_ordenados(df):
    """% de corridas con marcas de tiempo estrictamente no decrecientes."""
    if "run_name" not in df or "timestamp" not in df:
        return None
    total = 0
    ok = 0
    for _, sub in df.groupby("run_name"):
        total += 1
        if sub["timestamp"].is_monotonic_increasing:
            ok += 1
    return round(ok / total, 4) if total else None


def main():
    if not os.path.isfile(DATASET_PRINCIPALES):
        log(f"Falta {DATASET_PRINCIPALES}. Ejecuta el pipeline de preparacion.")
        return

    df = pd.read_parquet(DATASET_PRINCIPALES)
    n_filas = len(df)

    # --- Completitud ---
    celdas_totales = int(df.size)
    nulos = int(df.isna().sum().sum())
    completitud = 1 - nulos / celdas_totales if celdas_totales else 0.0

    # --- Consistencia (duplicados) ---
    duplicadas = int(df.duplicated().sum())
    consistencia = 1 - duplicadas / n_filas if n_filas else 0.0

    # --- Validez (promedio por variable con rango definido) ---
    por_variable = []
    for col, (lo, hi) in RANGOS.items():
        if col not in df.columns:
            continue
        v = validez_columna(df[col], lo, hi)
        por_variable.append({"variable": col, "validez": round(v, 4),
                             "min": lo, "max": hi})
    validez = (float(np.mean([d["validez"] for d in por_variable]))
               if por_variable else 0.0)

    calidad = float(np.mean([completitud, consistencia, validez]))

    salida = {
        "fuente": DATASET_PRINCIPALES,
        "n_filas": n_filas,
        "n_columnas": int(df.shape[1]),
        "completitud": round(completitud, 4),
        "consistencia": round(consistencia, 4),
        "validez": round(validez, 4),
        "calidad": round(calidad, 4),
        "meta": 0.95,
        "cumple": bool(calidad >= 0.95),
        "detalle": {
            "celdas_totales": celdas_totales,
            "celdas_nulas": nulos,
            "filas_duplicadas": duplicadas,
            "timestamps_ordenados": timestamps_ordenados(df),
            "validez_por_variable": por_variable,
        },
    }

    os.makedirs(DIR_VAL, exist_ok=True)
    ruta = os.path.join(DIR_VAL, "calidad_indice.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=2)

    print("\n=== I-1.2 INDICE DE CALIDAD DE DATOS ===")
    print(f"  filas={n_filas} columnas={df.shape[1]}")
    print(f"  completitud  = {completitud:.4f}")
    print(f"  consistencia = {consistencia:.4f}")
    print(f"  validez      = {validez:.4f}  ({len(por_variable)} variables)")
    print(f"  CALIDAD      = {calidad:.4f}  "
          f"({'CUMPLE' if calidad >= 0.95 else 'NO CUMPLE'} meta >= 0.95)")
    print(f"\nInforme: {ruta}")


if __name__ == "__main__":
    main()
