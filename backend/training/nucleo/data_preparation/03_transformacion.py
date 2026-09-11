"""
03_transformacion.py
====================

Paso 3 del Pipeline (Transformación de Datos).

Transforma y consolida, de forma independiente por corrida/carga, las
fuentes ya limpiadas:

    - metrics.log
    - events.log
    - sqlserver_logs.log

Procesos principales:
    1. Pivot de métricas: formato largo -> formato ancho.
    2. Cálculo de tasas para contadores acumulativos.
    3. Agregación temporal de eventos de events.log.
    4. Agregación temporal de errores/advertencias de SQL Server.
    5. Cálculo de variables derivadas.
    6. Generación de una tabla transformada por cada corrida.

IMPORTANTE:
    - No existen events_xe ni workload_stats.
    - Cada corrida is independiente.
    - No se comparan ni mezclan corridas en este paso.
    - No se etiqueta ninguna corrida como "normal".
"""

import json
import os

import numpy as np
import pandas as pd

import config


# ============================================================
# LOG
# ============================================================

def log(msg):
    print(f"[TRANSFORMACION] {msg}", flush=True)


# ============================================================
# CONFIGURACIÓN DE CONTADORES
# ============================================================

# Estas variables representan contadores/tasas que el collector
# ya debería entregar correctamente calculados por segundo.
#
# No se les aplica diff/dt nuevamente aquí.
CONTADORES_SIN_DELTA = [
    "page_reads_per_sec",
    "page_writes_per_sec",
    "rollbacks_per_sec",
    "batch_requests_per_sec",
    "sql_compilations_per_sec",
]


# Contadores acumulativos que sí necesitan convertirse a tasa.
#
# total_reads y total_writes proceden de métricas acumulativas,
# por lo que se calcula:
#
#       tasa = delta_valor / delta_tiempo
#
CONTADORES_A_TASA = [
    "total_reads",
    "total_writes",
]


# ============================================================
# PIVOTE DE MÉTRICAS
# ============================================================

def pivot_metricas(corrida, dir_salida):
    """
    Convierte las métricas del formato largo al formato ancho.

    Entrada:

        timestamp | metrica | valor

    Salida:

        timestamp | cpu_usr | cpu_sys | memory_percent | ...

    Cada timestamp representa una muestra de la corrida.
    """

    ruta = os.path.join(
        dir_salida,
        config.NOMBRE_METRICAS_LIMPIO
    )

    if not os.path.exists(ruta):
        raise FileNotFoundError(
            f"No existe el archivo de métricas: {ruta}"
        )

    df_m = pd.read_csv(
        ruta,
        encoding="utf-8-sig"
    )

    if df_m.empty:
        raise ValueError(
            f"El archivo de métricas está vacío: {ruta}"
        )

    columnas_requeridas = {
        "timestamp",
        "metrica",
        "valor",
    }

    faltantes = columnas_requeridas - set(df_m.columns)

    if faltantes:
        raise ValueError(
            f"Faltan columnas en {ruta}: {sorted(faltantes)}"
        )

    df_m = df_m.copy()

    df_m["timestamp"] = pd.to_datetime(
        df_m["timestamp"],
        errors="coerce"
    )

    df_m["valor"] = pd.to_numeric(
        df_m["valor"],
        errors="coerce"
    )

    df_m = df_m.dropna(
        subset=["timestamp", "metrica"]
    )

    wide = df_m.pivot_table(
        index="timestamp",
        columns="metrica",
        values="valor",
        aggfunc="first"
    )

    wide = wide.reset_index()

    wide.columns.name = None

    wide = wide.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    return wide


# ============================================================
# CÁLCULO DE TASAS
# ============================================================

