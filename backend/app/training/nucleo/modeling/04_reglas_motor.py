"""
04_reglas_motor.py
==================

Motor de reglas completo (R1-R7 + R3b) para el DIAGNÓSTICO de causas de
anomalías OLTP en SQL Server, basado en la metodología de Microsoft Learn.

Evidencia doble — EVENTOS + MÉTRICAS:

    - Eventos  : events.log   -> wait_type, duration, cpu_time,
                                  logical_reads, writes, blocking_session_id,
                                  signal_wait_time_ms, wait_resource.
    - Métricas : metrics.log  -> contadores del SO y de SQL Server
                                  (cpu_usr, cpu_sys, disk_*, lock_waits,
                                  page_life_expectancy, buffer_cache_hit_ratio,
                                  batch_requests_per_sec, ...).

Para cada evento se adjunta la métrica muestreada en el MISMO instante
(cruce por timestamp, asof nearest). Cada regla se dispara por el EVENTO y se
CORROBORA con las métricas: si el contador complementario está en pico
(>= p90 / p99 del propio baseline de la corrida) la evidencia es fuerte;
si no, la regla queda marcada como "solo evento / sin confirmación métrica".

Reglas:
    R1   I/O físico          PAGEIOLATCH_* WRITELOG IO_COMPLETION BACKUPIO
                             + duration alto
        -> corrobora: Physical Disk (disk_read/write_per_sec, page_*).
    R2   Bloqueo/contención  LCK_M_*
        -> corrobora: SQLServer:Locks Lock Wait Time / Number of Deadlocks
           (lock_waits, deadlocks_per_sec).
    R3   Presión de CPU      SOS_SCHEDULER_YIELD o cpu_time ≈ duration
        -> corrobora: Processor: % Processor Time (Microsoft: 80-90%
           sostenido = señalar más CPU).
    R3b  CPU de SO por I/O   cpu_time alto sin wait claro, cpu_sys alto
                             + contadores de disco altos a la vez
        -> el gasto de CPU es del sistema operativo procesando I/O.
    R4   Contención tempdb   PAGELATCH_* sobre recurso 2:1:x
        -> evento suficiente por sí solo (Microsoft), sin métrica.
    R5   Presión de memoria  RESOURCE_SEMAPHORE
        -> corrobora: Buffer cache hit ratio (<90 deseable según MS) y
           Page life expectancy (más alto/creciente es mejor).
    R6   Aplicación lenta    ASYNC_NETWORK_IO
        -> evento suficiente por sí solo (Microsoft), sin métrica.
    R7   Plan subóptimo      sin wait dominante + logical_reads >> histórico
        -> corrobora: SQL Statistics Batch Requests/sec vs SQL
           Compilations/sec (cruce SIN umbral oficial publicado).

Salidas (en <OUTPUT>/modelado/reglas_motor/):
    detecciones_reglas.csv      — cada evento con su corroboración métrica
    resumen_reglas.csv          — conteo por regla y por corrida
    diagnostico_reglas.json     — resumen con corroboración para operación
"""

import glob
import json
import os
import re

import numpy as np
import pandas as pd

import config


# ============================================================
# LOG
# ============================================================

def log(msg):
    print(f"[REGLAS-MOTOR] {msg}", flush=True)


# ============================================================
# WAIT TYPES DE FONDO (no representan un problema de la carga OLTP)
# ============================================================

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
    """True si el wait_type puede disparar una regla (no es de fondo)."""
    if not wait_type:
        return False
    if wait_type.upper() in FONDO:
        return False
    return True


# ============================================================
# MÉTRICAS (metrics.log)
# ============================================================

# Columnas de métricas que interesan para corroborar cada regla.
METRICAS_R1 = ["disk_read_per_sec", "disk_write_per_sec",
               "page_reads_per_sec", "page_writes_per_sec",
               "total_reads_delta", "total_writes_delta"]
