"""
01_seleccion.py
===============
Inventario de corridas y catálogo de variables.

Entrada : output/ con corridas crudas (baseline/, anomalias/)
Salida  : output/inventario/
            - inventario_corridas.csv
            - cobertura_fechas.csv
            - variables_seleccionadas.csv

Etiquetas: la verdad está en origen.json ('es_carga_normal').
La carpeta solo organiza; si no hay etiqueta, queda None.
"""

import os
import re
import subprocess
from datetime import date

import pandas as pd

from pipeline_config import config, utils


TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


def log(msg):
    print(f"[SELECCION] {msg}", flush=True)


# ==========================================
# Inventario de archivos
# ==========================================
def contar_lineas(ruta):
    """wc -l con fallback a lectura binaria."""
    try:
        return int(subprocess.check_output(["wc", "-l", str(ruta)]).split()[0])
    except Exception:
        with open(ruta, "rb") as f:
            return sum(1 for _ in f)


def obtener_info_archivo(ruta):
    """Devuelve (tamaño_mb, líneas)."""
    try:
        ruta_abs = os.path.abspath(ruta)
        tamano_mb = round(os.path.getsize(ruta_abs) / (1024 * 1024), 4)
        return tamano_mb, contar_lineas(ruta_abs)
    except Exception as e:
        log(f"Advertencia al leer {ruta}: {e}")
        return 0.0, 0


def cobertura_fechas(dir_corrida):
    """Rango de fechas y días cubiertos según metrics.log."""
    ruta = os.path.join(dir_corrida, config.NOMBRE_METRICAS)
    if not os.path.isfile(ruta):
        return None

    inicio = fin = None
    dias = set()
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for linea in f:
            m = TS_RE.match(linea)
            if not m:
                continue
            ts = m.group(0)
            inicio = ts if inicio is None else min(inicio, ts)
            fin = ts if fin is None else max(fin, ts)
            dias.add(ts[:10])

    if inicio is None:
        return None

    total = (date.fromisoformat(fin[:10]) - date.fromisoformat(inicio[:10])).days + 1
    return {
        "rango_inicio": inicio,
        "rango_fin": fin,
        "dias_unicos": len(dias),
        "dias_vacios": total - len(dias),
        "cobertura_dias_pct": round(100 * len(dias) / total, 2),
        "_dias": dias,
    }


# ==========================================
# Catálogo de variables
# ==========================================
def clasificar(columna, conjuntos):
    """Clasifica una columna según prioridad."""
    orden = [
        ("excluida",        conjuntos["excluidas"]),
        ("redundante",      conjuntos["redundantes"]),
        ("contador_a_tasa", conjuntos["a_tasa"]),
        ("contador",        conjuntos["contador"]),
        ("continua",        conjuntos["continua"]),
        ("feature_modelo",  conjuntos["features"]),
    ]
    for etiqueta, conjunto in orden:
        if columna in conjunto:
            return etiqueta
    return "disponible"


def catalogo_variables():
    """DataFrame con todas las variables clasificadas."""
    conjuntos = {
        "features":    set(config.FEATURES_MODELO),
        "continua":    set(config.METRICAS_CONTINUAS),
        "contador":    set(config.METRICAS_CONTADOR),
        "a_tasa":      set(config.METRICAS_A_TASA),
        "excluidas":   set(config.EXCLUIR_MEDICION_CORRUPTA),
        "redundantes": set(config.VARIABLES_REDUNDANTES),
    }

    # Avisos de solapamiento
    for nombre, s in {
        "features ∩ redundantes": conjuntos["features"] & conjuntos["redundantes"],
        "features ∩ excluidas":   conjuntos["features"] & conjuntos["excluidas"],
        "continua ∩ contador":    conjuntos["continua"] & conjuntos["contador"],
    }.items():
        if s:
            log(f"⚠ {nombre}: {sorted(s)}")

    universo = set().union(*conjuntos.values())
    df = pd.DataFrame([
        {
            "columna": col,
            "clasificacion": clasificar(col, conjuntos),
            "en_features_modelo": col in conjuntos["features"],
        }
        for col in sorted(universo)
    ])

    huerfanas = conjuntos["features"] - (
        conjuntos["continua"] | conjuntos["contador"] | conjuntos["a_tasa"]
    )
    if huerfanas:
        log(f"⚠ Features sin tipo de métrica: {sorted(huerfanas)}")

    return df


