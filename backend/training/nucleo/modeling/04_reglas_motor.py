"""
04_reglas_motor.py
==================

Motor de reglas alineado con la metodología oficial de Microsoft Learn
para el diagnóstico de causas de anomalías OLTP en SQL Server.

Evidencia doble — EVENTOS + MÉTRICAS:
    - Eventos  : events.log  -> wait_type, duration, cpu_time, logical_reads...
    - Métricas : metrics.log -> contadores de rendimiento y del SO.
"""

import json
import os
import re

import numpy as np
import pandas as pd

import config


def log(msg):
    print(f"[REGLAS-MOTOR] {msg}", flush=True)


FONDO = {
    "MSQL_XP", "SLEEP_TASK", "BROKER_TO_FLUSH", "BROKER_TASK_STOP",
    "SQLTRACE_INCREMENTAL_FLUSH_SLEEP", "SP_SERVER_DIAGNOSTICS_SLEEP",
    "ONDEMAND_TASK_QUEUE", "CHECKPOINT_QUEUE", "BROKER_EVENTHANDLER",
    "HADR_FILESTREAM_IOMGR_IOCOMPLETION", "HADR_NOTIFICATION_DEQUEUE",
    "BROKER_TRANSMITTER", "PREEMPTIVE_OS_FLUSHFILEBUFFERS",
    "PREEMPTIVE_OS_VERIFYTRUST", "MEMORY_ALLOCATION_EXT", "BROKER_ENDPOINT",
    "WAITFOR", "SLEEP", "XTP_WAIT", "SQLTRACE_BUFFER_FLUSH",
    "REQUEST_FOR_DEADLOCK_SEARCH", "LAZYWRITER_SLEEP", "DIRTY_PAGE_POLL",
    "DBMIRRORING_CMD", "LOG_MGR_QUEUE", "BRKR_BROKER_IDLE", "XE_TIMER_EVENT",
    "WAIT_FOR_RESULTS", "SP_SERVER_DIAGNOSTICS", "DISPATCHER_QUEUE_SEMAPHORE",
    "RESOURCE_MONITOR_ANTIPRIORITY", "QDS_PERSIST_TASK",
}


def es_relevante(wait_type):
    if not wait_type:
        return False
    if wait_type.upper() in FONDO:
        return False
    return True


METRICAS_R1 = ["disk_read_per_sec", "disk_write_per_sec",
               "page_reads_per_sec", "page_writes_per_sec",
               "total_reads_delta", "total_writes_delta"]
METRICAS_R2 = ["lock_waits", "deadlocks_per_sec", "total_locks"]
METRICAS_R3 = ["cpu_usr", "cpu_sys"]  # Uso general del procesador según Microsoft
METRICAS_R5 = ["buffer_cache_hit_ratio", "page_life_expectancy"]
METRICAS_R7 = ["batch_requests_per_sec", "sql_compilations_per_sec"]


def leer_metricas(ruta):
    if not ruta or not os.path.exists(ruta):
        return None
    registros = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            partes = re.split(r"\s{2,}", linea)
            if len(partes) < 3:
                continue
            try:
                valor = float(partes[2].strip())
            except (ValueError, TypeError):
                continue
            registros.append({
                "timestamp": partes[0].strip(),
                "metrica": partes[1].strip(),
                "valor": valor,
            })
    if not registros:
        return None

    df = pd.DataFrame(registros)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])

    ancho = df.pivot_table(
        index="timestamp", columns="metrica", values="valor", aggfunc="first")

    for col in ("total_reads", "total_writes"):
        if col in ancho.columns:
            ancho[col + "_delta"] = ancho[col].diff().fillna(0.0)

    return ancho


def umbrales_por_corrida(df_m):
    if df_m is None:
        return {}
    out = {}
    for col in df_m.columns:
        serie = pd.to_numeric(df_m[col], errors="coerce").dropna()
        if serie.empty:
            continue
        out[col] = (float(serie.quantile(0.90)), float(serie.quantile(0.99)))
    return out


