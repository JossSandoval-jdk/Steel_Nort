import subprocess
import sys
import os

# Lista de scripts de preparación en orden secuencial
pipeline = [
    "data_preparation/00_inventario.py",
    "data_preparation/01_seleccion.py",
    "data_preparation/02_limpieza.py",
    "data_preparation/03_transformacion.py",
    "data_preparation/04_integracion.py",
    "data_preparation/05_seleccion_variables_clave.py",
    "data_preparation/06_seleccion_variables_principales.py"
]

def run():
    print("==========================================================")
    print("   STEELNORT - Orquestador del Pipeline de Datos")
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
            else:
                print(f"[Fallo] {script} terminó con error:")
                print(result.stderr)
                break # Detener si un paso falla
        except Exception as e:
            print(f"[Excepción] Ocurrió un error inesperado: {e}")
            break
            
    print("\n==========================================================")
    print("   Proceso de preparación de datos finalizado.")
    print("   Los resultados se encuentran en la carpeta 'output/'.")
    print("==========================================================")

if __name__ == "__main__":
    run()