def aplicar_tasas(wide):
    """
    Calcula tasas delta/dt para contadores acumulativos.

    Se aplica únicamente a:

        - total_reads
        - total_writes

    Las variables que ya vienen como /sec NO se vuelven a
    diferenciar.
    """

    wide = wide.copy()

    wide = wide.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    dt = (
        wide["timestamp"]
        .diff()
        .dt.total_seconds()
    )

    for col in CONTADORES_A_TASA:

        if col not in wide.columns:
            continue

        valores = pd.to_numeric(
            wide[col],
            errors="coerce"
        )

        delta = valores.diff()

        # Evita división por cero y tiempos inválidos.
        tasa = delta.div(
            dt.replace(0, np.nan)
        )

        # Las tasas negativas pueden aparecer si el contador
        # acumulativo se reinicia. En ese caso se considera
        # inválida la primera observación posterior al reinicio.
        tasa = tasa.where(
            tasa >= 0,
            np.nan
        )

        wide[col] = tasa

    return wide


# ============================================================
# ASIGNACIÓN TEMPORAL DE EVENTOS
# ============================================================

def _asignar_a_muestras(df, timestamps):
    """
    Asigna cada evento a la siguiente muestra temporal disponible.

    Ejemplo:

        evento:   10:01:02
        muestra:  10:01:05

    El evento se asigna a la muestra 10:01:05.

    Esto permite convertir eventos discretos en variables
    agregadas por muestra.
    """

    muestras = pd.DataFrame({
        "muestra_timestamp": pd.to_datetime(timestamps)
    })

    muestras = (
        muestras
        .drop_duplicates()
        .sort_values("muestra_timestamp")
    )

    df = (
        df
        .dropna(subset=["timestamp"])
        .sort_values("timestamp")
    )

    if df.empty or muestras.empty:
        return df.iloc[0:0].copy()

    asignado = pd.merge_asof(
        df,
        muestras,
        left_on="timestamp",
        right_on="muestra_timestamp",
        direction="forward",
    )

    return asignado.dropna(
        subset=["muestra_timestamp"]
    )


# ============================================================
# EVENTOS DE EVENTS.LOG
# ============================================================

