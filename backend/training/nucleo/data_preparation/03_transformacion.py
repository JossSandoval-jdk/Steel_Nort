"""
03_transformacion.py
====================

Paso 4: transforma cada corrida por separado.

- Pivot de métricas
- Tasas para total_reads / total_writes
- Agregación temporal de events.log
- Convierte duration de μs a ms

Salida por corrida:
    output/limpio_v2/<corrida>/datos_transformados.csv
"""

import os

import numpy as np
import pandas as pd

import config
import utils


def log(msg):
    print(f"[TRANSFORMACION] {msg}", flush=True)


# ==========================================
# PIVOT DE MÉTRICAS
# ==========================================

def pivot_metricas(dir_corrida):
    """Pivotea métricas de formato largo a ancho."""
    ruta = os.path.join(dir_corrida, config.NOMBRE_METRICAS_LIMPIO)
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"No existe: {ruta}")

    df = pd.read_csv(ruta, encoding="utf-8-sig")
    if df.empty:
        raise ValueError(f"Archivo vacío: {ruta}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna(subset=["timestamp", "metrica"])

    wide = df.pivot_table(
        index="timestamp", columns="metrica",
        values="valor", aggfunc="first",
    ).reset_index()
    wide.columns.name = None

    return wide.sort_values("timestamp").reset_index(drop=True)


# ==========================================
# TASAS PARA CONTADORES ACUMULATIVOS
# ==========================================

def aplicar_tasas(wide):
    """Convierte total_reads y total_writes (acumulativos) en tasas Δt."""
    wide = wide.sort_values("timestamp").reset_index(drop=True)
    dt = wide["timestamp"].diff().dt.total_seconds()

    for col in config.METRICAS_A_TASA:
        if col not in wide.columns:
            continue
        valores = pd.to_numeric(wide[col], errors="coerce")
        delta = valores.diff()
        tasa = delta.div(dt.replace(0, np.nan))
        # Deltas negativos = reset de contador → NaN
        # Primer registro de la corrida → sin Δt → NaN.
        # Se completa con el valor siguiente (bfill) para no filtrar NaN al modelo.
        wide[col] = tasa.where(tasa >= 0, np.nan).bfill()

    return wide


# ==========================================
# ASIGNACIÓN DE EVENTOS A MUESTRAS
# ==========================================

def _asignar_a_muestras(df, timestamps):
    """Asigna cada evento a la siguiente muestra temporal."""
    muestras = (
        pd.DataFrame({"muestra_timestamp": pd.to_datetime(timestamps)})
        .drop_duplicates().sort_values("muestra_timestamp")
    )

    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    if df.empty or muestras.empty:
        return df.iloc[0:0].copy()

    asignado = pd.merge_asof(
        df, muestras,
        left_on="timestamp", right_on="muestra_timestamp",
        direction="forward",
    )
    return asignado.dropna(subset=["muestra_timestamp"])


# ==========================================
# AGREGACIÓN DE EVENTOS
# ==========================================

def _contar_evento(df, out, evento, destino):
    subset = df[df["event_name"] == evento]
    counts = subset.groupby("muestra_timestamp").size()
    out[destino] = out["timestamp"].map(counts).fillna(0).astype(int)


def _contar_wait(df, out, prefijos, destino):
    if "wait_type" not in df.columns:
        out[destino] = 0
        return
    wait_type = df["wait_type"].fillna("").astype(str).str.upper()
    mask = wait_type.str.startswith(tuple(prefijos))
    counts = df.loc[mask].groupby("muestra_timestamp").size()
    out[destino] = out["timestamp"].map(counts).fillna(0).astype(int)


def agregar_eventos(dir_corrida, timestamps):
    """Agrega events.log por muestra temporal."""
    ruta = os.path.join(dir_corrida, config.NOMBRE_EVENTS_LIMPIO)
    if not os.path.exists(ruta):
        log("   Sin events.log limpio")
        return None

    df_e = pd.read_csv(ruta, encoding="utf-8-sig")
    if df_e.empty or "timestamp" not in df_e.columns:
        return None

    df_e["timestamp"] = pd.to_datetime(df_e["timestamp"], errors="coerce")
    df_e = df_e.dropna(subset=["timestamp"])
    df_e = _asignar_a_muestras(df_e, timestamps)

    if df_e.empty:
        return None

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps).drop_duplicates().sort_values()
    }).reset_index(drop=True)

    # Conteos básicos
    for evento, destino in [
        ("login",            "events_login_count"),
        ("logout",           "events_logout_count"),
        ("lock_acquired",    "events_lock_acquired_count"),
        ("lock_released",    "events_lock_released_count"),
        ("wait_info",        "events_wait_count"),
    ]:
        _contar_evento(df_e, out, evento, destino)

    # Batches
    batch = df_e[df_e["event_name"] == "sql_batch_completed"].copy()

    if batch.empty:
        out["batch_count"] = 0
        out["batch_duration_avg_ms"] = 0.0
        out["batch_duration_max_ms"] = 0.0
        return out

    for col in ("duration", "cpu_time", "logical_reads", "writes"):
        if col in batch.columns:
            batch[col] = pd.to_numeric(batch[col], errors="coerce").fillna(0)
        else:
            batch[col] = 0

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

    grouped = batch.groupby("muestra_timestamp")

    out["batch_count"] = out["timestamp"].map(grouped.size()).fillna(0).astype(int)
    out["batch_duration_avg_ms"] = (
        out["timestamp"].map(grouped["duration_ms"].mean()).fillna(0.0)
    )
    out["batch_duration_max_ms"] = (
        out["timestamp"].map(grouped["duration_ms"].max()).fillna(0.0)
    )

    # Waits por prefijo
    _contar_wait(df_e, out, ["LCK_"], "wait_lck_count")
    _contar_wait(df_e, out, ["PAGEIOLATCH_", "PAGELATCH_"], "wait_io_count")
    _contar_wait(df_e, out, ["WRITELOG"], "wait_log_count")

    return out


