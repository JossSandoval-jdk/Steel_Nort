import subprocess
import sys
import os

prep_pipeline = [
    "data_preparation/00_inventario.py",
    "data_preparation/01_seleccion.py",
    "data_preparation/02_limpieza.py",
    "data_preparation/03_transformacion.py",
    "data_preparation/04_integracion.py"
]

modelos_pipeline = {
    "1": ("Isolation Forest", "training/nucleo/modeling/03_deteccion_isolation_forest.py"),
    "2": ("LOF", "training/nucleo/modeling/03.1_deteccion_lof.py"),
    "3": ("Elliptic Envelope", "training/nucleo/modeling/03.2_deteccion_elliptic_envelope.py"),
    "4": ("OCSVM", "training/nucleo/modeling/03.3_deteccion_ocsvm.py"),
    "5": ("COPOD", "training/nucleo/modeling/03.4_deteccion_copod.py"),
}
# Fixed stray brace; updated comparison script path
comparacion_script = "training/nucleo/modeling/06_comparacion_modelado.py"

def ejecutar_lista(scripts):
    for script in scripts:
        if not os.path.exists(script):
            print(f"[Error] No se encontró el script: {script}")
            return False
            
        print(f"\n[Ejecutando] {script}...")
        try:
            result = subprocess.run([sys.executable, script], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"[Éxito] {script} completado.")
                if result.stdout.strip():
                    print(result.stdout)
            else:
                print(f"[Fallo] {script} terminó con error:")
                print(result.stderr)
                return False
        except Exception as e:
            print(f"[Excepción] Ocurrió un error inesperado: {e}")
            return False
    return True

def run():
    print("==========================================================")
    print("   STEELNORT - Orquestador Modular de Modelado y Tesis")
    print("==========================================================")
    
    if not os.path.exists("output"):
        os.makedirs("output")
        print("[Info] Carpeta 'output' creada.")

    print("\nSelecciona una opción de ejecución:")
    print(" [1] Pipeline Completo (Prep + Todos los Modelos + Comparación)")
    print(" [2] Solo Preparación de Datos (00 al 04)")
    print(" [3] Entrenar TODOS los Modelos en secuencia")
    print(" [4] Entrenar UN SOLO modelo por separado (Evita sobreescritura accidental)")
    print(" [5] Generar solo la Tabla Comparativa Global")
    
    opcion = input("\nIngrese el número de la opción deseada: ").strip()

    if opcion == "1":
        if ejecutar_lista(prep_pipeline):
            todos = [m[1] for m in modelos_pipeline.values()]
            if ejecutar_lista(todos):
                ejecutar_lista([comparacion_script])

    elif opcion == "2":
        ejecutar_lista(prep_pipeline)

    elif opcion == "3":
        todos = [m[1] for m in modelos_pipeline.values()]
        if ejecutar_lista(todos):
            ejecutar_lista([comparacion_script])

    elif opcion == "4":
        print("\nSelecciona el modelo que deseas reentrenar:")
        for k, v in modelos_pipeline.items():
            print(f" [{k}] {v[0]}")
        mod_op = input("Ingrese el número del modelo: ").strip()
        
        if mod_op in modelos_pipeline:
            nombre, ruta = modelos_pipeline[mod_op]
            print(f"\n--- REENTRENANDO AISLADAMENTE: {nombre} ---")
            if ejecutar_lista([ruta]):
                actualizar = input("¿Desea actualizar la tabla comparativa global ahora? (s/n): ").strip().lower()
                if actualizar == 's':
                    ejecutar_lista([comparacion_script])
        else:
            print("[Error] Opción de modelo no válida.")

    elif opcion == "5":
        ejecutar_lista([comparacion_script])
    else:
        print("[Error] Opción no válida.")

    print("\n==========================================================")
    print("   Proceso finalizado.")
    print("==========================================================")

if __name__ == "__main__":
    run()