"""
04_integracion.py
=================

Paso 5: concatena las corridas transformadas en un único dataset.

Salida:
    output/integrado_v2/
        dataset_steelnort_preparado.csv
        reporte_calidad_datos.csv
        metadata_transformaciones.json
"""

import json
import os

import numpy as np
import pandas as pd

import config
import utils


def log(msg):
    print(f"[INTEGRACION] {msg}", flush=True)


def cargar_transformadas():
    """Lee datos_transformados.csv de cada corrida."""
    if not os.path.isdir(config.DIR_LIMPIO):
        return []

    corridas_info = utils.descubrir_corridas()
    corridas = sorted(
        corridas_info,
        key=lambda c: (corridas_info[c]["grupo"] != "baseline", c),
    )

    out = []
    for corrida in corridas:
        ruta = os.path.join(
            config.DIR_LIMPIO, corrida, config.NOMBRE_TRANSFORMADO
        )
        if not os.path.exists(ruta):
            log(f"   Sin transformado: {corrida}")
            continue

        try:
            df = pd.read_csv(ruta, encoding="utf-8-sig")
            if df.empty:
                log(f"   Vacío: {corrida}")
                continue

            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df = df.dropna(subset=["timestamp"])

            if df.empty:
                log(f"   Sin timestamps válidos: {corrida}")
                continue

            df["run_name"] = corrida
            df["grupo"] = corridas_info[corrida]["grupo"]
            out.append(df)

        except Exception as e:
            log(f"   ERROR leyendo {corrida}: {e}")

    return out


def construir_integrado(frames):
    """Concatena las corridas."""
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True, sort=False)

    # Baseline primero, luego anomalías; dentro, por timestamp
    df = df.sort_values(
        ["grupo", "run_name", "timestamp"]
    ).reset_index(drop=True)

    # experiment_id secuencial por corrida
    runs = df["run_name"].drop_duplicates().tolist()
    mapa = {r: f"exp_{i+1:02d}" for i, r in enumerate(runs)}
    df["experiment_id"] = df["run_name"].map(mapa)

    return df


def reporte_calidad(df, features):
    """Estadísticas básicas por feature."""
    filas = []
    n = len(df)

    for col in features:
        if col not in df.columns:
            continue
        s = df[col].dropna()
        filas.append({
            "columna": col,
            "total": n,
            "nulos": int(df[col].isna().sum()),
            "pct_nulos": round(df[col].isna().sum() / n * 100, 2),
            "unicos": int(df[col].nunique(dropna=True)),
            "media": round(float(s.mean()), 4) if len(s) else np.nan,
            "desv_std": round(float(s.std()), 4) if len(s) else np.nan,
            "min": round(float(s.min()), 4) if len(s) else np.nan,
            "max": round(float(s.max()), 4) if len(s) else np.nan,
        })
    return pd.DataFrame(filas)


def main():
    if not os.path.isdir(config.DIR_LIMPIO):
        log(f"No existe: {config.DIR_LIMPIO}")
        return

    frames = cargar_transformadas()
    if not frames:
        log("No hay datos transformados. Ejecuta 03_transformacion.py.")
        return

    log(f"Corridas a integrar ({len(frames)}): "
        f"{[f['run_name'].iloc[0] for f in frames]}")

    df = construir_integrado(frames)
    if df.empty:
        log("Dataset integrado vacío.")
        return

    os.makedirs(config.DIR_INTEGRADO, exist_ok=True)

    # Dataset integrado completo
    ruta_csv = os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_DATASET_INTEGRADO)
    df.to_csv(ruta_csv, index=False, encoding="utf-8-sig")
    log(f"Dataset integrado: {ruta_csv} ({df.shape[0]} x {df.shape[1]})")

    # Reporte de calidad sobre features del modelo
    reporte = reporte_calidad(df, config.FEATURES_MODELO)
    ruta_rep = os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_REPORTE_CALIDAD)
    reporte.to_csv(ruta_rep, index=False, encoding="utf-8-sig")
    log(f"Reporte de calidad: {ruta_rep}")

    # Metadata
    metadata = {
        "fase_crispdm": "Data Preparation",
        "fuentes": [
            config.NOMBRE_METRICAS,
            config.NOMBRE_EVENTS,
            config.NOMBRE_SQLSERVER_LOGS,
        ],
        "features_modelo": config.FEATURES_MODELO,
        "columnas_contexto": config.COLUMNAS_CONTEXTO,
        "total_corridas": int(df["run_name"].nunique()),
        "total_filas": int(len(df)),
        "nota_etiquetado": (
            "La columna 'grupo' indica procedencia (baseline/anomalias). "
            "No se usa para entrenamiento; solo para validación post-hoc."
        ),
    }
    ruta_meta = os.path.join(config.DIR_INTEGRADO, config.ARCHIVO_METADATA)
    with open(ruta_meta, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    log(f"Metadata: {ruta_meta}")

    print("\n=== RESUMEN INTEGRACION ===")
    print(f"Filas totales: {len(df)}")
    print(f"Columnas totales: {df.shape[1]}")
    print(f"Features del modelo: {len(config.FEATURES_MODELO)}")
    print("\nFilas por corrida:")
    print(df.groupby("run_name").size().to_string())


if __name__ == "__main__":
    main()