def unir_metricas(eventos, df_m, umbrales):
    if df_m is None or not eventos:
        return eventos

    for ev in eventos:
        for col in df_m.columns:
            ev["m_" + col] = None

    ev = pd.DataFrame(eventos)
    ev["_ts"] = pd.to_datetime(ev["timestamp"], errors="coerce")
    ev["_orden"] = np.arange(len(ev))

    m = df_m.reset_index().rename(columns={"timestamp": "_ts"})
    m = m.sort_values("_ts")

    merged = pd.merge_asof(
        ev.sort_values("_ts"),
        m,
        on="_ts",
        direction="nearest",
    ).sort_values("_orden")

    cols_m = df_m.columns
    eventos_finales = []
    for i, fila in merged.iterrows():
        ev_i = dict(ev.loc[fila["_orden"], :])
        ev_i.pop("_ts", None)
        for k, v in ev_i.items():
            if isinstance(v, float) and pd.isna(v):
                ev_i[k] = None
        for col in cols_m:
            v = fila.get(col)
            ev_i["m_" + col] = None if (isinstance(v, float) and pd.isna(v)) else v
        eventos_finales.append(ev_i)

    return eventos_finales


def v_met(met, nombre):
    v = met.get("m_" + nombre)
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return v


def estado_gauge(valor, umbrales, nombre):
    if valor is None:
        return None
    tupla = umbrales.get(nombre)
    if not tupla or not np.isfinite(tupla[0]):
        return "normal"
    p90, p99 = tupla
    if p99 - p90 < 1e-12:
        return "normal" if valor <= p99 else "pico"
    if valor >= 0.99 * p99:
        return "pico"
    if valor >= 0.99 * p90:
        return "alto"
    return "normal"


def texto_gauge(nombre, valor, estado):
    if valor is None:
        return f"{nombre}=n.d."
    return f"{nombre}={valor:g} ({estado or 'n.d.'})"


def corroboracion_io(met, umbrales):
    evidencias, estados = [], []
    for nombre in METRICAS_R1:
        v = v_met(met, nombre)
        if v is None:
            continue
        est = estado_gauge(v, umbrales, nombre)
        evidencias.append(texto_gauge(nombre, v, est))
        estados.append(est)
    fuertes = [e for e in estados if e in ("pico", "alto")]
    if fuertes:
        return "confirmado", "; ".join(evidencias)
    if evidencias:
        return "sin_pico", "; ".join(evidencias)
    return None, None


def corroboracion_locks(met, umbrales):
    """Corrobora bloqueos evaluando si los contadores globales superan el baseline (p90/p99)."""
    evidencias, estados = [], []
    for nombre in METRICAS_R2:
        v = v_met(met, nombre)
        if v is None:
            continue
        est = estado_gauge(v, umbrales, nombre)
        evidencias.append(texto_gauge(nombre, v, est))
        estados.append(est)
    
    # Exigimos estado alto o pico validado estadísticamente frente al baseline
    fuertes = [s for s in estados if s in ("pico", "alto")]
    if fuertes:
        return "confirmado", "; ".join(evidencias)
    if evidencias:
        return "sin_pico", "; ".join(evidencias)
    return None, None


def corroboracion_cpu(met, umbrales):
    """R3: Corrobora presión de CPU evaluando la saturación combinada de usuario y sistema frente al baseline."""
    evidencias, estados = [], []
    for nombre in METRICAS_R3:
        v = v_met(met, nombre)
        if v is None:
            continue
        est = estado_gauge(v, umbrales, nombre)
        evidencias.append(texto_gauge(nombre, v, est))
        estados.append(est)
    
    fuertes = [s for s in estados if s in ("pico", "alto")]
    cpu_usr = v_met(met, "cpu_usr")
    
    if fuertes or (cpu_usr is not None and cpu_usr >= config.UMBRAL_CPU_ALTO_PORCENTAJE):
        return "confirmado", "; ".join(evidencias)
    if evidencias:
        return "sin_pico", "; ".join(evidencias)
    return None, None


def corroboracion_memoria(met, umbrales):
    evidencias = []
    bch = v_met(met, "buffer_cache_hit_ratio")
    if bch is not None:
        if bch < config.BUFFER_CACHE_HIT_RATIO_DESEABLE:
            evidencias.append(
                f"buffer_cache_hit_ratio={bch:.1f} "
                f"(< {config.BUFFER_CACHE_HIT_RATIO_DESEABLE:.0f}, presión según Microsoft)")
        else:
            evidencias.append(f"buffer_cache_hit_ratio={bch:.1f} (deseable)")
    ple = v_met(met, "page_life_expectancy")
    if ple is not None:
        est = estado_gauge(ple, umbrales, "page_life_expectancy")
        evidencias.append(texto_gauge("page_life_expectancy", ple, est))
    if not evidencias:
        return None, None
    return ("confirmado" if bch is not None and bch < config.BUFFER_CACHE_HIT_RATIO_DESEABLE
            else "sin_pico"), "; ".join(evidencias)


