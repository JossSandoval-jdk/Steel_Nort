"""
04_integracion.py
=================

Paso 5: concatena las corridas transformadas en un único dataset.

Salida:
    output/integrado/
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

    # Baseline primero, luego anomalías; dentro, por corrida y timestamp.
    # (orden alfabético de "grupo" pondría anomalias antes que baseline)
    df["_orden_grupo"] = df["grupo"].map(
        {"baseline": 0, "anomalias": 1}).fillna(9)
    df = df.sort_values(
        ["_orden_grupo", "run_name", "timestamp"]
    ).drop(columns="_orden_grupo").reset_index(drop=True)

    # Warm-up: descartar las primeras N muestras de cada corrida. La 1a
    # muestra no tiene "anterior" -> tasas (x_per_sec) quedan nulas.
    if config.N_MUESTRAS_WARMUP > 0:
        antes = len(df)
        df = df[df.groupby("run_name").cumcount() >= config.N_MUESTRAS_WARMUP]
        df = df.reset_index(drop=True)
        log(f"   Warm-up: -{antes - len(df)} muestras "
            f"({config.N_MUESTRAS_WARMUP} por corrida)")

    # Descartar columnas casi vacias (ej. metricas de una sola captura)
    umbral = config.CALIDAD_MAX_NULOS_COLUMNA
    if umbral is not None:
        proteger = {"timestamp", "run_name", "grupo", "experiment_id"}
        nulos = df.isna().mean()
        descartar = [c for c in df.columns
                     if c not in proteger and nulos[c] > umbral]
        if descartar:
            df = df.drop(columns=descartar)
            log(f"   Columnas descartadas (>{umbral:.0%} nulos): {descartar}")

    # experiment_id secuencial por corrida
    runs = df["run_name"].drop_duplicates().tolist()
    mapa = {r: f"exp_{i+1:02d}" for i, r in enumerate(runs)}
    df["experiment_id"] = df["run_name"].map(mapa)

    # Columnas de contexto al inicio (no cambia el orden relativo de las
    # features, así que scaler/bundle siguen compatibles)
    contexto = ["timestamp", "run_name", "grupo", "experiment_id"]
    df = df[contexto + [c for c in df.columns if c not in contexto]]

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


def calidad_indice(df):
    """Indice I-1.2 (Objetivos_y_requisitos.md) = (C + Co + V) / 3.

    - completitud: 1 - celdas_nulas / celdas_totales
    - consistencia: 1 - filas_duplicadas / filas_totales
    - validez: % de valores dentro de config.RANGOS_VALIDEZ (promedio)
    - timestamps_ordenados: 1 si cada corrida queda ordenada por timestamp
    """
    celdas = df.size
    nulas = int(df.isna().sum().sum())
    completitud = 1 - nulas / celdas if celdas else np.nan

    duplicadas = int(df.duplicated().sum())
    consistencia = 1 - duplicadas / len(df) if len(df) else np.nan

    rangos = {c: r for c, r in config.RANGOS_VALIDEZ.items()
              if c in df.columns}
    validez = (
        float(np.mean([df[c].between(lo, hi).mean()
                       for c, (lo, hi) in rangos.items()]))
        if rangos else np.nan
    )

    if {"run_name", "timestamp"} <= set(df.columns):
        orden_ok = bool(
            df.groupby("run_name")["timestamp"]
            .apply(lambda s: s.is_monotonic_increasing).all()
        )
    else:
        orden_ok = True

    indice = float(np.nanmean([completitud, consistencia, validez]))
    dimensiones = [
        ("completitud", completitud, config.CALIDAD_MIN_COMPLETITUD),
        ("consistencia", consistencia, config.CALIDAD_MIN_CONSISTENCIA),
        ("validez", validez, config.CALIDAD_MIN_VALIDEZ),
        ("timestamps_ordenados", 1.0 if orden_ok else 0.0, 1.0),
        ("indice_calidad", indice, config.CALIDAD_MIN_INDICE),
    ]
    filas = [
        {"dimension": d, "valor": round(float(v), 6),
         "minimo": m, "cumple": bool(v >= m)}
        for d, v, m in dimensiones
    ]
    detalle = {
        "nulas": nulas, "duplicadas": duplicadas,
        "celdas": int(celdas), "filas": int(len(df)),
        "variables_con_rango": sorted(rangos),
    }
    return pd.DataFrame(filas), indice, detalle


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

    # Indice de calidad I-1.2 = (completitud + consistencia + validez) / 3
    df_indice, calidad, detalle_cal = calidad_indice(df)
    ruta_ind = os.path.join(config.DIR_INTEGRADO,
                            config.ARCHIVO_INDICE_CALIDAD)
    df_indice.to_csv(ruta_ind, index=False, encoding="utf-8-sig")
    for _, row in df_indice.iterrows():
        log(f"  {row['dimension']}: {row['valor']} (min {row['minimo']}) "
            f"{'OK' if row['cumple'] else 'FALLA'}")
    log(f"Indice de calidad I-1.2 = {calidad:.4f} -> "
        f"{'CUMPLE' if calidad >= config.CALIDAD_MIN_INDICE else 'NO CUMPLE'} "
        f"(>= {config.CALIDAD_MIN_INDICE}) -> {ruta_ind}")

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
        "calidad_i_1_2": {
            "indice": round(calidad, 6),
            "meta": config.CALIDAD_MIN_INDICE,
            "cumple": bool(calidad >= config.CALIDAD_MIN_INDICE),
            "dimensiones": df_indice.to_dict(orient="records"),
            **detalle_cal,
        },
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
    print(df.groupby("run_name", sort=False).size().to_string())


if __name__ == "__main__":
    main()