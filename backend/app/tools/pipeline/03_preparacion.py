"""
03_transformacion.py
====================
Pipeline completo: limpia + transforma + integra.

Entrada : output/ con corridas crudas (baseline/, anomalias/)
Salida  : output/preparado/
            - dataset_steelnort.parquet
            - metadata.json
            - reporte_calidad.csv

No genera CSVs intermedios por corrida.
"""

import importlib
import json
import os

import numpy as np
import pandas as pd

from pipeline_config import config, utils


# Import dinámico: el módulo empieza con número
limpieza = importlib.import_module("02_limpieza")


def log(msg):
    print(f"[TRANSFORMACION] {msg}", flush=True)


# ==========================================
# Pivot de métricas
# ==========================================
def pivot_metricas(df_metricas):
    """Pasa métricas de formato largo a ancho (una fila por timestamp)."""
    if df_metricas.empty:
        return pd.DataFrame()

    wide = df_metricas.pivot_table(
        index="timestamp", columns="metrica",
        values="valor", aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    return wide.sort_values("timestamp").reset_index(drop=True)


# ==========================================
# Tasas para contadores acumulativos
# ==========================================
def aplicar_tasas(wide):
    """Convierte total_reads / total_writes a tasa (Δ/Δt)."""
    wide = wide.sort_values("timestamp").reset_index(drop=True)
    dt = wide["timestamp"].diff().dt.total_seconds()

    for col in config.METRICAS_A_TASA:
        if col not in wide.columns:
            continue
        valores = pd.to_numeric(wide[col], errors="coerce")
        tasa = valores.diff().div(dt.replace(0, np.nan))
        # Deltas negativos = reset de contador → NaN
        wide[col] = tasa.where(tasa >= 0, np.nan).bfill()

    return wide


# ==========================================
# Eventos agregados
# ==========================================
def _asignar_a_muestras(df, timestamps):
    """Asigna cada evento a la siguiente muestra temporal."""
    muestras = (pd.DataFrame({"muestra_timestamp": pd.to_datetime(timestamps)})
                .drop_duplicates().sort_values("muestra_timestamp"))

    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    if df.empty or muestras.empty:
        return df.iloc[0:0].copy()

    asignado = pd.merge_asof(
        df, muestras,
        left_on="timestamp", right_on="muestra_timestamp",
        direction="forward",
    )
    return asignado.dropna(subset=["muestra_timestamp"])


def _contar_evento(df, out, evento, destino):
    subset = df[df["event_name"] == evento]
    counts = subset.groupby("muestra_timestamp").size()
    out[destino] = out["timestamp"].map(counts).fillna(0).astype(int)


def _contar_wait(df, out, prefijos, destino):
    if "wait_type" not in df.columns:
        out[destino] = 0
        return
    wt = df["wait_type"].fillna("").astype(str).str.upper()
    mask = wt.str.startswith(tuple(prefijos))
    counts = df.loc[mask].groupby("muestra_timestamp").size()
    out[destino] = out["timestamp"].map(counts).fillna(0).astype(int)


def agregar_eventos(df_eventos, timestamps):
    """Agrega events.log por muestra temporal."""
    if df_eventos is None or df_eventos.empty:
        return None

    df = df_eventos.dropna(subset=["timestamp"])
    df = _asignar_a_muestras(df, timestamps)
    if df.empty:
        return None

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps).drop_duplicates().sort_values()
    }).reset_index(drop=True)

    # Conteos básicos
    for evento, destino in [
        ("login",         "events_login_count"),
        ("logout",        "events_logout_count"),
        ("lock_acquired", "events_lock_acquired_count"),
        ("lock_released", "events_lock_released_count"),
        ("wait_info",     "events_wait_count"),
    ]:
        _contar_evento(df, out, evento, destino)

    # Batches
    batch = df[df["event_name"] == "sql_batch_completed"].copy()
    if batch.empty:
        out["batch_count"] = 0
        out["batch_duration_avg_ms"] = 0.0
        out["batch_duration_max_ms"] = 0.0
        return out

    for col in ("duration", "cpu_time", "logical_reads", "writes"):
        batch[col] = pd.to_numeric(batch.get(col, 0), errors="coerce").fillna(0)

    # Solo batches de SteelNort
    if "database_name" in batch.columns:
        batch = batch[batch["database_name"].astype(str).str.lower() == "steelnort"]
    if batch.empty:
        out["batch_count"] = 0
        out["batch_duration_avg_ms"] = 0.0
        out["batch_duration_max_ms"] = 0.0
        return out

    factor = 1e-3 if config.DURACION_EVENTOS_EN_MICROSEGUNDOS else 1.0
    batch["duration_ms"] = batch["duration"] * factor
    g = batch.groupby("muestra_timestamp")

    out["batch_count"] = out["timestamp"].map(g.size()).fillna(0).astype(int)
    out["batch_duration_avg_ms"] = out["timestamp"].map(g["duration_ms"].mean()).fillna(0.0)
    out["batch_duration_max_ms"] = out["timestamp"].map(g["duration_ms"].max()).fillna(0.0)

    # Waits por prefijo
    _contar_wait(df, out, ["LCK_"], "wait_lck_count")
    _contar_wait(df, out, ["PAGEIOLATCH_", "PAGELATCH_"], "wait_io_count")
    _contar_wait(df, out, ["WRITELOG"], "wait_log_count")

    return out


