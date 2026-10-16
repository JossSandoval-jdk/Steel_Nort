"""
reglas.py
=========
Motor de reglas R1-R7 en vivo (metodología Microsoft Learn).

Porta a producción lo que el pipeline offline aplica en
tools/modelado/02_reglas.py. Cada evento XE se contrasta con las reglas y,
si alguna se cumple, se devuelve una detección con:

    regla        código (R1..R7)
    detonante    qué se observó en el evento
    diagnostico  causa probable según Microsoft Learn
    corroborado  confirmado | sin_pico | n.d. (métricas del nodo)
    metricas     valores usados para corroborar
    apoyo        pasos de diagnóstico recomendados
    fuente       referencia de la regla
    evidencia    snapshot crudo del evento (para auditoría)

En vivo no hay baseline p90/p99 por corrida como en offline, así que la
corroboración es best-effort: usa umbrales absolutos del config y marca
sin_pico cuando no puede afirmar un pico. La detección de la regla es
idéntica a la del entrenamiento.
"""

from __future__ import annotations

import logging
import math

log = logging.getLogger("steelnort.reglas")

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

# Umbrales espejo de tools/modelado/modelado_config.py.
UMBRAL_DURATION_MS_ALTO = 500
TOLERANCIA_CPU_DURATION = 0.10
UMBRAL_DESVIO_LOGICAL_READS = 1.5
UMBRAL_DURACION_LENTA_MS = 800
UMBRAL_CPU_ALTO_MS = 80.0
BUFFER_CACHE_HIT_RATIO_DESEABLE = 90.0

# Etiqueta corta por regla (para titular de alerta).
ETIQUETA = {
    "R1": "I/O fisico",
    "R2": "bloqueos",
    "R3": "CPU",
    "R4": "tempdb",
    "R5": "memoria",
    "R6": "cliente lento",
    "R7": "plan/indices",
    "RML": "detector ML",
}

# Campos del evento que se guardan como evidencia.
_EVIDENCIA = (
    "timestamp", "session_id", "event_name", "command", "wait_type",
    "duration", "cpu_time", "logical_reads", "writes",
    "blocking_session_id", "wait_resource", "signal_wait_time_ms",
    "sql_text",
)


# ==========================================
# Utilidades
# ==========================================
def es_relevante(wait_type) -> bool:
    """Un wait es relevante si no está en la lista de fondo."""
    return bool(wait_type and wait_type.upper() not in FONDO)


