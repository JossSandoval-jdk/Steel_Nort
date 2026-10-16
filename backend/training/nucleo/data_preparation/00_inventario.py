import os
import re
import subprocess
from pathlib import Path

import pandas as pd

import config
import utils

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


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


def cobertura_fechas(dir_corrida):
    """Rango de fechas y dias cubiertos a partir de metrics.log (I-1.1).

    Devuelve rango_inicio/rango_fin, dias_unicos (dias con datos) y
    dias_vacios (dias sin datos dentro del rango), o None si no hay datos.
    """
    ruta = os.path.join(dir_corrida, config.NOMBRE_METRICAS)
    if not os.path.isfile(ruta):
        return None
    inicio = fin = None
    dias = set()
    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        for linea in f:
            m = TS_RE.match(linea)
            if not m:
                continue
            ts = m.group(0)
            if inicio is None or ts < inicio:
                inicio = ts
            if fin is None or ts > fin:
                fin = ts
            dias.add(ts[:10])
    if inicio is None:
        return None
    dias_rango = (pd.Timestamp(fin[:10]) - pd.Timestamp(inicio[:10])).days + 1
    return {
        "rango_inicio": inicio,
        "rango_fin": fin,
        "dias_unicos": len(dias),
        "dias_vacios": dias_rango - len(dias),
        "cobertura_dias_pct": round(100.0 * len(dias) / dias_rango, 2),
        "_dias": dias,
    }


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
    cobertura = []
    dias_global = set()
    global_inicio = global_fin = None
    for corrida in corridas:
        dir_corrida = corridas_info[corrida]["ruta"]
        grupo = corridas_info[corrida]["grupo"]
        origen = utils.leer_origen(dir_corrida, grupo=grupo)

        cov = cobertura_fechas(dir_corrida)
        if cov:
            dias_global |= cov.pop("_dias")
            if global_inicio is None or cov["rango_inicio"] < global_inicio:
                global_inicio = cov["rango_inicio"]
            if global_fin is None or cov["rango_fin"] > global_fin:
                global_fin = cov["rango_fin"]
        else:
            cov = {"rango_inicio": None, "rango_fin": None,
                   "dias_unicos": 0, "dias_vacios": None,
                   "cobertura_dias_pct": None}
        cobertura.append({"corrida": corrida, "grupo": grupo, **cov})

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

    # Cobertura de fechas (indicador I-1.1): rango, dias con datos y huecos,
    # por corrida y global sobre todos los metrics.log.
    if global_inicio and dias_global:
        dias_rango_g = ((pd.Timestamp(global_fin[:10])
                         - pd.Timestamp(global_inicio[:10])).days + 1)
        cobertura.append({
            "corrida": "(global)", "grupo": "(todos)",
            "rango_inicio": global_inicio, "rango_fin": global_fin,
            "dias_unicos": len(dias_global),
            "dias_vacios": dias_rango_g - len(dias_global),
            "cobertura_dias_pct": round(100.0 * len(dias_global)
                                        / dias_rango_g, 2),
        })
    df_cov = pd.DataFrame(cobertura)
    ruta_cov = os.path.join(config.DIR_INVENTARIO, "cobertura_fechas.csv")
    df_cov.to_csv(ruta_cov, index=False, encoding="utf-8-sig")
    log(f"Cobertura de fechas (I-1.1): {ruta_cov}")

    print("\n=== RESUMEN INVENTARIO ===")
    piv = df.pivot_table(
        index="corrida", columns="fuente", values="existe", aggfunc="first"
    )
    print(piv.to_string())
    print(f"\nTotal registros (corridas x fuentes): {len(df)}")

    print("\n=== COBERTURA DE FECHAS (I-1.1) ===")
    print(df_cov[["corrida", "rango_inicio", "rango_fin", "dias_unicos",
                  "dias_vacios", "cobertura_dias_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()