METRICAS_R2 = ["lock_waits", "deadlocks_per_sec", "total_locks"]
METRICAS_R3 = ["cpu_usr", "cpu_sys"]
METRICAS_R3B = ["cpu_sys", "cpu_usr"]
METRICAS_R5 = ["buffer_cache_hit_ratio", "page_life_expectancy"]
METRICAS_R7 = ["batch_requests_per_sec", "sql_compilations_per_sec"]


def leer_metricas(ruta):
    """Lee metrics.log (timestamp, metric, value) y devuelve un DataFrame
    ancho (index=timestamp, columnas=métricas) con las tasas de los
    contadores acumulativos (total_reads_delta, total_writes_delta)."""
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

    # Contadores acumulativos -> tasa por muestra (delta/dt apróx.).
    for col in ("total_reads", "total_writes"):
        if col in ancho.columns:
            ancho[col + "_delta"] = ancho[col].diff().fillna(0.0)

    return ancho


def umbrales_por_corrida(df_m):
    """p90/p99 de cada métrica dentro de la corrida (baseline interno).
    Permite clasificar cada observación como normal / alto / pico."""
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
    """Adjunta a cada evento las métricas muestreadas en el mismo instante
    (asof nearest). Devuelve los mismos eventos aumentados con claves
    m_<metrica>.
    """
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
        # ev_i trae _ts/_orden; descartarlos
        ev_i.pop("_ts", None)
        # pandas NaN en campos objeto -> None (JSON original sin valor)
        for k, v in ev_i.items():
            if isinstance(v, float) and pd.isna(v):
                ev_i[k] = None
        for col in cols_m:
            v = fila.get(col)
            ev_i["m_" + col] = None if (isinstance(v, float) and pd.isna(v)) else v
        eventos_finales.append(ev_i)

    return eventos_finales


def v_met(met, nombre):
    """Valor numérico de una métrica adjunta (None si no disponible)."""
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
    """Clasifica una observación frente al baseline interno (p90/p99)."""
    if valor is None:
        return None
    tupla = umbrales.get(nombre)
    if not tupla or not np.isfinite(tupla[0]):
        return "normal"
    p90, p99 = tupla
    # Columna sin variación (p90==p99): no hay baseline de pico; cualquier
    # valor en el mismo nivel no es un pico.
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
    """R1: confirma el evento de I/O con contadores de disco."""
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
    """R2: confirma el bloqueo con contadores de locks/waits."""
    evidencias, estados = [], []
    for nombre in METRICAS_R2:
        v = v_met(met, nombre)
        if v is None:
            continue
        est = estado_gauge(v, umbrales, nombre)
        evidencias.append(texto_gauge(nombre, v, est))
        estados.append(est)
    if any(s in ("pico", "alto") for s in estados) or \
            any(v_met(met, "lock_waits") for _ in [0] if v_met(met, "lock_waits")):
        return "confirmado", "; ".join(evidencias)
    if evidencias:
        return "sin_pico", "; ".join(evidencias)
    return None, None


def corroboracion_cpu(met):
    """R3: % Processor Time según Microsoft (80-90% sostenido)."""
    cpu = v_met(met, "cpu_usr")
    if cpu is None:
        return None, None
    if cpu >= config.UMBRAL_CPU_CRITICO_MS:
        return ("confirmado",
                f"cpu_usr={cpu:.1f}% (>= {config.UMBRAL_CPU_CRITICO_MS:.0f}%, "
                f"crítico según Microsoft)")
    if cpu >= config.UMBRAL_CPU_ALTO_MS:
        return ("confirmado",
                f"cpu_usr={cpu:.1f}% (>= {config.UMBRAL_CPU_ALTO_MS:.0f}%, "
                f"alto sostenido según Microsoft)")
    return "sin_pico", f"cpu_usr={cpu:.1f}% (< {config.UMBRAL_CPU_ALTO_MS:.0f}%)"


