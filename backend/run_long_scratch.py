import sys
import subprocess
from pathlib import Path

BACKEND_ROOT = Path(r"d:\SteelNort_web\backend")
sys.path.insert(0, str(BACKEND_ROOT))

from tools.menu_pipeline import cargar_config, paso_captura_normal

def main():
    cfg = cargar_config()
    print("Iniciando generacion de carga extendida (900 segundos)...")
    # Generar 1 corrida de 900 segundos (15 minutos)
    paso_captura_normal(cfg, duracion=900, workers=10)
    print("Captura generada. Ejecutando pipeline de preparacion y modelado...")

    steps = [
        r"training\nucleo\data_preparation\00_inventario.py",
        r"training\nucleo\data_preparation\01_seleccion.py",
        r"training\nucleo\data_preparation\02_limpieza.py",
        r"training\nucleo\data_preparation\03_transformacion.py",
        r"training\nucleo\data_preparation\04_integracion.py",
        r"training\nucleo\modeling\01_muestras.py"
    ]
    
    for step in steps:
        print(f"Ejecutando {step}...")
        subprocess.run([sys.executable, step], cwd=str(BACKEND_ROOT), check=True)
        
    print("Proceso completado.")

if __name__ == "__main__":
    main()

