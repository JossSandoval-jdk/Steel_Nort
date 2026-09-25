"""
04_reglas_motor.py
==================

Motor de reglas alineado con la metodología oficial de Microsoft Learn
para diagnosticar causas de anomalías OLTP en SQL Server.

Evidencia doble — EVENTOS + MÉTRICAS:
    - Eventos  : events.log  -> wait_type, duration, cpu_time, logical_reads...
    - Métricas : metrics.log -> contadores de rendimiento y del SO.

Reglas R1-R7: cada evento puede disparar varias; la celda "corroborado"
indica si las métricas globales confirmaron el diagnóstico.

Salidas (en <OUTPUT>/modelado/reglas_motor/):
    detecciones_reglas.csv
    diagnostico_reglas.json
    resumen_reglas.csv
"""

import json
import os
import re

import numpy as np
import pandas as pd

import config


def log(msg):
    print(f"[REGLAS-MOTOR] {msg}", flush=True)


# Esperas de fondo del motor: no son indicio de anomalía.
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

METRICAS_R1 = ["disk_read_per_sec", "disk_write_per_sec",
               "page_reads_per_sec", "page_writes_per_sec",
               "total_reads_delta", "total_writes_delta"]
METRICAS_R2 = ["lock_waits", "deadlocks_per_sec", "total_locks"]
METRICAS_R3 = ["cpu_usr", "cpu_sys"]


def es_relevante(wait_type):
    return bool(wait_type and wait_type.upper() not in FONDO)


# ---------------------------------------------------------------------------
# Lectura de métricas y unión con eventos
# ---------------------------------------------------------------------------

def leer_metricas(ruta):
    """metrics.log -> df pivoteado (timestamps x métrica), con total_*_delta."""
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
            registros.append({"timestamp": partes[0].strip(),
                              "metrica": partes[1].strip(),
                              "valor": valor})
    if not registros:
        return None

    df = pd.DataFrame(registros)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    ancho = df.pivot_table(index="timestamp", columns="metrica",
                           values="valor", aggfunc="first")
    for col in ("total_reads", "total_writes"):
        if col in ancho.columns:
            ancho[col + "_delta"] = ancho[col].diff().fillna(0.0)
    return ancho


def umbrales_por_corrida(df_m):
    """Baseline p90/p99 por métrica (referencia normal interna)."""
    out = {}
    if df_m is None:
        return out
    for col in df_m.columns:
        serie = pd.to_numeric(df_m[col], errors="coerce").dropna()
        if serie.empty:
            continue
        out[col] = (float(serie.quantile(0.90)), float(serie.quantile(0.99)))
    return out


def unir_metricas(eventos, df_m, umbrales):
    """Adjunta a cada evento las métricas más cercanas en el tiempo (m_*)."""
    if df_m is None or not eventos:
        return eventos

    ev = pd.DataFrame(eventos)
    ev["_ts"] = pd.to_datetime(ev["timestamp"], errors="coerce")
    ev["_orden"] = np.arange(len(ev))

    m = df_m.reset_index().rename(columns={"timestamp": "_ts"})
    merged = pd.merge_asof(ev.sort_values("_ts"), m.sort_values("_ts"),
                           on="_ts", direction="nearest"
                           ).sort_values("_orden")

    cols_m = list(df_m.columns)
    eventos_finales = []
    for i, fila in merged.iterrows():
        ev_i = dict(ev.loc[fila["_orden"], :])
        ev_i.pop("_ts", None)
        ev_i = {k: (None if isinstance(v, float) and pd.isna(v) else v)
                for k, v in ev_i.items()}
        for col in cols_m:
            v = fila.get(col)
            ev_i["m_" + col] = None if (isinstance(v, float) and pd.isna(v)) else v
        eventos_finales.append(ev_i)
    return eventos_finales


# ---------------------------------------------------------------------------
# Corroboración con métricas (baseline interno p90/p99)
# ---------------------------------------------------------------------------

def v_met(met, nombre):
    v = met.get("m_" + nombre)
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def estado_gauge(valor, umbrales, nombre):
    """Estado de una métrica frente a su baseline (p90/p99)."""
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


def corroborar(met, umbrales, metricas, condicion_extra=None):
    """Corrobora usando las métricas de ``metricas``.

    Devuelve ("confirmado"|"sin_pico", evidencia) si hay evidencia,
    o (None, None) si no hay ninguna métrica disponible.
    ``condicion_extra`` (opcional) puede forzar "confirmado" (p. ej. CPU
    con cpu_usr sobre un umbral absoluto del config).
    """
    evidencias, estados = [], []
    for nombre in metricas:
        v = v_met(met, nombre)
        if v is None:
            continue
        est = estado_gauge(v, umbrales, nombre)
        evidencias.append(texto_gauge(nombre, v, est))
        estados.append(est)

    fuertes = [s for s in estados if s in ("pico", "alto")]
    extra = condicion_extra is not None and bool(condicion_extra(met))
    if fuertes or extra:
        return "confirmado", "; ".join(evidencias)
    if evidencias:
        return "sin_pico", "; ".join(evidencias)
    return None, None