def corroboracion_cpu_so(met, umbrales):
    """R3b: % Privileged Time + disco altos a la vez => CPU del SO por I/O."""
    cpu_sys = v_met(met, "cpu_sys")
    if cpu_sys is None:
        return None, None
    est_sys = estado_gauge(cpu_sys, umbrales, "cpu_sys")
    discos = [nombre for nombre in METRICAS_R1
              if v_met(met, nombre) is not None
              and estado_gauge(v_met(met, nombre), umbrales, nombre)
              in ("pico", "alto")]
    if est_sys in ("pico", "alto") and discos:
        return ("confirmado",
                f"cpu_sys={cpu_sys:.1f}% ({est_sys}) + disco pico: "
                + ", ".join(discos))
    return None, None


def corroboracion_memoria(met, umbrales):
    """R5: buffer cache hit ratio (<90 deseable MS) + PLE (creciente mejor)."""
    evidencias = []
    bch = v_met(met, "buffer_cache_hit_ratio")
    if bch is not None:
        if bch < config.BUFFER_CACHE_HIT_RATIO_DESEABLE:
            evidencias.append(
                f"buffer_cache_hit_ratio={bch:.1f} "
                f"(< {config.BUFFER_CACHE_HIT_RATIO_DESEABLE:.0f}, presión "
                f"según Microsoft)")
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
    """R7: Batch Requests/sec vs SQL Compilations/sec (sin umbral oficial)."""
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


# ============================================================
# DEFINICIÓN DE REGLAS (evento + corroboración métrica)
# ============================================================

REGLA_GENERICA = {
    "fuente": "Microsoft Learn: Troubleshoot SQL Server Performance",
    "url": "https://learn.microsoft.com/en-us/troubleshoot/sql/database-engine/performance/large-ram-troubleshoot",
}


def regla_r1(wt, duration, met, umbrales):
    """
    R1: I/O físico. wait_type del grupo de I/O de página/log con duración
    alta. Se corrobora con contadores de disco en pico.
    """
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
        "Revisar sys.dm_io_virtual_file_stats para ver lecturas/escrituras"
        " por archivo y sus tiempos.",
        "Revisar contadores de disco del SO (LogicalDisk: Avg. Disk"
        " sec/Read, Write, Queue Length).",
        "Identificar las consultas con mayor logical_reads/writes que"
        " disparan el I/O.",
    ]
    if det:
        apoyo.insert(0, "Corroboración de métricas (pico frente a baseline"
                        " interno de la corrida): " + det + ".")

    return {
        "regla": "R1",
        "detonante": (
            "Espera de I/O de página/log (PAGEIOLATCH_*/WRITELOG/"
            "IO_COMPLETION/BACKUPIO) con duración alta."
        ),
        "diagnostico": (
            "Cuello de botella de I/O físico: si el evento coincide con "
            "picos en los contadores de disco, el subsistema de "
            "almacenamiento (no la consulta) es la causa; el motor pidió "
            "una página o está confirmando una escritura en el log y el "
            "disco tarda en responder (disco lento o log saturado)."
        ),
        "corroborado": corrob,
        "metricas": det,
        "apoyo": apoyo,
        "fuente": (
            "Troubleshoot Slow SQL Server Performance Caused by I/O Issues "
            "— learn.microsoft.com/en-us/troubleshoot/sql/database-engine/"
            "performance/troubleshoot-sql-io-performance"
        ),
    }