def agregar_eventos_dmv(corrida, dir_salida, timestamps):
    """
    Agrega events.log dentro de las ventanas temporales
    correspondientes a las muestras de metrics.log.

    No utiliza events_xe.
    """

    ruta = os.path.join(
        dir_salida,
        config.NOMBRE_EVENTS_LIMPIO
    )

    if not os.path.exists(ruta):
        log(f"   Sin events.log limpio para {corrida}")
        return None

    df_e = pd.read_csv(
        ruta,
        encoding="utf-8-sig"
    )

    if df_e.empty:
        return None

    if "timestamp" not in df_e.columns:
        return None

    if "event_name" not in df_e.columns:
        return None

    df_e = df_e.copy()

    df_e["timestamp"] = pd.to_datetime(
        df_e["timestamp"],
        errors="coerce"
    )

    df_e = df_e.dropna(
        subset=["timestamp"]
    )

    df_e = _asignar_a_muestras(
        df_e,
        timestamps
    )

    if df_e.empty:
        return None

    out = pd.DataFrame({
        "timestamp": (
            pd.to_datetime(timestamps)
            .drop_duplicates()
            .sort_values()
        )
    })

    # --------------------------------------------------------
    # EVENTOS DE USUARIO
    # --------------------------------------------------------

    if "process_type" in df_e.columns:

        user_events = df_e[
            df_e["process_type"] == "USER"
        ].copy()

    else:

        user_events = df_e.iloc[0:0].copy()

    # --------------------------------------------------------
    # LOGIN / LOGOUT / WAIT
    # --------------------------------------------------------

    eventos_basicos = {
        "login": "events_login_count",
        "logout": "events_logout_count",
        "wait_info": "events_wait_count",
    }

    for origen, destino in eventos_basicos.items():

        counts = (
            user_events[
                user_events["event_name"] == origen
            ]
            .groupby("muestra_timestamp")
            .size()
        )

        out[destino] = (
            out["timestamp"]
            .map(counts)
            .fillna(0)
            .astype(int)
        )

    # --------------------------------------------------------
    # LOCKS
    # --------------------------------------------------------

    lock_mask = df_e["event_name"].isin([
        "lock_acquired",
        "lock_released",
    ])

    lock_counts = (
        df_e.loc[lock_mask]
        .groupby("muestra_timestamp")
        .size()
    )

    out["events_lock_count"] = (
        out["timestamp"]
        .map(lock_counts)
        .fillna(0)
        .astype(int)
    )

    # --------------------------------------------------------
    # SQL BATCH COMPLETED
    # --------------------------------------------------------

    batch = user_events[
        user_events["event_name"] == "sql_batch_completed"
    ].copy()

    out["events_batch_count"] = (
        out["timestamp"]
        .map(
            batch.groupby("muestra_timestamp").size()
        )
        .fillna(0)
        .astype(int)
    )

    # --------------------------------------------------------
    # VARIABLES NUMÉRICAS DEL BATCH
    # --------------------------------------------------------

    for column in (
        "duration",
        "cpu_time",
        "logical_reads",
        "writes",
    ):

        if column in batch.columns:

            batch[column] = pd.to_numeric(
                batch[column],
                errors="coerce"
            ).fillna(0)

        else:

            batch[column] = 0

    grouped = batch.groupby(
        "muestra_timestamp"
    )

    # --------------------------------------------------------
    # CONSULTAS LARGAS
    # --------------------------------------------------------

    long_queries = (
        batch[
            batch["duration"] > 15000
        ]
        .groupby("muestra_timestamp")
        .size()
    )

    long_transactions = (
        batch[
            batch["duration"] > 30000
        ]
        .groupby("muestra_timestamp")
        .size()
    )

    out["long_queries"] = (
        out["timestamp"]
        .map(long_queries)
        .fillna(0)
        .astype(int)
    )

    out["long_transactions"] = (
        out["timestamp"]
        .map(long_transactions)
        .fillna(0)
        .astype(int)
    )

    # --------------------------------------------------------
    # ESTADÍSTICAS DE CONSULTAS
    # --------------------------------------------------------

    agregaciones = [
        (
            "duration",
            "query_duration_max_ms",
            "max"
        ),
        (
            "duration",
            "query_duration_avg_ms",
            "mean"
        ),
        (
            "cpu_time",
            "cpu_time_sum_ms",
            "sum"
        ),
        (
            "logical_reads",
            "logical_reads_sum",
            "sum"
        ),
        (
            "writes",
            "writes_sum",
            "sum"
        ),
    ]

    for source, target, method in agregaciones:

        values = getattr(
            grouped[source],
            method
        )()

        out[target] = (
            out["timestamp"]
            .map(values)
            .fillna(0)
        )

    # --------------------------------------------------------
    # WAIT TYPES
    # --------------------------------------------------------

    if "wait_type" in df_e.columns:

        wait_type = (
            df_e["wait_type"]
            .fillna("")
            .astype(str)
            .str.upper()
        )

    else:

        wait_type = pd.Series(
            "",
            index=df_e.index,
            dtype="object"
        )

    # Locks
    wait_lck = (
        wait_type.str.startswith("LCK_")
    )

    out["wait_lck_count"] = (
        out["timestamp"]
        .map(
            df_e.loc[wait_lck]
            .groupby("muestra_timestamp")
            .size()
        )
        .fillna(0)
        .astype(int)
    )

    # I/O
    wait_io = wait_type.str.startswith(
        (
            "PAGEIOLATCH_",
            "PAGELATCH_",
        )
    )

    out["wait_io_count"] = (
        out["timestamp"]
        .map(
            df_e.loc[wait_io]
            .groupby("muestra_timestamp")
            .size()
        )
        .fillna(0)
        .astype(int)
    )

    # Transaction log
    wait_log = wait_type == "WRITELOG"

    out["wait_log_count"] = (
        out["timestamp"]
        .map(
            df_e.loc[wait_log]
            .groupby("muestra_timestamp")
            .size()
        )
        .fillna(0)
        .astype(int)
    )

    # --------------------------------------------------------
    # SESIONES DISTINTAS
    # --------------------------------------------------------

    if "session_id" in user_events.columns:

        session_ids = pd.to_numeric(
            user_events["session_id"],
            errors="coerce"
        )

        distinct_sessions = (
            user_events.assign(
                _session_id=session_ids
            )
            .dropna(subset=["_session_id"])
            .groupby("muestra_timestamp")[
                "_session_id"
            ]
            .nunique()
        )

    else:

        distinct_sessions = pd.Series(
            dtype="int64"
        )

    out["distinct_sessions_count"] = (
        out["timestamp"]
        .map(distinct_sessions)
        .fillna(0)
        .astype(int)
    )

    # --------------------------------------------------------
    # QUERY COUNT
    # --------------------------------------------------------

    out["query_count"] = (
        out["events_batch_count"]
    )

    # --------------------------------------------------------
    # WAIT COUNT
    # --------------------------------------------------------

    wait_events = user_events[
        user_events["event_name"] == "wait_info"
    ]

    out["wait_count"] = (
        out["timestamp"]
        .map(
            wait_events
            .groupby("muestra_timestamp")
            .size()
        )
        .fillna(0)
        .astype(int)
    )

    # --------------------------------------------------------
    # LOCK EVENT COUNT
    # --------------------------------------------------------

    out["lock_event_count"] = (
        out["timestamp"]
        .map(
            df_e.loc[lock_mask]
            .groupby("muestra_timestamp")
            .size()
        )
        .fillna(0)
        .astype(int)
    )

    # --------------------------------------------------------
    # ERRORES DE EVENTS.LOG
    # --------------------------------------------------------

    error_events = df_e[
        df_e["event_name"].isin([
            "error_reported",
            "xml_deadlock_report",
        ])
    ]

    out["error_count"] = (
        out["timestamp"]
        .map(
            error_events
            .groupby("muestra_timestamp")
            .size()
        )
        .fillna(0)
        .astype(int)
    )

    # --------------------------------------------------------
    # ALIAS HISTÓRICOS
    # --------------------------------------------------------
    #
    # Se conservan porque otras etapas pueden estar esperando
    # estas columnas.

    out["duration_max_ms"] = (
        out["query_duration_max_ms"]
    )

    out["duration_avg_ms"] = (
        out["query_duration_avg_ms"]
    )

    return out


