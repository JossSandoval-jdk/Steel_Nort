"""Configuración común de las pruebas.

Deja ``backend/`` en ``sys.path`` para poder importar ``app.*`` y apunta el
detector al bundle de **producción**, de modo que las pruebas corran sin base
de datos ni servicios externos.
"""

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

PRODUCCION = BACKEND / "app" / "tools" / "output" / "modelado" / "produccion"

# El detector lee el entorno al importarse: fijarlo ANTES de cualquier import.
os.environ.setdefault("ML_ARTIFACTS_DIR", str(PRODUCCION))
os.environ.setdefault("ML_TRAIN_PKL", str(PRODUCCION / "dataset_muestras_train.pkl"))
os.environ.setdefault("STEELNORT_ZONAL", "0")
os.environ.setdefault("STEELNORT_ENSEMBLE", "")
