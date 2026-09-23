import sys
import subprocess
import os
import pandas as pd
from pathlib import Path

BACKEND_ROOT = Path(r"d:\SteelNort_web\backend")
MODELING_DIR = BACKEND_ROOT / "training" / "nucleo" / "modeling"

def main():
    print("Iniciando Pipeline Aparte de Comparacion de Modelos (Experimental)...")
    
    scripts_experimentales = [
        "experimental/03.1_deteccion_lof.py",
        "experimental/03.2_deteccion_elliptic_envelope.py",
        "experimental/03.3_deteccion_ocsvm.py",
        "experimental/03.4_deteccion_copod.py",
        "experimental/06_comparacion_modelado.py"
    ]
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(MODELING_DIR)
    
    for script in scripts_experimentales:
        print(f"\n=> Ejecutando {script}...")
        subprocess.run([sys.executable, script], cwd=str(MODELING_DIR), env=env, check=True)
        
    print("\n================ RESULTADOS DE LA COMPARACION ================\n")
    
    tabla_csv = BACKEND_ROOT / "training" / "output" / "modelado" / "deteccion" / "tabla_comparativa_modelos.csv"
    if tabla_csv.is_file():
        df = pd.read_csv(tabla_csv)
        print(df.to_string(index=False))
    else:
        print("No se encontro la tabla comparativa.")

if __name__ == "__main__":
    main()

