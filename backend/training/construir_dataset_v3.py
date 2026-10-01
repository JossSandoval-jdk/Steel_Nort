"""
construir_dataset_v3.py
=======================

Construye training/output/integrado_v3/dataset_steelnort_preparado.csv a
partir del dataset integrado v2 + el CSVV de captura live (mismo formato),
para reentrenar con la realidad actual sin tocar el dataset v2.

Variables de entorno (opcionales):
    STEELNORT_CAPTURA_SALIDA   CSV generado por capturar_live_v3.py
                               (default training/output/integrado_v3/captura_live.csv)
"""

import csv
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE = os.path.join(BACKEND, "training", "output", "integrado_v2",
                    "dataset_steelnort_preparado.csv")
CAPTURA = os.getenv(
    "STEELNORT_CAPTURA_SALIDA",
    os.path.join(BACKEND, "training", "output", "integrado_v3",
                 "captura_live.csv"))
DESTINO = os.path.join(BACKEND, "training", "output", "integrado_v3",
                       "dataset_steelnort_preparado.csv")

CONTEXTO = {
    "run_name", "grupo", "wait_lck_count", "wait_io_count",
    "wait_log_count", "experiment_id",
}


def _leer(ruta):
    with open(ruta, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        filas = [list(row) for row in reader]
    return header, filas


def main():
    if not os.path.exists(BASE):
        print(f"[DATASET-V3] No existe el base: {BASE}")
        return
    if not os.path.exists(CAPTURA):
        print(f"[DATASET-V3] No existe la captura: {CAPTURA}\n"
              "Ejecuta primero capturar_live_v3.py")
        return

    header_base, filas_base = _leer(BASE)
    header_cap, filas_cap = _leer(CAPTURA)

    if header_cap != header_base:
        print("[DATASET-V3] ERROR: el CSV de captura no tiene el mismo "
              "encabezado que el dataset base.")
        return

    runs = sorted({row[header_base.index("run_name")] for row in filas_cap})
    print(f"[DATASET-V3] base={len(filas_base)} filas | captura="
          f"{len(filas_cap)} filas (run {runs})", flush=True)

    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    with open(DESTINO, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header_base)
        w.writerows(filas_base)
        w.writerows(filas_cap)

    total = len(filas_base) + len(filas_cap)
    print(f"[DATASET-V3] LISTO: {total} filas -> {DESTINO}", flush=True)


if __name__ == "__main__":
    main()