def regla_r2(wt, blocking, met, umbrales):
    """R2: Bloqueo/contención. LCK_M_* + contadores de locks en pico."""
    if not wt:
        return None
    if not wt.upper().startswith("LCK_M_"):
        return None

    corrob, det = corroboracion_locks(met, umbrales)
    apoyo = [
        "Ubicar la sesión bloqueadora mediante blocking_session_id en "
        "sys.dm_exec_requests"
        + (f" (bloqueador = {blocking})" if blocking else
           " (no se registró blocking_session_id)")
        + ".",
        "Revisar el nivel de aislamiento y la duración de las transacciones"
        " que mantienen el lock.",
        "Revisar wait_resource para identificar el recurso contendido.",
    ]
    if det:
        apoyo.insert(0, "Corroboración de métricas: " + det + ".")

    return {
        "regla": "R2",
        "detonante": (
            "Espera de lock (LCK_M_*): una sesión mantiene un lock "
            "(transacción activa/larga) y otra necesita el mismo recurso."
        ),
        "diagnostico": (
            "Bloqueo o contención entre sesiones: problema de "
            "CONCURRENCIA, no de recursos físicos."
        ),
        "corroborado": corrob,
        "metricas": det,
        "apoyo": apoyo,
        "fuente": (
            "Understand and Resolve SQL Server Blocking Problems — "
            "learn.microsoft.com/en-us/troubleshoot/sql/database-engine/"
            "performance/understand-resolve-blocking"
        ),
    }


def regla_r3(wt, cpu, duration, signal, met):
    """
    R3: Presión de CPU. SOS_SCHEDULER_YIELD, o cpu_time ≈ duration.
    Se corrobora con % Processor Time (Microsoft: 80-90% sostenido).
    """
    cpu_close = False
    if (
        duration and cpu is not None
        and duration > config.UMBRAL_DURACION_LENTA_MS
        and cpu >= config.UMBRAL_DURACION_LENTA_MS * 0.5
    ):
        cpu_close = cpu >= duration * (1 - config.TOLERANCIA_CPU_DURATION)

    if not ((wt and wt.upper() == "SOS_SCHEDULER_YIELD") or cpu_close):
        return None

    corrob, det = corroboracion_cpu(met)
    apoyo = [
        "Revisar señal vs recurso: "
        + (f"signal_wait_time_ms={signal} ms (espera de CPU) frente a "
           "resource_wait_time_ms (espera de recurso)."
           if signal and signal > 0
           else "sin signal_wait_time_ms disponible; se asume CPU por "
                "cpu_time≈duration."),
        "Buscar índices faltantes (sys.dm_db_missing_index_details).",
        "Actualizar estadísticas y analizar el plan de ejecución de las "
        "consultas afectadas.",
    ]
    if det:
        apoyo.insert(0, "Corroboración de métricas: " + det + ".")

    return {
        "regla": "R3",
        "detonante": (
            "Espera de planificador (SOS_SCHEDULER_YIELD) o cpu_time muy "
            "cercano a duration (la consulta casi no espera y consume CPU "
            "todo el tiempo)."
        ),
        "diagnostico": (
            "Presión real de CPU (no solo un pico puntual de una consulta):"
            " planes ineficientes, estadísticas desactualizadas, índices "
            "faltantes o parameter sniffing."
        ),
        "corroborado": corrob,
        "metricas": det,
        "apoyo": apoyo,
        "fuente": (
            "Troubleshoot High CPU Usage Issues in SQL Server — "
            "learn.microsoft.com/en-us/troubleshoot/sql/database-engine/"
            "performance/troubleshoot-high-cpu-usage-issues"
        ),
    }


def regla_r3b(cpu, duration, met, umbrales):
    """
    R3b: cpu_time alto sin wait_type claro + % Privileged Time alto y
    contadores de disco altos a la vez => el gasto de CPU es del SISTEMA
    OPERATIVO procesando I/O (no de SQL Server haciendo lógica).
    """
    if duration and cpu and duration > config.UMBRAL_DURACION_LENTA_MS:
        corrob, det = corroboracion_cpu_so(met, umbrales)
        if not corrob:
            return None
        return {
            "regla": "R3b",
            "detonante": (
                "cpu_time alto sin wait_type claro de CPU, con cpu_sys "
                "(% Privileged Time) alto y contadores de disco altos en "
                "el mismo instante."
            ),
            "diagnostico": (
                "El gasto de CPU es del sistema operativo procesando I/O "
                "(drivers/controlador de disco), no de SQL Server "
                "procesando lógica de negocio."
            ),
            "corroborado": corrob,
            "metricas": det,
            "apoyo": [
                "Revisar drivers/controladores del subsistema de disco "
                "y el % Privileged Time sostenido.",
                "Microsoft: si % Privileged Time es consistentemente alto "
                "cuando el disco físico también lo está, evaluar un "
                "subsistema de disco más eficiente.",
            ],
            "fuente": (
                "Monitor CPU Usage — learn.microsoft.com/en-us/troubleshoot/"
                "sql/database-engine/performance/monitor-cpu-usage"
            ),
        }
    return None