# ============================================================
# SQL SERVER ERROR LOG
# ============================================================

def agregar_logs_sqlserver(dir_salida, timestamps):
    """
    Agrega errores, advertencias y eventos fatales encontrados
    en sqlserver_logs.log.
    """

    ruta = os.path.join(
        dir_salida,
        config.NOMBRE_SQLSERVER_LOGS_LIMPIO
    )

    if not os.path.exists(ruta):
        return None

    df_l = pd.read_csv(
        ruta,
        encoding="utf-8-sig"
    )

    if df_l.empty:
        return None

    if "timestamp" not in df_l.columns:
        return None

    df_l = df_l.copy()

    df_l["timestamp"] = pd.to_datetime(
        df_l["timestamp"],
        errors="coerce"
    )

    df_l = df_l.dropna(
        subset=["timestamp"]
    )

    df_l = _asignar_a_muestras(
        df_l,
        timestamps
    )

    if df_l.empty:
        return None

    out = pd.DataFrame({
        "timestamp": (
            pd.to_datetime(timestamps)
            .drop_duplicates()
            .sort_values()
        )
    })

    mensaje = (
        df_l.get(
            "mensaje",
            pd.Series(
                index=df_l.index,
                dtype="object"
            )
        )
        .fillna("")
        .astype(str)
        .str.lower()
    )

    severidad = mensaje.str.extract(
        r"severity\s*(?:level)?\s*[:=]?\s*(\d+)",
        expand=False
    )

    severidad = pd.to_numeric(
        severidad,
        errors="coerce"
    )

    grupos = {

        "log_error_count":
            mensaje.str.contains(
                "error",
                regex=False
            ),

        "log_warning_count":
            mensaje.str.contains(
                "warning|advertencia",
                regex=True
            ),

        "log_fatal_count":
            (
                mensaje.str.contains(
                    "fatal",
                    regex=False
                )
                |
                severidad.between(
                    20,
                    25
                )
            ),
    }

    for nombre, mask in grupos.items():

        counts = (
            df_l.loc[mask]
            .groupby("muestra_timestamp")
            .size()
        )

        out[nombre] = (
            out["timestamp"]
            .map(counts)
            .fillna(0)
            .astype(int)
        )

    return out