# ==========================================
# SQL Server logs agregados
# ==========================================
def agregar_sqlserver(df_sql, timestamps):
    """Cuenta errores/fatales de sqlserver_logs.log por muestra."""
    if df_sql is None or df_sql.empty or "mensaje" not in df_sql.columns:
        return None

    df = df_sql.dropna(subset=["timestamp"]).copy()
    df["mensaje_up"] = df["mensaje"].astype(str).str.upper()

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps).drop_duplicates().sort_values()
    }).reset_index(drop=True)

    # Asignar cada log a la siguiente muestra
    df = _asignar_a_muestras(df, out["timestamp"])
    if df.empty:
        out["log_error_count"] = 0
        out["log_fatal_count"] = 0
        return out

    g = df.groupby("muestra_timestamp")
    out["log_error_count"] = out["timestamp"].map(
        g["mensaje_up"].apply(lambda s: s.str.contains("ERROR").sum())
    ).fillna(0).astype(int)
    out["log_fatal_count"] = out["timestamp"].map(
        g["mensaje_up"].apply(lambda s: s.str.contains("FATAL").sum())
    ).fillna(0).astype(int)

    return out


# ==========================================
# Transformación por corrida
# ==========================================
def transformar_corrida(corrida, ruta_corrida):
    """Limpia + transforma una corrida. Devuelve DataFrame listo."""
    log(f"-- {corrida}")

    limpios = limpieza.limpiar_corrida(corrida, ruta_corrida)

    wide = pivot_metricas(limpios["metricas"])
    if wide.empty:
        log(f"   {corrida}: sin métricas, se omite")
        return None

    wide = aplicar_tasas(wide)

    # Eventos
    ev = agregar_eventos(limpios["eventos"], wide["timestamp"])
    if ev is not None and not ev.empty:
        wide = wide.merge(ev, on="timestamp", how="left")
        for c in ev.columns:
            if c != "timestamp" and c in wide.columns:
                wide[c] = pd.to_numeric(wide[c], errors="coerce").fillna(0)

    # SQL Server
    sq = agregar_sqlserver(limpios["sqlserver"], wide["timestamp"])
    if sq is not None and not sq.empty:
        wide = wide.merge(sq, on="timestamp", how="left")
        for c in sq.columns:
            if c != "timestamp" and c in wide.columns:
                wide[c] = pd.to_numeric(wide[c], errors="coerce").fillna(0)

    # Imputar continuas con mediana de la corrida
    if config.IMPUTAR_MEDIANA_CORRIDA:
        for c in config.METRICAS_CONTINUAS:
            if c in wide.columns:
                wide[c] = pd.to_numeric(wide[c], errors="coerce").fillna(wide[c].median())

    wide["run_name"] = corrida
    return wide.sort_values("timestamp").reset_index(drop=True)


# ==========================================
# Integración
# ==========================================
def integrar(frames, corridas_info):
    """Concatena corridas y aplica reglas globales."""
    df = pd.concat(frames, ignore_index=True, sort=False)

    # Agregados de eventos/batch: sin log = sin evento -> 0
    for c in df.columns:
        if c.startswith(("events_", "batch_")):
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # Añadir contexto por corrida (carpeta y etiqueta)
    for corrida, info in corridas_info.items():
        mask = df["run_name"] == corrida
        if not mask.any():
            continue
        origen = utils.leer_origen(info["ruta"], grupo=info["grupo"])
        df.loc[mask, "carpeta"] = info["grupo"]
        df.loc[mask, "etiqueta_manual"] = origen.get("es_carga_normal")

    # Orden: baseline primero
    df["_orden"] = (df["carpeta"] != "baseline").astype(int)
    df = (df.sort_values(["_orden", "run_name", "timestamp"])
            .drop(columns="_orden").reset_index(drop=True))

    # Warm-up
    if config.N_MUESTRAS_WARMUP > 0:
        antes = len(df)
        df = df[df.groupby("run_name").cumcount() >= config.N_MUESTRAS_WARMUP]
        df = df.reset_index(drop=True)
        log(f"Warm-up: -{antes - len(df)} muestras")

    # Descartar columnas casi vacías
    umbral = config.CALIDAD_MAX_NULOS_COLUMNA
    proteger = {"timestamp", "run_name", "carpeta", "etiqueta_manual"}
    nulos = df.isna().mean()
    descartar = [c for c in df.columns
                 if c not in proteger and nulos[c] > umbral]
    if descartar:
        df = df.drop(columns=descartar)
        log(f"Columnas descartadas (>{umbral:.0%} nulos): {descartar}")

    # experiment_id por corrida
    runs = df["run_name"].drop_duplicates().tolist()
    df["experiment_id"] = df["run_name"].map({r: f"exp_{i+1:02d}" for i, r in enumerate(runs)})

    # Contexto al inicio
    contexto = ["timestamp", "run_name", "experiment_id", "carpeta", "etiqueta_manual"]
    df = df[contexto + [c for c in df.columns if c not in contexto]]

    return df


