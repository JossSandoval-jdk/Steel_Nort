"""
pipeline.py
===========

Menú para ejecutar los pasos del pipeline de preparación de datos.

Uso:
    python pipeline.py          # menú interactivo
    python pipeline.py 1        # corre solo el paso 1
    python pipeline.py all      # corre todo en orden
    python pipeline.py e        # muestra estado
    python pipeline.py l        # borra salidas
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

import config


# ==========================================
# PASOS (orden real según tus scripts)
# ==========================================
PASOS = [
    ("1", "Inventario",     "00_inventario.py"),
    ("2", "Selección",      "01_seleccion.py"),
    ("3", "Limpieza",       "02_limpieza.py"),
    ("4", "Transformación", "03_transformacion.py"),
    ("5", "Integración",    "04_integracion.py"),
    ("6", "Modelado",       "05_modelado.py"),
]


def log(msg):
    print(f"[PIPELINE] {msg}", flush=True)


def script_existe(nombre):
    return (Path(__file__).resolve().parent / nombre).is_file()


def correr_paso(numero, nombre, script):
    ruta = Path(__file__).resolve().parent / script

    if not ruta.is_file():
        log(f"⚠ {script} no encontrado. Se omite.")
        return False

    print(f"\n{'=' * 60}")
    print(f"  PASO {numero} — {nombre}  ({script})")
    print(f"{'=' * 60}\n")

    t0 = time.time()
    try:
        resultado = subprocess.run(
            [sys.executable, str(ruta)],
            cwd=str(ruta.parent),
            check=False,
        )
        duracion = time.time() - t0

        if resultado.returncode == 0:
            log(f"✔ {nombre} OK ({duracion:.2f}s)")
            return True
        log(f"✘ {nombre} FALLÓ (código {resultado.returncode})")
        return False

    except KeyboardInterrupt:
        log(f"✘ {nombre} interrumpido")
        return False
    except Exception as e:
        log(f"✘ {nombre} excepción: {e}")
        return False


def correr_todo():
    log("Ejecutando pipeline completo...")
    for numero, nombre, script in PASOS:
        if not script_existe(script):
            log(f"⚠ {script} no existe. Se omite.")
            continue
        if not correr_paso(numero, nombre, script):
            log("Pipeline detenido por fallo.")
            return
    log("Pipeline completo sin errores.")


def mostrar_estado():
    print("\n=== ESTADO DEL PIPELINE ===\n")

    inv = config.DIR_INVENTARIO / config.ARCHIVO_INVENTARIO
    print(f"Inventario   : {'✔' if inv.exists() else '✘'}  {inv}")

    var = config.DIR_INVENTARIO / config.ARCHIVO_VARIABLES
    print(f"Variables    : {'✔' if var.exists() else '✘'}  {var}")

    if config.DIR_LIMPIO.exists():
        for c in sorted(config.DIR_LIMPIO.iterdir()):
            if c.is_dir():
                met = (c / config.NOMBRE_METRICAS_LIMPIO).exists()
                evt = (c / config.NOMBRE_EVENTS_LIMPIO).exists()
                tra = (c / config.NOMBRE_TRANSFORMADO).exists()
                print(f"  {c.name:<20} metricas={met} eventos={evt} transformado={tra}")

    ds = config.DIR_INTEGRADO / config.ARCHIVO_DATASET_INTEGRADO
    print(f"Integrado    : {'✔' if ds.exists() else '✘'}  {ds}")

    if config.DIR_MODELADO.exists():
        for a in sorted(config.DIR_MODELADO.glob("*")):
            print(f"  modelado/{a.name}")

    print()


CARPETAS_SALIDA = [
    config.DIR_INVENTARIO,
    config.DIR_LIMPIO,
    config.DIR_INTEGRADO,
    config.DIR_MODELADO,
]


def limpiar_salidas():
    print("\nSe borrarán las siguientes carpetas:")
    for d in CARPETAS_SALIDA:
        print(f"  - {d}")

    respuesta = input("\n¿Confirmas? (s/N): ").strip().lower()
    if respuesta != "s":
        log("Cancelado.")
        return

    for d in CARPETAS_SALIDA:
        if d.exists():
            shutil.rmtree(d)
            log(f"Borrado: {d}")
    log("Limpieza completada.")


def mostrar_menu():
    print("\n" + "=" * 60)
    print("  PIPELINE STEELNORT")
    print("=" * 60)
    for numero, nombre, script in PASOS:
        existe = "✔" if script_existe(script) else "✘"
        print(f"  {numero}. {nombre:<15} {existe}  {script}")
    print("  a. Correr todo en orden")
    print("  e. Ver estado")
    print("  l. Limpiar salidas")
    print("  q. Salir")
    print("=" * 60)


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "all":
            correr_todo(); return
        if arg == "estado" or arg == "e":
            mostrar_estado(); return
        if arg == "limpiar" or arg == "l":
            limpiar_salidas(); return
        for numero, nombre, script in PASOS:
            if arg == numero:
                correr_paso(numero, nombre, script); return
        log(f"Opción desconocida: {arg}")
        return

    while True:
        mostrar_menu()
        opcion = input("Opción: ").strip().lower()

        if opcion == "q":
            break
        elif opcion == "a":
            correr_todo()
        elif opcion == "e":
            mostrar_estado()
        elif opcion == "l":
            limpiar_salidas()
        else:
            encontrado = False
            for numero, nombre, script in PASOS:
                if opcion == numero:
                    correr_paso(numero, nombre, script)
                    encontrado = True
                    break
            if not encontrado:
                log(f"Opción inválida: {opcion}")


if __name__ == "__main__":
    main()