# ============================================================
# TRANSFORMACIÓN DE UNA CORRIDA
# ============================================================

def transformar_corrida(corrida):
    """
    Transforma una corrida completa de manera independiente.

    Ejemplo:

        output/
        └── carga_001/

    produce:

        output/limpio/carga_001/datos_transformados.csv

    No se mezclan datos con carga_002, carga_003, etc.
    """

    dir_salida = os.path.join(
        config.DIR_LIMPIO,
        corrida
    )

    if not os.path.isdir(dir_salida):
        raise FileNotFoundError(
            f"No existe la carpeta de la corrida: {dir_salida}"
        )

    log(f"   Transformando corrida: {corrida}")

    # --------------------------------------------------------
    # 1. MÉTRICAS
    # --------------------------------------------------------

    wide = pivot_metricas(
        corrida,
        dir_salida
    )

    # --------------------------------------------------------
    # 2. TASAS
    # --------------------------------------------------------

    wide = aplicar_tasas(
        wide
    )

    # --------------------------------------------------------
    # 3. VARIABLES DERIVADAS
    # --------------------------------------------------------

    cpu_usr = pd.to_numeric(
        wide.get(
            "cpu_usr",
            pd.Series(0, index=wide.index)
        ),
        errors="coerce"
    ).fillna(0)

    cpu_sys = pd.to_numeric(
        wide.get(
            "cpu_sys",
            pd.Series(0, index=wide.index)
        ),
        errors="coerce"
    ).fillna(0)

    wide["cpu_total"] = (
        cpu_usr + cpu_sys
    )

    # --------------------------------------------------------
    # 4. EVENTOS
    # --------------------------------------------------------

    n_muestras = len(wide)

    log(
        f"   Muestras métricas={n_muestras}"
    )

    ev_dmv = agregar_eventos_dmv(
        corrida,
        dir_salida,
        wide["timestamp"]
    )

    if ev_dmv is not None and not ev_dmv.empty:

        wide = wide.merge(
            ev_dmv,
            on="timestamp",
            how="left"
        )

        # Evitar NaN después del merge.
        columnas_eventos = [
            c for c in ev_dmv.columns
            if c != "timestamp"
        ]

        for column in columnas_eventos:

            if column in wide.columns:

                if pd.api.types.is_numeric_dtype(
                    wide[column]
                ):

                    wide[column] = (
                        wide[column]
                        .fillna(0)
                    )

    # --------------------------------------------------------
    # 5. SQL SERVER LOG
    # --------------------------------------------------------

    ev_logs = agregar_logs_sqlserver(
        dir_salida,
        wide["timestamp"]
    )

    if ev_logs is not None and not ev_logs.empty:

        wide = wide.merge(
            ev_logs,
            on="timestamp",
            how="left"
        )

        columnas_logs = [
            c for c in ev_logs.columns
            if c != "timestamp"
        ]

        for column in columnas_logs:

            if column in wide.columns:

                wide[column] = (
                    pd.to_numeric(
                        wide[column],
                        errors="coerce"
                    )
                    .fillna(0)
                )

    # --------------------------------------------------------
    # 6. REQUESTS POR SESIÓN
    # --------------------------------------------------------

    active_sessions = pd.to_numeric(
        wide.get(
            "active_sessions",
            pd.Series(
                np.nan,
                index=wide.index
            )
        ),
        errors="coerce"
    )

    active_requests = pd.to_numeric(
        wide.get(
            "active_requests",
            pd.Series(
                np.nan,
                index=wide.index
            )
        ),
        errors="coerce"
    )

    wide["requests_per_session"] = (
        active_requests
        .div(
            active_sessions.replace(
                0,
                np.nan
            )
        )
        .fillna(0)
    )

    # --------------------------------------------------------
    # 7. COLUMNAS DE EVENTOS
    # --------------------------------------------------------

    prefijos_eventos = (
        "events_",
        "duration_",
        "query_duration_",
        "cpu_time_",
        "logical_reads_",
        "writes_",
        "wait_",
        "distinct_sessions_",
        "log_",
    )

    cols_eventos = [
        c
        for c in wide.columns
        if c.startswith(prefijos_eventos)
    ]

    log(
        f"   Columnas de eventos/logs={len(cols_eventos)}"
    )

    # --------------------------------------------------------
    # 8. ORDEN FINAL
    # --------------------------------------------------------

    wide = wide.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    # --------------------------------------------------------
    # 9. GUARDAR TRANSFORMADO
    # --------------------------------------------------------

    ruta_transformado = os.path.join(
        dir_salida,
        config.NOMBRE_TRANSFORMADO
    )

    wide.to_csv(
        ruta_transformado,
        index=False,
        encoding="utf-8-sig"
    )

    # --------------------------------------------------------
    # 10. RESUMEN
    # --------------------------------------------------------

    resumen = {
        "corrida": corrida,
        "muestras": int(n_muestras),
        "columnas": int(wide.shape[1]),
        "columnas_eventos": int(len(cols_eventos)),
    }

    ruta_resumen = os.path.join(
        dir_salida,
        "resumen_transformacion.json"
    )

    with open(
        ruta_resumen,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            resumen,
            f,
            ensure_ascii=False,
            indent=2
        )

    return resumen