def corroboracion_compilaciones(met):
    b = v_met(met, "batch_requests_per_sec")
    c = v_met(met, "sql_compilations_per_sec")
    if b is None or c is None:
        return None, None
    ratio = (b / c) if c > 0 else float("inf")
    texto = (f"batch_requests_per_sec={b:g}, sql_compilations_per_sec={c:g} "
             f"-> ratio {ratio:.1f}:1")
    if c > 50:
        return "confirmado", texto
    return "sin_pico", texto


def regla_r1(wt, duration, met, umbrales):
    if not wt:
        return None
    grupos_io = {
        "PAGEIOLATCH_SH", "PAGEIOLATCH_EX", "PAGEIOLATCH_UP",
        "WRITELOG", "IO_COMPLETION", "BACKUPIO",
        "PAGEIOLATCH_DT", "PAGEIOLATCH_KP", "PAGEIOLATCH_NL",
        "ASYNC_IO_COMPLETION", "LOGBUFFER",
    }
    if wt.upper() not in grupos_io:
        return None
    if duration < config.UMBRAL_DURATION_MS_ALTO:
        return None

    corrob, det = corroboracion_io(met, umbrales)
    apoyo = [
        "Revisar sys.dm_io_virtual_file_stats para ver lecturas/escrituras por archivo.",
        "Revisar contadores de disco del SO (LogicalDisk latency/queue length).",
    ]
    if det:
        apoyo.insert(0, "Corroboración de métricas frente al baseline interno: " + det + ".")

    return {
        "regla": "R1",
        "detonante": "Espera de I/O físico (PAGEIOLATCH_*/WRITELOG) con duración alta.",
        "diagnostico": "Cuello de botella de I/O físico en el subsistema de almacenamiento.",
        "corroborado": corrob,
        "metricas": det,
        "apoyo": apoyo,
        "fuente": "Microsoft Learn: Troubleshoot Slow SQL Server Performance Caused by I/O Issues",
    }


def regla_r2(wt, blocking, met, umbrales):
    if not wt:
        return None
    if not wt.upper().startswith("LCK_M_"):
        return None

    corrob, det = corroboracion_locks(met, umbrales)
    apoyo = [
        "Ubicar sesión bloqueadora mediante blocking_session_id en sys.dm_exec_requests"
        + (f" (bloqueador = {blocking})" if blocking else "") + ".",
    ]
    if det:
        apoyo.insert(0, "Corroboración de métricas de bloqueo: " + det + ".")

    return {
        "regla": "R2",
        "detonante": "Espera de lock (LCK_M_*) por contención de concurrencia.",
        "diagnostico": "Bloqueo o contención transaccional entre sesiones.",
        "corroborado": corrob,
        "metricas": det,
        "apoyo": apoyo,
        "fuente": "Microsoft Learn: Understand and Resolve SQL Server Blocking Problems",
    }


def regla_r3(wt, cpu, duration, signal, met, umbrales):
    cpu_close = False
    if (
        duration and cpu is not None
        and duration > config.UMBRAL_DURACION_LENTA_MS
        and cpu >= config.UMBRAL_DURACION_LENTA_MS * 0.5
    ):
        cpu_close = cpu >= duration * (1 - config.TOLERANCIA_CPU_DURATION)

    if not ((wt and wt.upper() == "SOS_SCHEDULER_YIELD") or cpu_close):
        return None

    corrob, det = corroboracion_cpu(met, umbrales)
    apoyo = [
        "Revisar signal_wait_time_ms vs resource_wait_time_ms para confirmar saturación de CPU.",
        "Buscar planes de ejecución costosos o índices faltantes.",
    ]
    if det:
        apoyo.insert(0, "Corroboración de métricas de CPU: " + det + ".")

    return {
        "regla": "R3",
        "detonante": "Espera de planificador (SOS_SCHEDULER_YIELD) o consumo intensivo de CPU (cpu_time ≈ duration).",
        "diagnostico": "Presión real de CPU en el motor por consultas ineficientes o carencia de índices.",
        "corroborado": corrob,
        "metricas": det,
        "apoyo": apoyo,
        "fuente": "Microsoft Learn: Troubleshoot High CPU Usage Issues in SQL Server",
    }