def regla_r4(wt, wait_resource):
    """R4: Contención de asignación en tempdb. PAGELATCH_* 2:1:x.
    Evento suficiente por sí solo (Microsoft), sin métrica complementaria."""
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
            "detonante": (
                "Espera PAGELATCH_SH/EX/UP sobre páginas de asignación "
                "(tempdb, patrón 2:1:x) por creación/destrucción simultánea "
                "de tablas temporales."
            ),
            "diagnostico": (
                "Contención de asignación en tempdb bajo carga concurrente "
                "alta (contienda por páginas PFS/GAM/SGAM)."
            ),
            "corroborado": None,
            "metricas": "N/A (evento suficiente por sí solo según Microsoft).",
            "apoyo": [
                "Recurso detectado: "
                + (str(wait_resource) if es_tempdb_alloc else
                   "(recurso no capturado o no 2:1:x)")
                + ".",
                "Igualar el nº de archivos de datos de tempdb al nº de "
                "núcleos de la máquina.",
                "Revisar el uso de tablas temporales en la carga.",
            ],
            "fuente": (
                "Recommendations to Reduce Allocation Contention — "
                "learn.microsoft.com/en-us/troubleshoot/sql/database-engine/"
                "performance/recommendations-reduce-allocation-contention"
            ),
        }
    return None


def regla_r5(wt, met, umbrales):
    """
    R5: Presión de memoria (RESOURCE_SEMAPHORE). Se corrobora con
    Buffer cache hit ratio (<90 deseable MS) y Page life expectancy.
    """
    if not wt:
        return None
    if wt.upper() != "RESOURCE_SEMAPHORE":
        return None

    corrob, det = corroboracion_memoria(met, umbrales)
    apoyo = [
        "Revisar planes con memory grants grandes "
        "(sys.dm_exec_query_memory_grants).",
        "Optimizar joins/sorts costosos.",
        "Evaluar si hace falta más memoria en el servidor.",
    ]
    if det:
        apoyo.insert(0, "Corroboración de métricas: " + det + ".")

    return {
        "regla": "R5",
        "detonante": (
            "RESOURCE_SEMAPHORE: una consulta pide memoria para "
            "ordenar/unir/agregar y no hay suficiente memoria disponible "
            "por otras consultas concurrentes."
        ),
        "diagnostico": (
            "Presión de memoria: buffer pool insuficiente para la carga de "
            "consultas concurrentes, con memory grants muy grandes."
        ),
        "corroborado": corrob,
        "metricas": det,
        "apoyo": apoyo,
        "fuente": (
            "Troubleshoot Slow Performance Caused by Memory Grants — "
            "learn.microsoft.com/en-us/troubleshoot/sql/database-engine/"
            "performance/troubleshoot-memory-grant-issues"
        ),
    }


