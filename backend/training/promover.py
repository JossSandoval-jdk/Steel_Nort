"""
promover.py
===========

Promueve los artefactos generados en modelado a ml/artifacts y al
dataset de runtime (training/datasets/dataset_muestras_train.pkl), respaldando
lo existente con sufijo .bak_old_<timestamp>.

Artefactos: modelo_isolation_forest.joblib, modelo_copod.joblib,
scaler.joblib, features_modelo.csv, reglas_umbrales.csv,
variables_correlacion.csv, importancia_variables.csv,
dataset_muestras_train.pkl.
"""

import datetime
import os
import shutil
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ART = os.path.join(BACKEND, "ml", "artifacts")
DATASETS = os.path.join(BACKEND, "training", "datasets")
MODELADO = os.path.join(BACKEND, "training", "output", "modelado")

FUENTES = {
    "modelo_isolation_forest.joblib": os.path.join(MODELADO, "deteccion"),
    "modelo_copod.joblib": os.path.join(MODELADO, "deteccion"),
    "scaler.joblib": os.path.join(MODELADO, "deteccion"),
    "features_modelo.csv": os.path.join(MODELADO, "correlacion"),
    "reglas_umbrales.csv": os.path.join(MODELADO, "correlacion"),
    "variables_correlacion.csv": os.path.join(MODELADO, "correlacion"),
    "importancia_variables.csv": os.path.join(MODELADO, "deteccion"),
}
PKL_SRC = os.path.join(MODELADO, "dataset_muestras_train.pkl")
PKL_DEST = os.path.join(DATASETS, "dataset_muestras_train.pkl")

STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _backup(dest):
    if os.path.exists(dest):
        shutil.copy2(dest, dest + f".bak_old_{STAMP}")
        print(f"  respaldo: {os.path.basename(dest)} -> {os.path.basename(dest)}.bak_old_{STAMP}")


def _era_ok():
    """No promueve si los artefactos son de una era distinta a la config."""
    src = os.path.join(MODELADO, "correlacion", "features_modelo.csv")
    if not os.path.exists(src):
        return True  # ya lo reporta la revisión de faltantes
    try:
        sys.path.insert(0, os.path.join(BACKEND, "training", "nucleo", "modeling"))
        import config as cfg
        n_vars = sum(1 for _ in open(src, encoding="utf-8-sig")) - 1
        if n_vars != len(cfg.VARIABLES_MODELO):
            print(f"[PROMOVER] ABORTADO: {src} tiene {n_vars} variables pero "
                  f"config.VARIABLES_MODELO tiene {len(cfg.VARIABLES_MODELO)}. "
                  "Los artefactos son de una era anterior; ejecuta entrenar.bat "
                  "antes de promover.")
            return False
    except Exception as error:  # sin config no se puede validar
        print(f"[PROMOVER] AVISO: no se pudo validar la era ({error}).")
    return True


def main():
    faltan = []
    for nombre, carpeta in FUENTES.items():
        if not os.path.exists(os.path.join(carpeta, nombre)):
            faltan.append(nombre)
    if not os.path.exists(PKL_SRC):
        faltan.append(PKL_SRC)

    if faltan:
        print(f"[PROMOVER] No se encontro: {faltan}\n"
              "Revisa que los pasos 01-05 y generar_copod hayan terminado.")
        return

    if not _era_ok():
        return

    print("[PROMOVER] Promoviendo a ml/artifacts y training/datasets ...")
    for nombre, carpeta in FUENTES.items():
        src = os.path.join(carpeta, nombre)
        dest = os.path.join(ART, nombre)
        _backup(dest)
        shutil.copy2(src, dest)
        print(f"  {nombre}")

    print("  ", os.path.basename(PKL_SRC))

    _backup(PKL_DEST)
    shutil.copy2(PKL_SRC, PKL_DEST)


    features = os.path.join(ART, "features_modelo.csv")
    n_vars = sum(1 for _ in open(features, encoding="utf-8-sig")) - 1 if os.path.exists(features) else 0
    print(f"[PROMOVER] LISTO. features_modelo.csv con {n_vars} vars.\n"
          "Reinicia el backend para que el detector cargue los artefactos.")


if __name__ == "__main__":
    main()