def regla_r4(wt, wait_resource):
    if not wt:
        return None
    if wt.upper() in ("PAGELATCH_SH", "PAGELATCH_EX", "PAGELATCH_UP"):
        es_tempdb_alloc = False
        if wait_resource:
            partes = str(wait_resource).split(":")
            if len(partes) >= 3 and partes[0].strip() == "2":
                es_tempdb_alloc = True
        return {
            "regla": "R4",
            "detonante": "Espera PAGELATCH sobre páginas de asignación de tempdb (patrón 2:1:x).",
            "diagnostico": "Contención de asignación en tempdb (PFS/GAM/SGAM).",
            "corroborado": None,
            "metricas": "N/A (evento suficiente por sí solo según Microsoft).",
            "apoyo": ["Igualar archivos de datos de tempdb al número de cores físicos."],
            "fuente": "Microsoft Learn: Recommendations to Reduce Allocation Contention",
        }
    return None


def regla_r5(wt, met, umbrales):
    if not wt:
        return None
    if wt.upper() != "RESOURCE_SEMAPHORE":
        return None

    corrob, det = corroboracion_memoria(met, umbrales)
    apoyo = ["Revisar sys.dm_exec_query_memory_grants para identificar consultas con memory grants excesivos."]
    if det:
        apoyo.insert(0, "Corroboración de memoria: " + det + ".")

    return {
        "regla": "R5",
        "detonante": "RESOURCE_SEMAPHORE: espera por concesión de memoria para operaciones de SQL.",
        "diagnostico": "Presión severa de memoria RAM / Buffer Pool insuficientes.",
        "corroborado": corrob,
        "metricas": det,
        "apoyo": apoyo,
        "fuente": "Microsoft Learn: Troubleshoot Slow Performance Caused by Memory Grants",
    }


def regla_r6(wt):
    if not wt:
        return None
    if wt.upper() != "ASYNC_NETWORK_IO":
        return None
    return {
        "regla": "R6",
        "detonante": "ASYNC_NETWORK_IO: el motor espera que el cliente procese los datos enviados.",
        "diagnostico": "Aplicación cliente lenta consumiendo los resultados.",
        "corroborado": None,
        "metricas": "N/A (evento suficiente por sí solo según Microsoft).",
        "apoyo": ["Revisar desempeño de la aplicación cliente y red."],
        "fuente": "Microsoft Learn: Troubleshoot Slow Queries Resulting from ASYNC_NETWORK_IO",
    }


def regla_r7(command, wait_type, logical_reads, historial_comando, met):
    if not command:
        return None
    if es_relevante(wait_type):
        return None
    if historial_comando is None or historial_comando <= 0:
        return None
    if logical_reads is None:
        return None
    if logical_reads < historial_comando * (1 + config.UMBRAL_DESVIO_LOGICAL_READS):
        return None

    corrob, det = corroboracion_compilaciones(met)
    apoyo = ["Analizar el plan de ejecución y estadísticas de la consulta."]
    if det:
        apoyo.insert(0, "Corroboración de compilaciones: " + det + ".")

    return {
        "regla": "R7",
        "detonante": f"Ejecución intensiva sin espera con lecturas lógicas muy superiores al histórico ({historial_comando:.0f}).",
        "diagnostico": "Plan de ejecución subóptimo o carencia de índices adecuados.",
        "corroborado": corrob,
        "metricas": det,
        "apoyo": apoyo,
        "fuente": "Microsoft Learn: Troubleshoot Slow-Running Queries in SQL Server",
    }


def leer_eventos(ruta):
    eventos = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                ev = json.loads(linea)
            except json.JSONDecodeError:
                continue
            eventos.append(ev)
    return eventos


def encontrar_events_log():
    rutas = {}
    for carpeta in os.listdir(config.DIR_CORRIDAS):
        ruta_carpeta = os.path.join(config.DIR_CORRIDAS, carpeta)
        if not os.path.isdir(ruta_carpeta):
            continue
        if carpeta.lower() in config.CARPETAS_NO_CORRIDA:
            continue
        ev_file = os.path.join(ruta_carpeta, "events.log")
        if os.path.exists(ev_file):
            rutas[carpeta] = ev_file
    return rutas