def regla_r6(wt):
    """R6: Aplicación consumidora lenta (ASYNC_NETWORK_IO).
    Evento suficiente por sí solo (Microsoft), sin métrica complementaria."""
    if not wt:
        return None
    if wt.upper() != "ASYNC_NETWORK_IO":
        return None
    return {
        "regla": "R6",
        "detonante": (
            "ASYNC_NETWORK_IO: el motor ya generó el resultado y lo puso "
            "en el buffer de salida, pero la aplicación cliente no lo lee "
            "lo bastante rápido."
        ),
        "diagnostico": (
            "El cuello de botella está en la aplicación cliente, no en el "
            "motor."
        ),
        "corroborado": None,
        "metricas": "N/A (evento suficiente por sí solo según Microsoft).",
        "apoyo": [
            "Revisar la aplicación cliente que consume el result set.",
            "Limitar el tamaño del result set (paginación / TOP).",
        ],
        "fuente": (
            "Troubleshoot Slow Queries Resulting from ASYNC_NETWORK_IO — "
            "learn.microsoft.com/en-us/troubleshoot/sql/database-engine/"
            "performance/troubleshoot-query-async-network-io"
        ),
    }


def regla_r7(command, wait_type, logical_reads, historial, met):
    """
    R7: Plan subóptimo. Sin wait dominante + logical_reads muy por encima
    del historial de esa misma consulta. Se corrobora con Batch Requests/sec
    vs SQL Compilations/sec (cruce sin umbral oficial publicado).
    """
    if not command:
        return None
    if es_relevante(wait_type):
        return None
    if historial is None or historial <= 0:
        return None
    if logical_reads is None:
        return None
    if logical_reads < historial * (1 + config.UMBRAL_DESVIO_LOGICAL_READS):
        return None

    corrob, det = corroboracion_compilaciones(met)
    apoyo = [
        "Analizar el plan de ejecución de la consulta.",
        "Verificar índices y estadísticas.",
    ]
    if det:
        apoyo.insert(
            0, "Corroboración de métricas (sin umbral oficial publicado): "
               + det + ".")

    return {
        "regla": "R7",
        "detonante": (
            "Sin wait_type dominante (consulta ejecutándose) pero "
            f"logical_reads={logical_reads} muy por encima del historial de "
            f"esa consulta ({historial:.0f})."
        ),
        "diagnostico": (
            "La consulta se la pasa ejecutando (no esperando) porque tiene "
            "que escanear muchas más páginas de las necesarias: plan "
            "subóptimo por falta de índice o estadísticas obsoletas; si "
            "además hay muchas recompilaciones (ratio compilaciones/batches "
            "alto) apunta a falta de parametrización."
        ),
        "corroborado": corrob,
        "metricas": det,
        "apoyo": apoyo,
        "fuente": (
            "Troubleshoot Slow-Running Queries in SQL Server — "
            "learn.microsoft.com/en-us/troubleshoot/sql/database-engine/"
            "performance/troubleshoot-slow-running-queries"
        ),
    }


# ============================================================
# LECTURA DE events.log
# ============================================================