def corroboracion_io(met, umbrales):
    return corroborar(met, umbrales, METRICAS_R1)


def corroboracion_locks(met, umbrales):
    return corroborar(met, umbrales, METRICAS_R2)


def corroboracion_cpu(met, umbrales):
    return corroborar(met, umbrales, METRICAS_R3,
                      lambda m: v_met(m, "cpu_usr") is not None
                      and v_met(m, "cpu_usr") >= config.UMBRAL_CPU_ALTO_MS)


def corroboracion_memoria(met, umbrales):
    evidencias = []
    bch = v_met(met, "buffer_cache_hit_ratio")
    if bch is not None:
        if bch < config.BUFFER_CACHE_HIT_RATIO_DESEABLE:
            evidencias.append(
                f"buffer_cache_hit_ratio={bch:.1f} "
                f"(< {config.BUFFER_CACHE_HIT_RATIO_DESEABLE:.0f}, presión "
                "según Microsoft)")
        else:
            evidencias.append(f"buffer_cache_hit_ratio={bch:.1f} (deseable)")
    ple = v_met(met, "page_life_expectancy")
    if ple is not None:
        evidencias.append(texto_gauge(
            "page_life_expectancy", ple,
            estado_gauge(ple, umbrales, "page_life_expectancy")))
    if not evidencias:
        return None, None
    return ("confirmado" if bch is not None
            and bch < config.BUFFER_CACHE_HIT_RATIO_DESEABLE
            else "sin_pico"), "; ".join(evidencias)


def corroboracion_compilaciones(met):
    b = v_met(met, "batch_requests_per_sec")
    c = v_met(met, "sql_compilations_per_sec")
    if b is None or c is None:
        return None, None
    ratio = (b / c) if c > 0 else float("inf")
    texto = (f"batch_requests_per_sec={b:g}, "
             f"sql_compilations_per_sec={c:g} -> ratio {ratio:.1f}:1")
    return ("confirmado" if c > 50 else "sin_pico"), texto


# ---------------------------------------------------------------------------
# Reglas R1-R7 (metodología Microsoft Learn)
# ---------------------------------------------------------------------------

def _regla(regla, detonante, diagnostico, corrob, det, apoyo, fuente):
    return {"regla": regla, "detonante": detonante,
            "diagnostico": diagnostico, "corroborado": corrob,
            "metricas": det, "apoyo": apoyo, "fuente": fuente}


def _apoyo(mensajes, det, prefijo):
    """Base de apoyo (uno o más mensajes) + evidencia métrica al inicio."""
    apoyo = list(mensajes)
    if det:
        apoyo.insert(0, prefijo + det + ".")
    return apoyo


def regla_r1(wt, duration, met, umbrales):
    grupos_io = {
        "PAGEIOLATCH_SH", "PAGEIOLATCH_EX", "PAGEIOLATCH_UP",
        "WRITELOG", "IO_COMPLETION", "BACKUPIO",
        "PAGEIOLATCH_DT", "PAGEIOLATCH_KP", "PAGEIOLATCH_NL",
        "ASYNC_IO_COMPLETION", "LOGBUFFER",
    }
    if not wt or wt.upper() not in grupos_io \
            or duration < config.UMBRAL_DURATION_MS_ALTO:
        return None
    corrob, det = corroboracion_io(met, umbrales)
    return _regla(
        "R1", "Espera de I/O físico (PAGEIOLATCH_*/WRITELOG) con duración alta.",
        "Cuello de botella de I/O físico en el subsistema de almacenamiento.",
        corrob, det,
        _apoyo(["Revisar sys.dm_io_virtual_file_stats para ver lecturas/"
                "escrituras por archivo.",
                "Revisar contadores de disco del SO "
                "(LogicalDisk latency/queue length)."],
               det, "Corroboración de métricas frente al baseline interno: "),
        "Microsoft Learn: Troubleshoot Slow SQL Server Performance Caused by "
        "I/O Issues")


def regla_r2(wt, blocking, met, umbrales):
    if not wt or not wt.upper().startswith("LCK_M_"):
        return None
    corrob, det = corroboracion_locks(met, umbrales)
    return _regla(
        "R2", "Espera de lock (LCK_M_*) por contención de concurrencia.",
        "Bloqueo o contención transaccional entre sesiones.", corrob, det,
        _apoyo(["Ubicar sesión bloqueadora mediante blocking_session_id en "
                "sys.dm_exec_requests"
                + (f" (bloqueador = {blocking})" if blocking else "") + "."],
               det, "Corroboración de métricas de bloqueo: "),
        "Microsoft Learn: Understand and Resolve SQL Server Blocking Problems")