# ==========================================
# Main
# ==========================================
def main():
    if not os.path.isdir(config.OUTPUT_BASE_DIR):
        log(f"Directorio no encontrado: {config.OUTPUT_BASE_DIR}")
        return

    os.makedirs(config.DIR_INVENTARIO, exist_ok=True)

    corridas_info = utils.descubrir_corridas()
    corridas = sorted(
        corridas_info,
        key=lambda c: (corridas_info[c]["grupo"] != "baseline", c),
    )
    log(f"Corridas encontradas ({len(corridas)}): {corridas}")
    if not corridas:
        log("No se encontraron corridas.")
        return

    # --- Inventario + cobertura ---
    registros, cobertura = [], []
    dias_global, g_inicio, g_fin = set(), None, None
    conflictos = 0

    for corrida in corridas:
        info = corridas_info[corrida]
        dir_corrida, carpeta = info["ruta"], info["grupo"]
        origen = utils.leer_origen(dir_corrida, grupo=carpeta)
        etiqueta = origen.get("es_carga_normal")   # True / False / None

        # Aviso si carpeta y etiqueta se contradicen
        if etiqueta is not None and etiqueta != (carpeta == "baseline"):
            log(f"⚠ {corrida}: carpeta='{carpeta}' pero etiqueta={etiqueta}")
            conflictos += 1

        cov = cobertura_fechas(dir_corrida)
        if cov:
            dias_global |= cov.pop("_dias")
            g_inicio = cov["rango_inicio"] if g_inicio is None else min(g_inicio, cov["rango_inicio"])
            g_fin    = cov["rango_fin"]    if g_fin    is None else max(g_fin,    cov["rango_fin"])
        else:
            cov = {"rango_inicio": None, "rango_fin": None,
                   "dias_unicos": 0, "dias_vacios": None,
                   "cobertura_dias_pct": None}

        cobertura.append({"corrida": corrida, "carpeta": carpeta, **cov})

        for fuente in config.ARCHIVOS_ENTRADA:
            ruta = os.path.join(dir_corrida, fuente)
            existe = os.path.isfile(ruta)
            tamano_mb, lineas = obtener_info_archivo(ruta) if existe else (0.0, 0)
            registros.append({
                "corrida": corrida,
                "carpeta": carpeta,
                "etiqueta_manual": etiqueta,
                "tipo_fallo": origen.get("tipo_fallo"),
                "fuente": fuente,
                "existe": existe,
                "tamano_mb": tamano_mb,
                "lineas": lineas,
            })

    df = pd.DataFrame(registros)
    df.to_csv(os.path.join(config.DIR_INVENTARIO, config.ARCHIVO_INVENTARIO),
              index=False, encoding="utf-8-sig")
    log(f"Inventario guardado: {config.ARCHIVO_INVENTARIO}")

    # Fila global de cobertura
    if g_inicio and dias_global:
        total = (date.fromisoformat(g_fin[:10]) - date.fromisoformat(g_inicio[:10])).days + 1
        cobertura.append({
            "corrida": "(global)", "carpeta": "(todas)",
            "rango_inicio": g_inicio, "rango_fin": g_fin,
            "dias_unicos": len(dias_global),
            "dias_vacios": total - len(dias_global),
            "cobertura_dias_pct": round(100 * len(dias_global) / total, 2),
        })

    df_cov = pd.DataFrame(cobertura)
    df_cov.to_csv(os.path.join(config.DIR_INVENTARIO, config.ARCHIVO_COBERTURA),
                  index=False, encoding="utf-8-sig")
    log(f"Cobertura guardada: {config.ARCHIVO_COBERTURA}")

    # --- Catálogo de variables ---
    df_var = catalogo_variables()
    df_var.to_csv(os.path.join(config.DIR_INVENTARIO, config.ARCHIVO_VARIABLES),
                  index=False, encoding="utf-8-sig")
    log(f"Catálogo: {config.ARCHIVO_VARIABLES} ({len(df_var)} variables)")

    # --- Resumen por consola ---
    print("\n=== INVENTARIO ===")
    print(df.pivot_table(index="corrida", columns="fuente",
                         values="existe", aggfunc="first").to_string())

    print("\n=== ETIQUETAS ===")
    print(df.drop_duplicates("corrida")
            .groupby(["carpeta", "etiqueta_manual"], dropna=False)
            .size().to_string())
    if conflictos:
        print(f"⚠ {conflictos} corridas con carpeta ≠ etiqueta")

    print("\n=== COBERTURA ===")
    print(df_cov[["corrida", "rango_inicio", "rango_fin",
                  "dias_unicos", "dias_vacios", "cobertura_dias_pct"]]
          .to_string(index=False))

    print("\n=== VARIABLES ===")
    print(df_var.groupby("clasificacion").size().to_string())
    print(f"Features del modelo: {df_var['en_features_modelo'].sum()}/{len(df_var)}")


if __name__ == "__main__":
    main()