def _val(ev, key, default=0):
    """Lee un valor numérico de un evento (None/sin clave → default)."""
    v = ev.get(key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def leer_eventos(ruta):
    """Lee un events.log y devuelve una lista de dicts."""
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


# ============================================================
# AGRUPAR POR CORRIDA, APLICAR REGLAS
# ============================================================

def encontrar_events_log():
    """Busca todos los events.log dentro de la raiz de corridas
    (baseline/ y anomalias/, más legacy en la raiz; excluye carpetas
    que no son corridas)."""
    rutas = {}

    def _barrer(carpeta_grupo):
        for carpeta in os.listdir(carpeta_grupo):
            ruta_carpeta = os.path.join(carpeta_grupo, carpeta)
            if not os.path.isdir(ruta_carpeta):
                continue
            if carpeta.lower() in config.CARPETAS_NO_CORRIDA:
                continue
            ev_file = os.path.join(ruta_carpeta, "events.log")
            if os.path.exists(ev_file):
                rutas[carpeta] = ev_file

    for grupo in ("anomalias", "baseline"):
        ruta_grupo = os.path.join(config.DIR_CORRIDAS, grupo)
        if os.path.isdir(ruta_grupo):
            _barrer(ruta_grupo)

    # Legacy: corridas con events.log directo en la raiz
    for carpeta in os.listdir(config.DIR_CORRIDAS):
        ruta_carpeta = os.path.join(config.DIR_CORRIDAS, carpeta)
        if not os.path.isdir(ruta_carpeta):
            continue
        if carpeta.lower() in config.CARPETAS_NO_CORRIDA or \
                carpeta in ("baseline", "anomalias"):
            continue
        ev_file = os.path.join(ruta_carpeta, "events.log")
        if os.path.exists(ev_file):
            rutas[carpeta] = ev_file

    return rutas


def aplicar_reglas_a_eventos(eventos, df_m, umbrales):
    """
    Recorre los eventos (en orden temporal) y aplica R1-R7+R3b.
    Cada evento ya venía aumentado con sus métricas (m_*).
    R7 necesita un HISTORIAL de logical_reads por command, que se construye
    sobre la marcha (media móvil). Devuelve (detecciones, historial_global).
    """
    detecciones = []
    historial = {}

    for ev in eventos:
        en = ev.get("event_name")
        if en not in ("sql_batch_completed", "wait_info",
                      "blocked_process_report"):
            continue

        wt = ev.get("wait_type") or None

        duration = _val(ev, "duration")
        cpu = _val(ev, "cpu_time", None)
        logical_reads = _val(ev, "logical_reads")
        writes = _val(ev, "writes")
        blocking = ev.get("blocking_session_id")
        wait_resource = ev.get("wait_resource")
        signal = _val(ev, "signal_wait_time_ms", None)

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
            "writes": writes,
            "blocking_session_id": blocking,
            "wait_resource": wait_resource,
            "signal_wait_time_ms": signal,
        }

        r1 = regla_r1(w_eff, duration, ev, umbrales)
        r2 = regla_r2(w_eff, blocking, ev, umbrales)
        r3 = regla_r3(w_eff, cpu, duration, signal, ev)
        r3b = regla_r3b(cpu, duration, ev, umbrales)
        r4 = regla_r4(w_eff, wait_resource)
        r5 = regla_r5(w_eff, ev, umbrales)
        r6 = regla_r6(w_eff)

        reglas = [x for x in (r1, r2, r3, r3b, r4, r5, r6) if x]

        if not wt_relevante:
            hist = historial.get(ev.get("command"))
            r7 = regla_r7(ev.get("command"), wt, logical_reads, hist, ev)
            if r7:
                reglas.append(r7)

        cmd = ev.get("command")
        if en == "sql_batch_completed" and cmd:
            actual = historial.get(cmd)
            if actual is None:
                historial[cmd] = logical_reads
            else:
                historial[cmd] = (actual + logical_reads) / 2.0

        for regla in reglas:
            fila = dict(ocurrencia)
            fila.update(regla)
            detecciones.append(fila)

    return detecciones, historial


# ============================================================
# MAIN
# ============================================================