def regla_r3(wt, cpu, duration, signal, met, umbrales):
    cpu_close = (duration and cpu is not None
                 and duration > config.UMBRAL_DURACION_LENTA_MS
                 and cpu >= config.UMBRAL_DURACION_LENTA_MS * 0.5
                 and cpu >= duration * (1 - config.TOLERANCIA_CPU_DURATION))
    if not ((wt and wt.upper() == "SOS_SCHEDULER_YIELD") or cpu_close):
        return None
    corrob, det = corroboracion_cpu(met, umbrales)
    return _regla(
        "R3", "Espera de planificador (SOS_SCHEDULER_YIELD) o consumo "
              "intensivo de CPU (cpu_time ≈ duration).",
        "Presión real de CPU en el motor por consultas ineficientes o "
        "carencia de índices.", corrob, det,
        _apoyo(["Revisar signal_wait_time_ms vs resource_wait_time_ms para "
                "confirmar saturación de CPU.",
                "Buscar planes de ejecución costosos o índices faltantes."],
               det, "Corroboración de métricas de CPU: "),
        "Microsoft Learn: Troubleshoot High CPU Usage Issues in SQL Server")


def regla_r4(wt, wait_resource):
    if not wt or wt.upper() not in ("PAGELATCH_SH", "PAGELATCH_EX",
                                    "PAGELATCH_UP"):
        return None
    es_tempdb_alloc = False
    if wait_resource:
        partes = str(wait_resource).split(":")
        es_tempdb_alloc = len(partes) >= 3 and partes[0].strip() == "2"
    if not es_tempdb_alloc:
        return None
    return _regla(
        "R4", "Espera PAGELATCH sobre páginas de asignación de tempdb "
              "(patrón 2:1:x).",
        "Contención de asignación en tempdb (PFS/GAM/SGAM).", None,
        "N/A (evento suficiente por sí solo según Microsoft).",
        ["Igualar archivos de datos de tempdb al número de cores físicos."],
        "Microsoft Learn: Recommendations to Reduce Allocation Contention")


def regla_r5(wt, met, umbrales):
    if not wt or wt.upper() != "RESOURCE_SEMAPHORE":
        return None
    corrob, det = corroboracion_memoria(met, umbrales)
    return _regla(
        "R5", "RESOURCE_SEMAPHORE: espera por concesión de memoria para "
              "operaciones de SQL.",
        "Presión severa de memoria RAM / Buffer Pool insuficientes.",
        corrob, det,
        _apoyo(["Revisar sys.dm_exec_query_memory_grants para identificar "
                "consultas con memory grants excesivos."], det,
               "Corroboración de memoria: "),
        "Microsoft Learn: Troubleshoot Slow Performance Caused by Memory Grants")


def regla_r6(wt):
    if not wt or wt.upper() != "ASYNC_NETWORK_IO":
        return None
    return _regla(
        "R6", "ASYNC_NETWORK_IO: el motor espera que el cliente procese los "
              "datos enviados.",
        "Aplicación cliente lenta consumiendo los resultados.", None,
        "N/A (evento suficiente por sí solo según Microsoft).",
        ["Revisar desempeño de la aplicación cliente y red."],
        "Microsoft Learn: Troubleshoot Slow Queries Resulting from "
        "ASYNC_NETWORK_IO")


def regla_r7(command, wait_type, logical_reads, historial_comando, met):
    if not command or es_relevante(wait_type) or logical_reads is None:
        return None
    if historial_comando is None or historial_comando <= 0:
        return None
    if logical_reads < historial_comando * (1 + config.UMBRAL_DESVIO_LOGICAL_READS):
        return None
    corrob, det = corroboracion_compilaciones(met)
    return _regla(
        "R7", f"Ejecución intensiva sin espera con lecturas lógicas muy "
              f"superiores al histórico ({historial_comando:.0f}).",
        "Plan de ejecución subóptimo o carencia de índices adecuados.",
        corrob, det,
        _apoyo(["Analizar el plan de ejecución y estadísticas de la consulta."],
               det, "Corroboración de compilaciones: "),
        "Microsoft Learn: Troubleshoot Slow-Running Queries in SQL Server")


# ---------------------------------------------------------------------------
# Lectura de eventos y aplicación de reglas
# ---------------------------------------------------------------------------

def leer_eventos(ruta):
    eventos = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                eventos.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
    return eventos