def _num(valor):
    """Convierte a float finito o devuelve None."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def normalizar_evento(ev: dict) -> dict:
    """Normaliza un evento crudo de XE al vocabulario del motor.

    XE entrega duration y cpu_time en microsegundos; el motor trabaja en
    milisegundos, como el events.log del entrenamiento.
    """
    dur = _num(ev.get("duration"))
    cpu = _num(ev.get("cpu_time"))
    sig = _num(ev.get("signal_duration"))
    if sig is None:
        sig = _num(ev.get("signal_wait_time_ms"))
    nombre = str(ev.get("event_name") or "")
    return {
        "event_name": nombre[3:] if nombre.startswith("xe.") else nombre,
        "timestamp": ev.get("timestamp"),
        "session_id": ev.get("session_id"),
        "command": ev.get("command") or ev.get("statement_type"),
        "wait_type": ev.get("wait_type"),
        "duration": dur / 1000.0 if dur is not None else 0.0,
        "cpu_time": cpu / 1000.0 if cpu is not None else None,
        "logical_reads": _num(ev.get("logical_reads")),
        "writes": _num(ev.get("writes")),
        "blocking_session_id": ev.get("blocking_session_id"),
        "wait_resource": ev.get("wait_resource"),
        "signal_wait_time_ms": sig / 1000.0 if sig is not None else None,
        "sql_text": ev.get("sql_text") or ev.get("message"),
    }


# ==========================================
# Corroboración con métricas
# ==========================================
def _v_met(met, nombre):
    """Valor de la métrica nombre en met (con o sin prefijo m_)."""
    if not met:
        return None
    if nombre in met:
        return _num(met.get(nombre))
    return _num(met.get("m_" + nombre))


def estado_gauge(valor, umbrales, nombre):
    """Estado de una métrica frente a su baseline (p90/p99), si lo hay."""
    if valor is None:
        return None
    tupla = (umbrales or {}).get(nombre)
    if not tupla or not math.isfinite(tupla[0]):
        return "normal"
    p90, p99 = tupla
    if p99 - p90 < 1e-12:
        return "normal" if valor <= p99 else "pico"
    if valor >= 0.99 * p99:
        return "pico"
    if valor >= 0.99 * p90:
        return "alto"
    return "normal"


def _texto_gauge(nombre, valor, estado):
    if valor is None:
        return f"{nombre}=n.d."
    return f"{nombre}={valor:g} ({estado or 'n.d.'})"


def _corroborar(met, umbrales, metricas, condicion_extra=None):
    """Corrobora usando las métricas indicadas."""
    evidencias, estados = [], []
    for nombre in metricas:
        v = _v_met(met, nombre)
        if v is None:
            continue
        est = estado_gauge(v, umbrales, nombre)
        evidencias.append(_texto_gauge(nombre, v, est))
        estados.append(est)

    fuertes = [s for s in estados if s in ("pico", "alto")]
    extra = condicion_extra is not None and bool(condicion_extra(met))
    if fuertes or extra:
        return "confirmado", "; ".join(evidencias)
    if evidencias:
        return "sin_pico", "; ".join(evidencias)
    return None, None


def _corr_io(met, umbrales):
    return _corroborar(met, umbrales, METRICAS_R1)


def _corr_locks(met, umbrales):
    return _corroborar(met, umbrales, METRICAS_R2)


def _corr_cpu(met, umbrales):
    return _corroborar(
        met, umbrales, METRICAS_R3,
        lambda m: _v_met(m, "cpu_usr") is not None
        and _v_met(m, "cpu_usr") >= UMBRAL_CPU_ALTO_MS,
    )


def _corr_memoria(met, umbrales):
    evidencias = []
    bch = _v_met(met, "buffer_cache_hit_ratio")
    if bch is not None:
        if bch < BUFFER_CACHE_HIT_RATIO_DESEABLE:
            evidencias.append(
                f"buffer_cache_hit_ratio={bch:.1f} "
                f"(< {BUFFER_CACHE_HIT_RATIO_DESEABLE:.0f}, presión)"
            )
        else:
            evidencias.append(f"buffer_cache_hit_ratio={bch:.1f} (deseable)")
    ple = _v_met(met, "page_life_expectancy")
    if ple is not None:
        evidencias.append(_texto_gauge(
            "page_life_expectancy", ple,
            estado_gauge(ple, umbrales, "page_life_expectancy")))
    if not evidencias:
        return None, None
    confirmado = bch is not None and bch < BUFFER_CACHE_HIT_RATIO_DESEABLE
    return ("confirmado" if confirmado else "sin_pico"), "; ".join(evidencias)


def _corr_compilaciones(met):
    b = _v_met(met, "batch_requests_per_sec")
    c = _v_met(met, "sql_compilations_per_sec")
    if b is None or c is None:
        return None, None
    ratio = (b / c) if c > 0 else float("inf")
    texto = (f"batch_requests_per_sec={b:g}, "
             f"sql_compilations_per_sec={c:g} -> ratio {ratio:.1f}:1")
    return ("confirmado" if c > 50 else "sin_pico"), texto


# ==========================================
# Reglas R1-R7
# ==========================================
def _regla(codigo, detonante, diagnostico, corrob, det, apoyo, fuente):
    return {
        "regla": codigo,
        "detonante": detonante,
        "diagnostico": diagnostico,
        "corroborado": corrob or "n.d.",
        "metricas": det,
        "apoyo": apoyo,
        "fuente": fuente,
    }


def _apoyo(mensajes, det, prefijo):
    """Base de apoyo + evidencia métrica al inicio (si la hay)."""
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
    if not wt or wt.upper() not in grupos_io or duration < UMBRAL_DURATION_MS_ALTO:
        return None
    corrob, det = _corr_io(met, umbrales)
    return _regla(
        "R1",
        "Espera de I/O físico (PAGEIOLATCH_*/WRITELOG) con duración alta.",
        "Cuello de botella de I/O físico en el subsistema de almacenamiento.",
        corrob, det,
        _apoyo([
            "Revisar sys.dm_io_virtual_file_stats para ver lecturas/escrituras por archivo.",
            "Revisar contadores de disco del SO (LogicalDisk latency/queue length).",
        ], det, "Corroboración de métricas frente al baseline interno: "),
        "Microsoft Learn: Troubleshoot Slow SQL Server Performance Caused by I/O Issues",
    )


def regla_r2(wt, blocking, met, umbrales):
    if not wt or not wt.upper().startswith("LCK_M_"):
        return None
    corrob, det = _corr_locks(met, umbrales)
    return _regla(
        "R2",
        "Espera de lock (LCK_M_*) por contención de concurrencia.",
        "Bloqueo o contención transaccional entre sesiones.",
        corrob, det,
        _apoyo([
            "Ubicar sesión bloqueadora mediante blocking_session_id en "
            "sys.dm_exec_requests"
            + (f" (bloqueador = {blocking})" if blocking else "") + "."
        ], det, "Corroboración de métricas de bloqueo: "),
        "Microsoft Learn: Understand and Resolve SQL Server Blocking Problems",
    )


def regla_r3(wt, cpu, duration, signal, met, umbrales):
    cpu_close = (
        duration and cpu is not None
        and duration > UMBRAL_DURACION_LENTA_MS
        and cpu >= UMBRAL_DURACION_LENTA_MS * 0.5
        and cpu >= duration * (1 - TOLERANCIA_CPU_DURATION)
    )
    if not ((wt and wt.upper() == "SOS_SCHEDULER_YIELD") or cpu_close):
        return None
    corrob, det = _corr_cpu(met, umbrales)
    return _regla(
        "R3",
        "Espera de planificador (SOS_SCHEDULER_YIELD) o consumo intensivo "
        "de CPU (cpu_time ≈ duration).",
        "Presión real de CPU en el motor por consultas ineficientes o "
        "carencia de índices.",
        corrob, det,
        _apoyo([
            "Revisar signal_wait_time_ms vs resource_wait_time_ms para "
            "confirmar saturación de CPU.",
            "Buscar planes de ejecución costosos o índices faltantes.",
        ], det, "Corroboración de métricas de CPU: "),
        "Microsoft Learn: Troubleshoot High CPU Usage Issues in SQL Server",
    )


def regla_r4(wt, wait_resource):
    if not wt or wt.upper() not in ("PAGELATCH_SH", "PAGELATCH_EX", "PAGELATCH_UP"):
        return None
    es_tempdb_alloc = False
    if wait_resource:
        partes = str(wait_resource).split(":")
        es_tempdb_alloc = len(partes) >= 3 and partes[0].strip() == "2"
    if not es_tempdb_alloc:
        return None
    return _regla(
        "R4",
        "Espera PAGELATCH sobre páginas de asignación de tempdb (patrón 2:1:x).",
        "Contención de asignación en tempdb (PFS/GAM/SGAM).",
        None,
        "N/A (evento suficiente por sí solo según Microsoft).",
        ["Igualar archivos de datos de tempdb al número de cores físicos."],
        "Microsoft Learn: Recommendations to Reduce Allocation Contention",
    )


def regla_r5(wt, met, umbrales):
    if not wt or wt.upper() != "RESOURCE_SEMAPHORE":
        return None
    corrob, det = _corr_memoria(met, umbrales)
    return _regla(
        "R5",
        "RESOURCE_SEMAPHORE: espera por concesión de memoria para operaciones de SQL.",
        "Presión severa de memoria RAM / Buffer Pool insuficientes.",
        corrob, det,
        _apoyo([
            "Revisar sys.dm_exec_query_memory_grants para identificar "
            "consultas con memory grants excesivos."
        ], det, "Corroboración de memoria: "),
        "Microsoft Learn: Troubleshoot Slow Performance Caused by Memory Grants",
    )


def regla_r6(wt):
    if not wt or wt.upper() != "ASYNC_NETWORK_IO":
        return None
    return _regla(
        "R6",
        "ASYNC_NETWORK_IO: el motor espera que el cliente procese los datos enviados.",
        "Aplicación cliente lenta consumiendo los resultados.",
        None,
        "N/A (evento suficiente por sí solo según Microsoft).",
        ["Revisar desempeño de la aplicación cliente y red."],
        "Microsoft Learn: Troubleshoot Slow Queries Resulting from ASYNC_NETWORK_IO",
    )


def regla_r7(command, wait_type, logical_reads, historial_comando, met):
    if not command or es_relevante(wait_type) or logical_reads is None:
        return None
    if historial_comando is None or historial_comando <= 0:
        return None
    if logical_reads < historial_comando * (1 + UMBRAL_DESVIO_LOGICAL_READS):
        return None
    corrob, det = _corr_compilaciones(met)
    return _regla(
        "R7",
        f"Ejecución intensiva sin espera con lecturas lógicas muy superiores "
        f"al histórico ({historial_comando:.0f}).",
        "Plan de ejecución subóptimo o carencia de índices adecuados.",
        corrob, det,
        _apoyo([
            "Analizar el plan de ejecución y estadísticas de la consulta."
        ], det, "Corroboración de compilaciones: "),
        "Microsoft Learn: Troubleshoot Slow-Running Queries in SQL Server",
    )


# ==========================================
# Evaluación
# ==========================================
def evaluar(eventos, met=None, umbrales=None):
    """Evalúa eventos crudos y devuelve las detecciones.

    met son las métricas del nodo de la ventana (features del detector);
    umbrales es un baseline opcional {metrica: (p90, p99)}.
    """
    detecciones = []
    historial = {}

    for crudo in eventos or []:
        ev = normalizar_evento(crudo)
        en = ev["event_name"]
        if en not in ("sql_batch_completed", "wait_info", "wait_completed",
                      "rpc_completed", "blocked_process_report"):
            continue

        wt = ev.get("wait_type") or None
        duration = ev.get("duration") or 0.0
        cpu = ev.get("cpu_time")
        signal = ev.get("signal_wait_time_ms")
        logical_reads = ev.get("logical_reads")
        blocking = ev.get("blocking_session_id")
        wait_resource = ev.get("wait_resource")

        wt_relevante = bool(wt and es_relevante(wt))
        w_eff = wt if wt_relevante else None

        reglas = [r for r in (
            regla_r1(w_eff, duration, met, umbrales),
            regla_r2(w_eff, blocking, met, umbrales),
            regla_r3(w_eff, cpu, duration, signal, met, umbrales),
            regla_r4(w_eff, wait_resource),
            regla_r5(w_eff, met, umbrales),
            regla_r6(w_eff),
        ) if r]

        cmd = ev.get("command")
        if not wt_relevante:
            r7 = regla_r7(cmd, wt, logical_reads, historial.get(cmd), met)
            if r7:
                reglas.append(r7)

        # Historial suavizado por comando (para R7)
        if en == "sql_batch_completed" and cmd:
            historial[cmd] = (
                0.8 * historial.get(cmd, logical_reads) + 0.2 * logical_reads
                if cmd in historial else logical_reads
            )

        for regla in reglas:
            fila = dict(regla)
            fila["evidencia"] = {k: ev.get(k) for k in _EVIDENCIA}
            detecciones.append(fila)

    return detecciones


def resumen(detecciones, maximo=4):
    """Titular corto de las reglas disparadas: R1 (I/O fisico), R3 (CPU)."""
    vistas = []
    for d in detecciones or []:
        r = d.get("regla")
        if r and r not in vistas:
            vistas.append(r)
    return ", ".join(f"{r} ({ETIQUETA.get(r, '')})" for r in vistas[:maximo])