# ============================================================
# MAIN
# ============================================================

def main():

    if not os.path.isdir(
        config.DIR_LIMPIO
    ):

        log(
            f"No existe DIR_LIMPIO: "
            f"{config.DIR_LIMPIO}"
        )

        return

    corridas = sorted([
        d
        for d in os.listdir(
            config.DIR_LIMPIO
        )
        if os.path.isdir(
            os.path.join(
                config.DIR_LIMPIO,
                d
            )
        )
        and os.path.exists(
            os.path.join(
                config.DIR_LIMPIO,
                d,
                config.NOMBRE_METRICAS_LIMPIO
            )
        )
    ])

    log(
        f"Corridas a transformar "
        f"({len(corridas)}): {corridas}"
    )

    resumenes = []

    for corrida in corridas:

        log(
            f"-- Transformando: {corrida}"
        )

        try:

            resumen = transformar_corrida(
                corrida
            )

            resumenes.append(
                resumen
            )

        except Exception as e:

            log(
                f"   ERROR en {corrida}: {e}"
            )

    # --------------------------------------------------------
    # RESUMEN FINAL
    # --------------------------------------------------------

    print(
        "\n=== RESUMEN TRANSFORMACION ==="
    )

    for r in resumenes:

        print(
            f"  {r['corrida']:<12} "
            f"muestras={r['muestras']:<5} "
            f"cols={r['columnas']:<4} "
            f"cols_eventos={r['columnas_eventos']}"
        )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()