def encontrar_events_log():
    """Localiza events.log por corrida. Orden: baseline/, anomalias/,
    contenedores legacy (p.ej. run1-7), y carpetas en la raíz."""
    raiz = config.DIR_CORRIDAS

    def _marcar(ruta_carpeta, nombre):
        ev_file = os.path.join(ruta_carpeta, "events.log")
        if os.path.isfile(ev_file):
            rutas.setdefault(nombre, ev_file)

    def _escaneo(raiz_dir):
        if not os.path.isdir(raiz_dir):
            return
        for carpeta in sorted(os.listdir(raiz_dir)):
            if not os.path.isdir(os.path.join(raiz_dir, carpeta)):
                continue
            if carpeta.lower() in config.CARPETAS_NO_CORRIDA:
                continue
            _marcar(os.path.join(raiz_dir, carpeta), carpeta)

    rutas = {}
    _escaneo(os.path.join(raiz, "baseline"))
    _escaneo(os.path.join(raiz, "anomalias"))

    for carpeta in sorted(os.listdir(raiz)):
        contenedor = os.path.join(raiz, carpeta)
        if not os.path.isdir(contenedor) \
                or carpeta.lower() in config.CARPETAS_NO_CORRIDA \
                or carpeta in ("baseline", "anomalias"):
            continue
        subcarpetas = [s for s in os.listdir(contenedor)
                       if os.path.isdir(os.path.join(contenedor, s))]
        if any(os.path.isfile(os.path.join(contenedor, s, "events.log"))
               for s in subcarpetas):
            _escaneo(contenedor)

    _escaneo(raiz)
    return rutas


def aplicar_reglas_a_eventos(eventos, df_m, umbrales):
    """Devuelve (detecciones, historial_por_comando)."""
    detecciones = []
    historial = {}

    for ev in eventos:
        en = ev.get("event_name")
        if en not in ("sql_batch_completed", "wait_info", "blocked_process_report"):
            continue

        wt = ev.get("wait_type") or None
        duration = float(ev.get("duration") or 0)
        cpu = float(ev.get("cpu_time") or 0) if ev.get("cpu_time") is not None else None
        signal = float(ev.get("signal_wait_time_ms") or 0) \
            if ev.get("signal_wait_time_ms") is not None else None
        logical_reads = float(ev.get("logical_reads") or 0)
        blocking = ev.get("blocking_session_id")
        wait_resource = ev.get("wait_resource")

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

        reglas = [r for r in (
            regla_r1(w_eff, duration, ev, umbrales),
            regla_r2(w_eff, blocking, ev, umbrales),
            regla_r3(w_eff, cpu, duration, signal, ev, umbrales),
            regla_r4(w_eff, wait_resource),
            regla_r5(w_eff, ev, umbrales),
            regla_r6(w_eff),
        ) if r]

        cmd = ev.get("command")
        if not wt_relevante:
            r7 = regla_r7(cmd, wt, logical_reads, historial.get(cmd), ev)
            if r7:
                reglas.append(r7)

        if en == "sql_batch_completed" and cmd:
            historial[cmd] = 0.8 * historial.get(cmd, logical_reads) + \
                0.2 * logical_reads if cmd in historial else logical_reads

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

    if not todas_detecciones:
        log("Sin detecciones registradas.")
        return

    df = pd.DataFrame(todas_detecciones)
    df.to_csv(ruta_csv, index=False, encoding="utf-8-sig")
    log(f"Detecciones guardadas en: {ruta_csv} ({len(df)} filas)")

    catalogo = {}
    for _, fila in df.iterrows():
        regla = fila.get("regla")
        if regla and regla not in catalogo and fila.get("diagnostico"):
            catalogo[regla] = {"detonante": fila.get("detonante"),
                               "diagnostico": fila.get("diagnostico"),
                               "fuente": fila.get("fuente")}
    ruta_cat = os.path.join(config.DIR_REGLAS, "diagnostico_reglas.json")
    with open(ruta_cat, "w", encoding="utf-8") as f:
        json.dump({"reglas": catalogo}, f, ensure_ascii=False, indent=2)
    log(f"Catálogo de diagnóstico en: {ruta_cat} ({len(catalogo)} reglas)")

    df.groupby(["regla", "run_name"]).size().reset_index(name="conteo").to_csv(
        os.path.join(config.DIR_REGLAS, "resumen_reglas.csv"),
        index=False, encoding="utf-8-sig")

    corrob = df.groupby(["regla", "corroborado"]).size().reset_index(name="conteo")
    print("\n=== REGLAS DE MOTOR (Alineadas con Microsoft Learn) ===")
    print(df.groupby("regla").size().to_string())
    print("\nCorroboración métrica:")
    print(corrob.to_string(index=False))


if __name__ == "__main__":
    main()