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
    - cantidad de líneas

Salida:
    datasets/inventario/inventario_corridas.csv
"""

import os

import pandas as pd

import config


def log(msg):
    print(f"[INVENTARIO] {msg}", flush=True)


def contar_lineas(ruta):
    """
    Cuenta la cantidad de líneas de un archivo.
    """
    try:
        with open(
            ruta,
            encoding=config.ENCODING,
            errors="replace"
        ) as f:
            return sum(1 for _ in f)

    except Exception:
        return 0


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

    # Corridas reales: subcarpetas de baseline/ (normal) y anomalias/
    # (con timeline), más cualquier corrida legacy en la raíz.
    corridas = config.descubrir_corridas()

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

        dir_corrida = config.ruta_corrida(
            config.OUTPUT_BASE_DIR,
            corrida
        )

        for fuente in fuentes:

            ruta = os.path.join(
                dir_corrida,
                fuente
            )

            existe = os.path.isfile(ruta)

            registros.append({
                "corrida": corrida,
                "fuente": fuente,
                "existe": existe,
                "lineas": (
                    contar_lineas(ruta)
                    if existe
                    else 0
                ),
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

    piv = df.pivot(
        index="corrida",
        columns="fuente",
        values="existe"
    )

    print(piv.to_string())

    print(
        f"\nTotal registros "
        f"(corridas x fuentes): {len(df)}"
    )


if __name__ == "__main__":
    main()