# ==========================================
# TRANSFORMACIÓN POR CORRIDA
# ==========================================

def transformar_corrida(corrida, ruta_corrida):
    """Transforma una corrida y guarda datos_transformados.csv."""
    dir_salida = os.path.join(config.DIR_LIMPIO, corrida)
    os.makedirs(dir_salida, exist_ok=True)

    log(f"   Transformando: {corrida}")

    wide = pivot_metricas(dir_salida)
    wide = aplicar_tasas(wide)
    n_muestras = len(wide)

    ev = agregar_eventos(dir_salida, wide["timestamp"])
    if ev is not None and not ev.empty:
        wide = wide.merge(ev, on="timestamp", how="left")
        for c in ev.columns:
            if c != "timestamp" and c in wide.columns:
                wide[c] = pd.to_numeric(wide[c], errors="coerce").fillna(0)

    wide = wide.sort_values("timestamp").reset_index(drop=True)
    wide["run_name"] = corrida

    # Imputación de métricas continuas incompletas (p. ej. primer registro
    # sin transacciones_per_sec) con la mediana de la propia corrida.
    if config.IMPUTAR_MEDIANA_CORRIDA:
        for c in config.METRICAS_CONTINUAS:
            if c not in wide.columns:
                continue
            mediana = wide[c].median()
            wide[c] = pd.to_numeric(wide[c], errors="coerce").fillna(mediana)

    ruta_out = os.path.join(dir_salida, config.NOMBRE_TRANSFORMADO)
    wide.to_csv(ruta_out, index=False, encoding="utf-8-sig")

    return {
        "corrida": corrida,
        "muestras": int(n_muestras),
        "columnas": int(wide.shape[1]),
    }


def main():
    if not os.path.isdir(config.DIR_LIMPIO):
        log(f"No existe DIR_LIMPIO: {config.DIR_LIMPIO}")
        return

    corridas_info = utils.descubrir_corridas()
    corridas = sorted(
        corridas_info,
        key=lambda c: (corridas_info[c]["grupo"] != "baseline", c),
    )

    log(f"Corridas a transformar ({len(corridas)}): {corridas}")
    if not corridas:
        log("No se encontraron corridas.")
        return

    resumenes = []
    for corrida in corridas:
        try:
            r = transformar_corrida(corrida, corridas_info[corrida]["ruta"])
            r["grupo"] = corridas_info[corrida]["grupo"]
            resumenes.append(r)
        except Exception as e:
            log(f"   ERROR en {corrida}: {e}")

    print("\n=== RESUMEN TRANSFORMACION ===")
    for r in resumenes:
        print(f"  {r['corrida']:<20} muestras={r['muestras']:<5} cols={r['columnas']}")


if __name__ == "__main__":
    main()