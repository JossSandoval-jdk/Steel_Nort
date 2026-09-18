import subprocess
import sys
import os

# Pipeline completo: preparación de datos + modelos de detección
pipeline = [
    "data_preparation/00_inventario.py",
    "data_preparation/01_seleccion.py",
    "data_preparation/02_limpieza.py",
    "data_preparation/03_transformacion.py",
    "data_preparation/04_integracion.py",
    # Scripts de modelado y detección de anomalías
    "modelado/03_deteccion_isolation_forest.py",
    "modelado/03.1_deteccion_lof.py",
    "modelado/03.2_deteccion_elliptic_envelope.py",
    "modelado/03.3_deteccion_ocsvm.py",
    "modelado/03.4_deteccion_copod.py"
]

def run():
    print("==========================================================")
    print("   STEELNORT - Orquestador del Pipeline y Modelado")
    print("==========================================================")
    
    # Crear carpeta de output si no existe
    if not os.path.exists("output"):
        os.makedirs("output")
        print("[Info] Carpeta 'output' creada.")

    for script in pipeline:
        if not os.path.exists(script):
            print(f"[Error] No se encontró el script: {script}")
            continue
            
        print(f"\n[Ejecutando] {script}...")
        try:
            # Ejecuta usando el intérprete de Python actual
            result = subprocess.run([sys.executable, script], capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"[Éxito] {script} completado.")
                if result.stdout.strip():
                    print(result.stdout)
            else:
                print(f"[Fallo] {script} terminó con error:")
                print(result.stderr)
                break # Detener si un paso falla
        except Exception as e:
            print(f"[Excepción] Ocurrió un error inesperado: {e}")
            break
            
    print("\n==========================================================")
    print("   Proceso completo de pipeline y modelado finalizado.")
    print("   Los resultados se encuentran en la carpeta 'output/'.")
    print("==========================================================")

if __name__ == "__main__":
    run()