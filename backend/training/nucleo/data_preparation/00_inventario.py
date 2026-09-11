"""
00_inventario.py
================

Paso 0 de la preparación de datos (CRISP-DM):
inventario de corridas y fuentes.

Recorre OUTPUT_BASE_DIR, identifica cada corrida (subcarpeta)
y, para cada fuente de captura:

    - metrics.log
    - events.log
    - sqlserver_logs.log

registra:
    - si existe
    - tamaño en MB
    - cantidad de líneas

Salida:
    datasets/inventario/inventario_corridas.csv
"""

import os
from pathlib import Path

import pandas as pd

import config


def log(msg):
    print(f"[INVENTARIO] {msg}", flush=True)


def obtener_info_archivo(ruta):
    """
    Retorna el tamaño en MB y la cantidad de líneas de un archivo,
    manejando excepciones de manera robusta.
    """
    try:
        ruta_p = Path(ruta)
        tamano_mb = round(ruta_p.stat().st_size / (1024 * 1024), 4)
        with open(ruta_p, encoding=config.ENCODING, errors="replace") as f:
            lineas = sum(1 for _ in f)
        return tamano_mb, lineas
    except Exception as e:
        log(f"Advertencia al leer {ruta}: {e}")
        return 0.0, 0


def main():

    # ========================================================
    # 1. VALIDAR DIRECTORIO PRINCIPAL
    # ========================================================

    if not os.path.isdir(config.OUTPUT_BASE_DIR):
        log(
            f"Directorio de datos no encontrado: "
            f"{config.OUTPUT_BASE_DIR}"
        )
        return

    # ========================================================
    # 2. IDENTIFICAR CORRIDAS / CARGAS
    # ========================================================

    # Excluir carpetas de salida del propio pipeline
    # (inventario, limpio, integrado, datasets).
    dirs_salida = {
        os.path.basename(d)
        for d in (
            config.DIR_DATASETS,
            config.DIR_INVENTARIO,
            config.DIR_LIMPIO,
            config.DIR_INTEGRADO,
        )
    }

    corridas = sorted([
        d
        for d in os.listdir(config.OUTPUT_BASE_DIR)
        if os.path.isdir(
            os.path.join(config.OUTPUT_BASE_DIR, d)
        )
        and d not in dirs_salida
    ])

    log(
        f"Corridas encontradas ({len(corridas)}): "
        f"{corridas}"
    )

    if not corridas:
        log("No se encontraron corridas/cargas.")
        return

    # ========================================================
    # 3. FUENTES DE CADA CORRIDA
    # ========================================================

    fuentes = [
        config.NOMBRE_METRICAS,
        config.NOMBRE_EVENTS,
        config.NOMBRE_SQLSERVER_LOGS,
    ]

    # ========================================================
    # 4. CONSTRUIR INVENTARIO
    # ========================================================

    registros = []

    for corrida in corridas:

        dir_corrida = os.path.join(
            config.OUTPUT_BASE_DIR,
            corrida
        )

        for fuente in fuentes:

            ruta = os.path.join(
                dir_corrida,
                fuente
            )

            existe = os.path.isfile(ruta)
            tamano_mb, lineas = obtener_info_archivo(ruta) if existe else (0.0, 0)

            registros.append({
                "corrida": corrida,
                "fuente": fuente,
                "existe": existe,
                "tamano_mb": tamano_mb,
                "lineas": lineas,
            })

    # ========================================================
    # 5. CREAR DATAFRAME
    # ========================================================

    df = pd.DataFrame(registros)

    # ========================================================
    # 6. GUARDAR INVENTARIO
    # ========================================================

    os.makedirs(
        config.DIR_INVENTARIO,
        exist_ok=True
    )

    ruta_salida = os.path.join(
        config.DIR_INVENTARIO,
        config.ARCHIVO_INVENTARIO
    )

    df.to_csv(
        ruta_salida,
        index=False,
        encoding="utf-8-sig"
    )

    log(
        f"Inventario guardado en: "
        f"{ruta_salida}"
    )

    # ========================================================
    # 7. RESUMEN
    # ========================================================

    print("\n=== RESUMEN INVENTARIO ===")

    piv = df.pivot_table(
        index="corrida",
        columns="fuente",
        values="existe",
        aggfunc="first"
    )

    print(piv.to_string())

    print(
        f"\nTotal registros "
        f"(corridas x fuentes): {len(df)}"
    )


if __name__ == "__main__":
    main()