import sys
import os
from pathlib import Path

BACKEND_ROOT = Path(r"d:\SteelNort_web\backend")
sys.path.insert(0, str(BACKEND_ROOT))

from tools.menu_pipeline import cargar_config, paso_captura_normal

def main():
    cfg = cargar_config()
    print("Iniciando generación de carga...")
    # Generar 2 corridas de 120 segundos para asegurar al menos ~220 ventanas extras
    paso_captura_normal(cfg, duracion=120, workers=10)
    paso_captura_normal(cfg, duracion=120, workers=10)
    print("Capturas generadas.")

if __name__ == "__main__":
    main()