def aplicar_reglas_a_eventos(eventos, df_m, umbrales):
    detecciones = []
    historial = {}

    for ev in eventos:
        en = ev.get("event_name")
        if en not in ("sql_batch_completed", "wait_info", "blocked_process_report"):
            continue

        wt = ev.get("wait_type") or None
        duration = float(ev.get("duration") or 0)
        cpu = float(ev.get("cpu_time") or 0) if ev.get("cpu_time") is not None else None
        logical_reads = float(ev.get("logical_reads") or 0)
        blocking = ev.get("blocking_session_id")
        wait_resource = ev.get("wait_resource")
        signal = float(ev.get("signal_wait_time_ms") or 0) if ev.get("signal_wait_time_ms") is not None else None

        wt_relevante = bool(wt and es_relevante(wt))
        w_eff = wt if wt_relevante else None

        ocurrencia = {
            "run_name": ev.get("_run", ""),
            "timestamp": ev.get("timestamp"),
            "event_name": en,
            "session_id": ev.get("session_id"),
            "command": ev.get("command"),
            "wait_type": wt,
            "duration_ms": duration,
            "cpu_time_ms": cpu,
            "logical_reads": logical_reads,
            "blocking_session_id": blocking,
            "wait_resource": wait_resource,
            "signal_wait_time_ms": signal,
        }

        r1 = regla_r1(w_eff, duration, ev, umbrales)
        r2 = regla_r2(w_eff, blocking, ev, umbrales)
        r3 = regla_r3(w_eff, cpu, duration, signal, ev, umbrales)
        r4 = regla_r4(w_eff, wait_resource)
        r5 = regla_r5(w_eff, ev, umbrales)
        r6 = regla_r6(w_eff)

        reglas = [x for x in (r1, r2, r3, r4, r5, r6) if x]

        if not wt_relevante:
            cmd = ev.get("command")
            hist = historial.get(cmd)
            r7 = regla_r7(cmd, wt, logical_reads, hist, ev)
            if r7:
                reglas.append(r7)

        # Historial robusto por comando (acumulado ponderado para R7)
        cmd = ev.get("command")
        if en == "sql_batch_completed" and cmd:
            if cmd not in historial:
                historial[cmd] = logical_reads
            else:
                historial[cmd] = 0.8 * historial[cmd] + 0.2 * logical_reads

        for regla in reglas:
            fila = dict(ocurrencia)
            fila.update(regla)
            detecciones.append(fila)

    return detecciones, historial


def main():
    rutas = encontrar_events_log()
    if not rutas:
        log(f"No se encontraron events.log en {config.DIR_CORRIDAS}.")
        return

    todas_detecciones = []
    resumen = []

    for run in sorted(rutas):
        eventos = leer_eventos(rutas[run])
        for ev in eventos:
            ev["_run"] = run

        ruta_m = os.path.join(os.path.dirname(rutas[run]), "metrics.log")
        df_m = leer_metricas(ruta_m)
        umbrales = umbrales_por_corrida(df_m)
        eventos = unir_metricas(eventos, df_m, umbrales)

        detecciones, _ = aplicar_reglas_a_eventos(eventos, df_m, umbrales)
        todas_detecciones.extend(detecciones)

        resumen.append({
            "run_name": run,
            "eventos_leidos": len(eventos),
            "metricas_adjuntas": int(df_m.shape[0]) if df_m is not None else 0,
            "detecciones": len(detecciones),
        })

    os.makedirs(config.DIR_REGLAS, exist_ok=True)
    ruta_csv = os.path.join(config.DIR_REGLAS, "detecciones_reglas.csv")

    if todas_detecciones:
        df = pd.DataFrame(todas_detecciones)
        df.to_csv(ruta_csv, index=False, encoding="utf-8-sig")
        log(f"Detecciones guardadas en: {ruta_csv} ({len(df)} filas)")

        ruta_resumen = os.path.join(config.DIR_REGLAS, "resumen_reglas.csv")
        resumen_reglas = df.groupby(["regla", "run_name"]).size().reset_index(name="conteo")
        resumen_reglas.to_csv(ruta_resumen, index=False, encoding="utf-8-sig")

        corrob = df.groupby(["regla", "corroborado"]).size().reset_index(name="conteo")
        
        print("\n=== REGLAS DE MOTOR (Alineadas con Microsoft Learn) ===")
        print(df.groupby("regla").size().to_string())
        print("\nCorroboración métrica:")
        print(corrob.to_string(index=False))
    else:
        log("Sin detecciones registradas.")


if __name__ == "__main__":
    main()