# ==========================================
# Reporte de calidad
# ==========================================
def reporte_calidad(df, features):
    """Estadísticas por feature."""
    filas = []
    n = len(df)
    for col in features:
        if col not in df.columns:
            continue
        s = df[col].dropna()
        filas.append({
            "columna": col,
            "nulos": int(df[col].isna().sum()),
            "pct_nulos": round(df[col].isna().sum() / n * 100, 2),
            "unicos": int(df[col].nunique(dropna=True)),
            "media": round(float(s.mean()), 4) if len(s) else np.nan,
            "desv_std": round(float(s.std()), 4) if len(s) else np.nan,
            "min": round(float(s.min()), 4) if len(s) else np.nan,
            "max": round(float(s.max()), 4) if len(s) else np.nan,
        })
    return pd.DataFrame(filas)


# ==========================================
# Main
# ==========================================
def main():
    if not os.path.isdir(config.OUTPUT_BASE_DIR):
        log(f"No existe: {config.OUTPUT_BASE_DIR}")
        return

    corridas_info = utils.descubrir_corridas()
    corridas = sorted(corridas_info,
                      key=lambda c: (corridas_info[c]["grupo"] != "baseline", c))

    log(f"Corridas a procesar ({len(corridas)}): {corridas}")
    if not corridas:
        log("No hay corridas.")
        return

    frames = []
    for corrida in corridas:
        try:
            df = transformar_corrida(corrida, corridas_info[corrida]["ruta"])
            if df is not None and not df.empty:
                frames.append(df)
        except Exception as e:
            log(f"   ERROR en {corrida}: {e}")

    if not frames:
        log("Nada que integrar.")
        return

    df = integrar(frames, corridas_info)
    log(f"Dataset: {len(df)} filas × {df.shape[1]} columnas")

    # Salida
    os.makedirs(config.DIR_PREPARADO, exist_ok=True)

    # Parquet
    ruta_parquet = os.path.join(config.DIR_PREPARADO, config.ARCHIVO_DATASET)
    df.to_parquet(ruta_parquet, index=False)
    log(f"Dataset: {ruta_parquet}")

    # Reporte de calidad
    rep = reporte_calidad(df, config.FEATURES_MODELO)
    ruta_rep = os.path.join(config.DIR_PREPARADO, config.ARCHIVO_CALIDAD)
    rep.to_csv(ruta_rep, index=False, encoding="utf-8-sig")
    log(f"Calidad: {ruta_rep}")

    # Metadata
    metadata = {
        "fase": "Data Preparation",
        "fuentes": config.ARCHIVOS_ENTRADA,
        "features_modelo": config.FEATURES_MODELO,
        "total_corridas": int(df["run_name"].nunique()),
        "total_filas": int(len(df)),
        "nota_etiquetado": (
            "'carpeta' indica origen organizativo (baseline/anomalias). "
            "'etiqueta_manual' es la verdad del origen.json "
            "(True/False/None). Ninguna entra al modelo; "
            "'etiqueta_manual' es solo para evaluación post-hoc."
        ),
    }
    ruta_meta = os.path.join(config.DIR_PREPARADO, config.ARCHIVO_METADATA)
    with open(ruta_meta, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    log(f"Metadata: {ruta_meta}")

    # Resumen
    print("\n=== RESUMEN ===")
    print(f"Filas: {len(df)} | Columnas: {df.shape[1]}")
    print(f"Corridas: {df['run_name'].nunique()}")
    print("\nFilas por corrida:")
    print(df.groupby("run_name", sort=False).size().to_string())
    print("\nEtiquetas:")
    print(df.drop_duplicates("run_name")
            .groupby(["carpeta", "etiqueta_manual"], dropna=False)
            .size().to_string())


if __name__ == "__main__":
    main()