def main():

    rutas = encontrar_events_log()

    if not rutas:
        log("No se encontraron events.log en "
            f"{config.DIR_CORRIDAS}.")
        return

    log(f"Corridas con events.log: {sorted(rutas)}")

    todas_detecciones = []
    resumen = []

    for run in sorted(rutas):

        eventos = leer_eventos(rutas[run])

        for ev in eventos:
            ev["_run"] = run

        # --- leer y unir métricas del mismo instante ---
        ruta_m = os.path.join(
            os.path.dirname(rutas[run]), "metrics.log")
        df_m = leer_metricas(ruta_m)
        umbrales = umbrales_por_corrida(df_m)
        eventos = unir_metricas(eventos, df_m, umbrales)

        detecciones, historial = aplicar_reglas_a_eventos(
            eventos, df_m, umbrales)

        todas_detecciones.extend(detecciones)

        resumen.append({
            "run_name": run,
            "eventos_leidos": len(eventos),
            "metricas_adjuntas": int(df_m.shape[0]) if df_m is not None else 0,
            "detecciones": len(detecciones),
        })

        log(f"{run}: {len(eventos)} eventos (métricas en {resumen[-1]['metricas_adjuntas']} "
            f"muestras) -> {len(detecciones)} detecciones")

    os.makedirs(config.DIR_REGLAS, exist_ok=True)

    ruta_csv = os.path.join(config.DIR_REGLAS, "detecciones_reglas.csv")

    if todas_detecciones:

        df = pd.DataFrame(todas_detecciones)

        df.to_csv(ruta_csv, index=False, encoding="utf-8-sig")

        log(f"Detecciones guardadas en: {ruta_csv} ({len(df)} filas)")

        ruta_resumen = os.path.join(config.DIR_REGLAS, "resumen_reglas.csv")
        resumen_reglas = (
            df.groupby(["regla", "run_name"])
              .size()
              .reset_index(name="conteo")
        )
        resumen_reglas.to_csv(ruta_resumen, index=False, encoding="utf-8-sig")
        log(f"Resumen por regla en: {ruta_resumen}")

        # Corroboración resumida
        corrob = df.groupby(["regla", "corroborado"]).size().reset_index(
            name="conteo")

        agrupado = {}
        for _, fila in df.iterrows():
            reg = fila["regla"]
            if reg not in agrupado:
                agrupado[reg] = {
                    "diagnostico": fila["diagnostico"],
                    "detonante": fila["detonante"],
                    "fuente": fila["fuente"],
                    "casos": [],
                }
            agrupado[reg]["casos"].append({
                "run": fila["run_name"],
                "timestamp": fila["timestamp"],
                "session_id": fila["session_id"],
                "command": fila["command"],
                "wait_type": fila["wait_type"],
                "duration_ms": fila["duration_ms"],
                "cpu_time_ms": fila["cpu_time_ms"],
                "logical_reads": fila["logical_reads"],
                "blocking_session_id": fila["blocking_session_id"],
                "wait_resource": fila["wait_resource"],
                "signal_wait_time_ms": fila["signal_wait_time_ms"],
                "corroborado": fila.get("corroborado"),
                "metricas": fila.get("metricas"),
            })

        diagnostico = {
            "resumen_por_regla": (
                resumen_reglas.to_dict(orient="records")
            ),
            "corroboracion_por_regla": (
                corrob.to_dict(orient="records")
            ),
            "reglas": {
                k: {
                    "diagnostico": v["diagnostico"],
                    "detonante": v["detonante"],
                    "fuente": v["fuente"],
                    "n_casos": len(v["casos"]),
                }
                for k, v in agrupado.items()
            },
            "casos": {
                k: v["casos"]
                for k, v in agrupado.items()
            },
        }

        ruta_json = os.path.join(config.DIR_REGLAS, "diagnostico_reglas.json")
        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump(diagnostico, f, ensure_ascii=False, indent=2)
        log(f"Diagnóstico en: {ruta_json}")

    else:

        pd.DataFrame(resumen).to_csv(
            os.path.join(config.DIR_REGLAS, "resumen_reglas.csv"),
            index=False, encoding="utf-8-sig",
        )
        log("Sin detecciones: ninguna regla se disparó en los events.log "
            "disponibles.")

    print("\n=== REGLAS DE MOTOR (R1-R7 + R3b) ===")
    print(f"Rutas analizadas: {len(rutas)}")

    for r in resumen:
        print(
            f"  {r['run_name']}: {r['eventos_leidos']} eventos "
            f"(métricas {r['metricas_adjuntas']} muestras) "
            f"-> {r['detecciones']} detecciones"
        )

    if todas_detecciones:
        print("\nConteo por regla:")
        print(
            df.groupby("regla")
              .size()
              .sort_values(ascending=False)
              .to_string()
        )
        print("\nCorroboración métrica por regla:")
        print(
            corrob.to_string(index=False)
        )


if __name__ == "__main__":
    main()