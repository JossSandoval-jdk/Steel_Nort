"""
01_seleccion.py
===============

Paso 1 del Pipeline de Preparación de Datos (CRISP-DM):
Selección de Variables.

Genera un catálogo centralizado de las variables disponibles
para la preparación de datos, utilizando el diccionario
canónico definido en config.py.

Las variables se clasifican posteriormente como:
    - Principales
    - Diagnóstico
    - Redundantes
    - Requieren corrección
    - Excluidas por medición no confiable

Este paso NO extrae datos y NO procesa anomalías.
"""

from pathlib import Path

import pandas as pd

import config


def log(msg):
    print(f"[SELECCION] {msg}", flush=True)


def main():

    # ========================================================
    # 1. OBTENER VARIABLES CANÓNICAS
    # ========================================================

    variables_principales = set(config.VARIABLES_PRINCIPALES)
    variables_diagnostico = set(config.VARIABLES_DIAGNOSTICO)
    variables_redundantes = set(config.VARIABLES_REDUNDANTES)
    variables_correccion = set(config.VARIABLES_REQUIEREN_CORRECCION)
    variables_excluidas = set(config.EXCLUIR_MEDICION_CORRUPTA)

    # ========================================================
    # 2. CONSTRUIR CATÁLOGO
    # ========================================================

    filas = []

    for f in config.FEATURES_SELECCIONADAS:

        columna = f["columna"]

        if columna in variables_excluidas:
            clasificacion = "excluida"
        elif columna in variables_principales:
            clasificacion = "principal"
        elif columna in variables_redundantes:
            clasificacion = "redundante"
        elif columna in variables_correccion:
            clasificacion = "requiere_correccion"
        elif columna in variables_diagnostico:
            clasificacion = "diagnostico"
        else:
            clasificacion = "disponible"

        filas.append({
            "columna": columna,
            "fuente": f["fuente"],
            "dominio": f["dominio"],
            "tipo": f["tipo"],
            "descripcion": f.get("descripcion", ""),
            "clasificacion": clasificacion,
        })

    # ========================================================
    # 3. CREAR DATAFRAME
    # ========================================================

    df = pd.DataFrame(filas)

    # ========================================================
    # 4. GUARDAR CATÁLOGO
    # ========================================================

    dir_inventario = Path(config.DIR_INVENTARIO)
    dir_inventario.mkdir(parents=True, exist_ok=True)

    ruta_salida = dir_inventario / config.ARCHIVO_VARIABLES

    df.to_csv(
        ruta_salida,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # 5. REGISTRO
    # ========================================================

    log(f"Variables seleccionadas: {len(df)}")
    log(f"Guardado en: {ruta_salida}")

    # ========================================================
    # 6. RESUMEN POR DOMINIO
    # ========================================================

    print("\n=== RESUMEN SELECCIÓN POR DOMINIO ===")
    print(df.groupby("dominio").size().to_string())

    # ========================================================
    # 7. RESUMEN POR CLASIFICACIÓN
    # ========================================================

    print("\n=== RESUMEN POR CLASIFICACIÓN ===")
    print(df.groupby("clasificacion").size().to_string())


if __name__ == "__main__":
    main()