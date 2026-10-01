import os
import subprocess
from pathlib import Path

import pandas as pd

import config
import utils


def log(msg):
    print(f"[INVENTARIO] {msg}", flush=True)


def contar_lineas(ruta):
    """Cuenta líneas con wc -l; si falla, lee en binario."""
    try:
        return int(subprocess.check_output(["wc", "-l", str(ruta)]).split()[0])
    except Exception:
        with open(ruta, "rb") as f:
            return sum(1 for _ in f)


def obtener_info_archivo(ruta):
    try:
        ruta_p = Path(ruta)
        tamano_mb = round(ruta_p.stat().st_size / (1024 * 1024), 4)
        return tamano_mb, contar_lineas(ruta_p)
    except Exception as e:
        log(f"Advertencia al leer {ruta}: {e}")
        return 0.0, 0


def main():
    if not os.path.isdir(config.OUTPUT_BASE_DIR):
        log(f"Directorio no encontrado: {config.OUTPUT_BASE_DIR}")
        return

    corridas_info = utils.descubrir_corridas()

    # Baseline primero, luego anomalías
    corridas = sorted(
        corridas_info,
        key=lambda c: (corridas_info[c]["grupo"] != "baseline", c),
    )
    log(f"Corridas encontradas ({len(corridas)}): {corridas}")

    if not corridas:
        log("No se encontraron corridas.")
        return

    registros = []
    for corrida in corridas:
        dir_corrida = corridas_info[corrida]["ruta"]
        grupo = corridas_info[corrida]["grupo"]
        origen = utils.leer_origen(dir_corrida, grupo=grupo)

        for fuente in config.ARCHIVOS_ENTRADA:
            ruta = os.path.join(dir_corrida, fuente)
            existe = os.path.isfile(ruta)
            tamano_mb, lineas = obtener_info_archivo(ruta) if existe else (0.0, 0)

            registros.append({
                "corrida": corrida,
                "grupo": grupo,
                "es_carga_normal": origen.get("es_carga_normal"),
                "fuente": fuente,
                "existe": existe,
                "tamano_mb": tamano_mb,
                "lineas": lineas,
            })

    df = pd.DataFrame(registros)
    os.makedirs(config.DIR_INVENTARIO, exist_ok=True)
    ruta_salida = os.path.join(config.DIR_INVENTARIO, config.ARCHIVO_INVENTARIO)
    df.to_csv(ruta_salida, index=False, encoding="utf-8-sig")
    log(f"Inventario guardado en: {ruta_salida}")

    print("\n=== RESUMEN INVENTARIO ===")
    piv = df.pivot_table(
        index="corrida", columns="fuente", values="existe", aggfunc="first"
    )
    print(piv.to_string())
    print(f"\nTotal registros (corridas x fuentes): {len(df)}")


if __name__ == "__main__":
    main()