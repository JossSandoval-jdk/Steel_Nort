"""
config.py
=========

Configuración central de la fase de PREPARACIÓN DE DATOS (CRISP-DM)
para la detección de anomalías de rendimiento OLTP de SteelNort.

La preparación trabaja con cargas/corridas independientes.

Cada carga contiene sus propios archivos de captura:

    carga_001/
        metrics.log
        events.log
        sqlserver_logs.log

    carga_002/
        metrics.log
        events.log
        sqlserver_logs.log

Este archivo SOLO define:
    - Rutas
    - Nombres de archivos
    - Variables canónicas
    - Variables principales para el modelo
    - Variables de diagnóstico
    - Variables redundantes
    - Variables que requieren corrección
    - Reglas generales de preparación

NO se etiquetan anomalías aquí.
NO se define una carga normal fija.
NO se define una carga específica a procesar.
"""

import os

from pathlib import Path

BASE_PROYECTO = Path(__file__).resolve().parent

_OUTPUT_PROYECTO = (
    Path(__file__).resolve().parents[3]
    / "training" / "output"
)

OUTPUT_BASE_DIR = Path(
    os.getenv(
        "STEELNORT_OUTPUT_DIR",
        _OUTPUT_PROYECTO
    )
)

DIR_DATASETS = OUTPUT_BASE_DIR / "datasets"
DIR_INVENTARIO = OUTPUT_BASE_DIR / "inventario"
DIR_LIMPIO = OUTPUT_BASE_DIR / "limpio"
DIR_INTEGRADO = OUTPUT_BASE_DIR / "integrado"

DIR_BASELINE = OUTPUT_BASE_DIR / "baseline"
DIR_ANOMALIAS = OUTPUT_BASE_DIR / "anomalias"

DIRS_ARTEFACTO = (
    {d.name for d in (DIR_DATASETS, DIR_INVENTARIO, DIR_LIMPIO, DIR_INTEGRADO)}
    | {"modelado"}
)

def ruta_corrida(raiz, corrida):
    """Ruta de la carpeta de una corrida (busca en anomalias/,
    baseline/ y por compatibilidad en la raiz)."""
    raiz = Path(raiz) if raiz else OUTPUT_BASE_DIR
    for grupo in ("anomalias", "baseline"):
        p = raiz / grupo / corrida
        if p.is_dir():
            return str(p)
    return str(raiz / corrida)

NOMBRE_ORIGEN = "origen.json"

TIPO_ORIGEN_CONTENEDOR = "contenedor_sql"
TIPO_ORIGEN_LEGADO = "legacy"

MOTOR_SQL_PODMAN = "SQL Server Podman (localhost:1434/SteelNort)"

def leer_origen(ruta_corrida):
    """Metadatos de procedencia de una corrida (origen.json si existe).

    Las corridas capturadas por las herramientas de Fase 2 escriben
    ``origen.json`` con su etiqueta (p. ej. ``contenedor_sql``). Las
    capturas históricas que no lo tienen se clasifican por defecto como
    ``legacy``. Nunca lanza excepción: regresa un dict mínimo."""
    origen = {"origen": TIPO_ORIGEN_LEGADO}
    try:
        import json as _json
        p = Path(ruta_corrida) / NOMBRE_ORIGEN
        if p.is_file():
            with open(p, encoding="utf-8") as f:
                origen.update(_json.load(f))
    except Exception:
        pass
    return origen

def escribir_origen(ruta_corrida, tipo=TIPO_ORIGEN_CONTENEDOR, **campos):
    """Escribe origen.json con la etiqueta de procedencia de la corrida."""
    import json as _json
    ruta = Path(ruta_corrida)
    ruta.mkdir(parents=True, exist_ok=True)
    origen = {"origen": tipo}
    origen.update(campos)
    p = ruta / NOMBRE_ORIGEN
    with open(p, "w", encoding="utf-8") as f:
        _json.dump(origen, f, ensure_ascii=False, indent=2)
    return str(p)

def _subcarpetas_con_logs(carpeta):
    """Subcarpetas de 'carpeta' que contienen al menos un log de entrada."""
    if not os.path.isdir(carpeta):
        return []
    return [
        d for d in sorted(os.listdir(carpeta))
        if os.path.isdir(os.path.join(carpeta, d))
        and any(
            os.path.isfile(os.path.join(carpeta, d, f))
            for f in ARCHIVOS_ENTRADA
        )
    ]

def descubrir_corridas(raiz=None):

    raiz = Path(raiz) if raiz else OUTPUT_BASE_DIR
    corridas = {}

    def _marcar(carpeta, grupo, prioridad):
        for d in _subcarpetas_con_logs(carpeta):
            corridas.setdefault(
                d,
                {"grupo": grupo, "prioridad": prioridad,
                 "ruta": str(Path(carpeta) / d)},
            )

    _marcar(DIR_ANOMALIAS, "anomalias", 1)
    _marcar(DIR_BASELINE, "baseline", 2)

    for d in sorted(os.listdir(raiz)):
        p = raiz / d
        if not p.is_dir():
            continue
        if d in DIRS_ARTEFACTO or d in ("anomalias", "baseline"):
            continue
        if _subcarpetas_con_logs(p):
            _marcar(p, "legacy", 3)
        elif any(os.path.isfile(p / f) for f in ARCHIVOS_ENTRADA):
            corridas.setdefault(
                d, {"grupo": "raiz", "prioridad": 4, "ruta": str(p)})

    for info in corridas.values():
        info.pop("prioridad", None)
    return corridas

ARCHIVO_INVENTARIO = "inventario_corridas.csv"

ARCHIVO_VARIABLES = "variables_seleccionadas.csv"

ARCHIVO_DATASET_INTEGRADO = "dataset_steelnort_preparado.csv"

ARCHIVO_METADATA = "metadata_transformaciones.json"

ARCHIVO_REPORTE_CALIDAD = "reporte_calidad_datos.csv"

ARCHIVO_DATASET_PRINCIPALES = "dataset_carga_principales.csv"

ARCHIVO_DATASET_EVENTOS = "dataset_eventos.csv"

ARCHIVO_DATASET_LOGS = "dataset_logs.csv"

NOMBRE_METRICAS_LIMPIO = "metricas_limpio.csv"

NOMBRE_EVENTS_LIMPIO = "eventos_limpio.csv"

NOMBRE_SQLSERVER_LOGS_LIMPIO = "sqlserver_logs_limpio.csv"

NOMBRE_EVENTOS_PREPARADOS = "eventos_preparados.csv"

NOMBRE_LOGS_PREPARADOS = "logs_preparados.csv"

NOMBRE_TRANSFORMADO = "datos_transformados.csv"

"""
Cada carga/corrida debe contener únicamente estos archivos.

Ejemplo:

carga_001/
    metrics.log
    events.log
    sqlserver_logs.log
"""

NOMBRE_METRICAS = "metrics.log"

NOMBRE_EVENTS = "events.log"

NOMBRE_SQLSERVER_LOGS = "sqlserver_logs.log"

ARCHIVOS_ENTRADA = [
    NOMBRE_METRICAS,
    NOMBRE_EVENTS,
    NOMBRE_SQLSERVER_LOGS,
]

FORMATO_INTERMEDIO = "csv"

ENCODING = "utf-8"

SEPARADOR_CSV = ","

UMBRAL_NAV = 50.0

MIN_UNICOS = 2

FEATURES_SISTEMA = [
    {
        "columna": "cpu_usr",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de CPU utilizado por procesos de usuario",
    },
    {
        "columna": "cpu_sys",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de CPU utilizado por procesos del sistema",
    },
    {
        "columna": "cpu_idl",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de CPU inactiva",
    },
    {
        "columna": "cpu_wai",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de CPU esperando operaciones de E/S",
    },
    {
        "columna": "cpu_stl",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de CPU en espera por virtualización",
    },
    {
        "columna": "memory_percent",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Porcentaje de memoria utilizada",
    },
    {
        "columna": "memory_used_mb",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Memoria utilizada en MB",
    },
    {
        "columna": "memory_available_mb",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Memoria disponible en MB",
    },
    {
        "columna": "disk_read_per_sec",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Lecturas de disco por segundo",
    },
    {
        "columna": "disk_write_per_sec",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Escrituras de disco por segundo",
    },
    {
        "columna": "net_send_per_sec",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Bytes enviados por segundo",
    },
    {
        "columna": "net_recv_per_sec",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Bytes recibidos por segundo",
    },
    {
        "columna": "load1",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Carga promedio del sistema durante 1 minuto",
    },
    {
        "columna": "load5",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Carga promedio del sistema durante 5 minutos",
    },
    {
        "columna": "load15",
        "fuente": "metrics",
        "dominio": "sistema",
        "tipo": "numerica",
        "descripcion": "Carga promedio del sistema durante 15 minutos",
    },
]

FEATURES_SESIONES = [
    {
        "columna": "active_sessions",
        "fuente": "metrics",
        "dominio": "sesiones",
        "tipo": "numerica",
        "descripcion": "Número de sesiones activas",
    },
    {
        "columna": "active_requests",
        "fuente": "metrics",
        "dominio": "sesiones",
        "tipo": "numerica",
        "descripcion": "Número de solicitudes activas",
    },
    {
        "columna": "long_queries",
        "fuente": "metrics",
        "dominio": "sesiones",
        "tipo": "numerica",
        "descripcion": "Cantidad de consultas de larga duración",
    },
    {
        "columna": "long_transactions",
        "fuente": "metrics",
        "dominio": "sesiones",
        "tipo": "numerica",
        "descripcion": "Cantidad de transacciones de larga duración",
    },
    {
        "columna": "idle_sessions",
        "fuente": "metrics",
        "dominio": "sesiones",
        "tipo": "numerica",
        "descripcion": "Sesiones inactivas",
    },
]

FEATURES_LOCKS = [
    {
        "columna": "lock_waits",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Cantidad de esperas por bloqueos",
    },
    {
        "columna": "total_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Cantidad total de bloqueos",
    },
    {
        "columna": "deadlocks_per_sec",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Deadlocks por segundo",
    },
    {
        "columna": "venta_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a venta",
    },
    {
        "columna": "detalle_venta_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a detalle de venta",
    },
    {
        "columna": "inventario_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a inventario",
    },
    {
        "columna": "kardex_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a kardex",
    },
    {
        "columna": "caja_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a caja",
    },
    {
        "columna": "movimiento_caja_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a movimientos de caja",
    },
    {
        "columna": "auditoria_locks",
        "fuente": "metrics",
        "dominio": "bloqueos",
        "tipo": "numerica",
        "descripcion": "Bloqueos asociados a auditoría",
    },
]

FEATURES_BUFFER = [
    {
        "columna": "transactions_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Transacciones por segundo",
    },
    {
        "columna": "total_reads",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Lecturas totales",
    },
    {
        "columna": "total_writes",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Escrituras totales",
    },
    {
        "columna": "page_life_expectancy",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Page Life Expectancy",
    },
    {
        "columna": "buffer_cache_hit_ratio",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Ratio de aciertos de caché del buffer",
    },
    {
        "columna": "page_reads_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Lecturas de páginas por segundo",
    },
    {
        "columna": "page_writes_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Escrituras de páginas por segundo",
    },
    {
        "columna": "rollbacks_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Rollbacks por segundo",
    },
    {
        "columna": "batch_requests_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Solicitudes batch por segundo",
    },
    {
        "columna": "sql_compilations_per_sec",
        "fuente": "metrics",
        "dominio": "sqlserver",
        "tipo": "numerica",
        "descripcion": "Compilaciones SQL por segundo",
    },
]

FEATURES_API = [
    {
        "columna": "api_status",
        "fuente": "metrics",
        "dominio": "api",
        "tipo": "categorica",
        "descripcion": "Estado de la API",
    },
    {
        "columna": "api_latency_ms",
        "fuente": "metrics",
        "dominio": "api",
        "tipo": "numerica",
        "descripcion": "Latencia de la API en milisegundos",
    },
    {
        "columna": "products_count",
        "fuente": "metrics",
        "dominio": "api",
        "tipo": "numerica",
        "descripcion": "Cantidad de productos procesados",
    },
    {
        "columna": "sales_count",
        "fuente": "metrics",
        "dominio": "api",
        "tipo": "numerica",
        "descripcion": "Cantidad de ventas procesadas",
    },
]

FEATURES_EVENTOS = [
    {
        "columna": "events_login_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos de login",
    },
    {
        "columna": "events_logout_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos de logout",
    },
    {
        "columna": "events_batch_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos batch",
    },
    {
        "columna": "events_lock_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos de bloqueo",
    },
    {
        "columna": "events_wait_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos de espera",
    },
    {
        "columna": "duration_max_ms",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Duración máxima de consultas",
    },
    {
        "columna": "duration_avg_ms",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Duración promedio de consultas",
    },
    {
        "columna": "query_duration_max_ms",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Duración máxima registrada para consultas",
    },
    {
        "columna": "query_duration_avg_ms",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Duración promedio registrada para consultas",
    },
    {
        "columna": "cpu_time_sum_ms",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Tiempo total de CPU utilizado",
    },
    {
        "columna": "logical_reads_sum",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Lecturas lógicas acumuladas",
    },
    {
        "columna": "writes_sum",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Escrituras acumuladas",
    },
    {
        "columna": "wait_lck_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Esperas asociadas a locks",
    },
    {
        "columna": "wait_io_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Esperas asociadas a operaciones de E/S",
    },
    {
        "columna": "wait_log_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Esperas asociadas al log",
    },
    {
        "columna": "distinct_sessions_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de sesiones distintas",
    },
    {
        "columna": "cpu_total",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "CPU total utilizada",
    },
    {
        "columna": "query_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de consultas",
    },
    {
        "columna": "wait_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de esperas",
    },
    {
        "columna": "lock_event_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de eventos de bloqueo",
    },
    {
        "columna": "error_count",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Cantidad de errores registrados",
    },
    {
        "columna": "requests_per_session",
        "fuente": "events",
        "dominio": "eventos",
        "tipo": "numerica",
        "descripcion": "Solicitudes promedio por sesión",
    },
]

FEATURES_SETTINGS = [
    {
        "columna": "max_server_memory",
        "fuente": "metrics",
        "dominio": "configuracion",
        "tipo": "numerica",
        "descripcion": "Memoria máxima configurada para SQL Server",
    },
    {
        "columna": "user_connections_setting",
        "fuente": "metrics",
        "dominio": "configuracion",
        "tipo": "numerica",
        "descripcion": "Máximo de conexiones de usuario configuradas",
    },
    {
        "columna": "cost_threshold",
        "fuente": "metrics",
        "dominio": "configuracion",
        "tipo": "numerica",
        "descripcion": "Cost Threshold for Parallelism",
    },
]

FEATURES_LOGS = [
    {
        "columna": "log_error_count",
        "fuente": "sqlserver_logs",
        "dominio": "logs",
        "tipo": "numerica",
        "descripcion": "Cantidad de errores registrados en SQL Server",
    },
    {
        "columna": "log_warning_count",
        "fuente": "sqlserver_logs",
        "dominio": "logs",
        "tipo": "numerica",
        "descripcion": "Cantidad de advertencias registradas",
    },
    {
        "columna": "log_fatal_count",
        "fuente": "sqlserver_logs",
        "dominio": "logs",
        "tipo": "numerica",
        "descripcion": "Cantidad de errores críticos registrados",
    },
]

COLUMNA_TEXTO = {
    "columna": "sql_text",
    "fuente": "derivada",
    "dominio": "texto",
    "tipo": "texto",
    "descripcion": "SQL de la consulta más lenta",
}

"""
Estas variables pueden conservarse durante la preparación
para fines de diagnóstico, pero no son necesarias como
variables principales del modelo.

NOTA DE ALINEACIÓN: esta lista es SOLO de clasificación diagnóstica
(puebla variables_seleccionadas.csv). La poda operativa EFECTIVA del
modelo de producción está definida en modeling/config.VARIABLES_MODELO
(19 variables); no modificar esta lista sin revisar esa referencia.
"""

VARIABLES_REDUNDANTES = [
    "cpu_idl",
    "memory_used_mb",
    "memory_available_mb",
    "load5",
    "load15",
    "idle_sessions",
    "cpu_total",
    "requests_per_session",
    "query_duration_max_ms",
    "query_duration_avg_ms",
]

"""
Estas métricas son contadores y requieren cálculo correcto
de delta por intervalo antes de utilizarse directamente
como variables de tasa.
"""

VARIABLES_REQUIEREN_CORRECCION = [
    "page_reads_per_sec",
    "page_writes_per_sec",
    "rollbacks_per_sec",
    "batch_requests_per_sec",
    "sql_compilations_per_sec",
]

"""
buffer_cache_hit_ratio no debe utilizarse actualmente
porque el colector registra el cntr_value sin disponer
del contador base necesario para calcular correctamente
el porcentaje.
"""

EXCLUIR_MEDICION_CORRUPTA = [
    "buffer_cache_hit_ratio",
]

"""
Winsorización: recorte de colas extremas POR CORRIDA (03_transformacion).

Colapsa al percentil superior solo los picos aislados (p.ej.
duration_max_ms con mínimos negativos -24ms o picos de 6.2e6 ms) que
ensucian las tasas sin aportar señal. El recorte se calcula con el
percentil 99.5 de la MISMA corrida, así una corrida corta casi no se
modifica y las corridas sanas no se contagian entre sí.
SIN label leakage: solo transforma valores, nunca etiqueta.
"""

COLUMNAS_WINSORIZAR = [
    "duration_avg_ms",
    "duration_max_ms",
    "query_duration_avg_ms",
    "query_duration_max_ms",
    "cpu_time_sum_ms",
    "disk_read_per_sec",
    "disk_write_per_sec",
    "total_reads",
    "total_writes",
    "load1",
]

# Percentil superior del recorte (por corrida). Límite inferior = 0 para
# tasas/duraciones (no pueden ser negativas).
WINSORIZAR_PCT = float(os.getenv("STEELNORT_WINSORIZAR_PCT", "0.995"))
WINSORIZAR_ACTIVO = os.getenv("STEELNORT_WINSORIZAR", "1") == "1"

"""
Imputación de numéricos residuales (04_integracion):

Antes se rellenaba TODO con 0, lo que convertía la primera muestra de cada
tasa (NaN por delta/dt) en "0 actividad" falsa. Ahora se imputa con la
MEDIANA de la propia corrida, y solo se cae a 0 si la corrida entera es
NaN para esa columna.
"""

IMPUTAR_MEDIANA_CORRIDA = os.getenv("STEELNORT_IMPUTAR_MEDIANA", "1") == "1"

"""
Conjunto canónico de 22 variables para el modelo de detección
de anomalías, definido por experta de dominio OLTP (ver
docs/PREPARACION_DATOS_CRISPDM.md). El modelo usa EXACTAMENTE
este set y NADA más.
"""

VARIABLES_PRINCIPALES = [
    "cpu_usr",
    "cpu_sys",
    "cpu_wai",
    "cpu_idl",
    "memory_used_mb",
    "memory_available_mb",
    "page_life_expectancy",
    "disk_read_per_sec",
    "disk_write_per_sec",
    "total_reads",
    "total_writes",
    "active_sessions",
    "active_requests",
    "transactions_per_sec",
    "long_queries",
    "long_transactions",
    "duration_avg_ms",
    "duration_max_ms",
    "cpu_time_sum_ms",
    "api_latency_ms",
    "api_status",
    "load1",
]

"""
Variables del conjunto canónico que aún no tienen datos
capturados (100% vacías) pero SÍ deben conservarse como
columnas para no romper el contrato de las 22 variables.
Quedan en 0 hasta que el colector empiece a poblarlas.
"""

VARIABLES_CONSERVAR_VACIAS = [
    "long_queries",
    "long_transactions",
]

"""
Variables que pueden ayudar a explicar una anomalía,
pero que no necesariamente forman parte del conjunto
principal utilizado por el modelo.
"""

VARIABLES_DIAGNOSTICO = [
    "api_status",

    "products_count",
    "sales_count",

    "events_login_count",
    "events_logout_count",
    "events_batch_count",
    "events_lock_count",
    "events_wait_count",

    "logical_reads_sum",
    "writes_sum",
    "distinct_sessions_count",

    "wait_count",
    "lock_event_count",

    "log_error_count",
    "log_warning_count",
    "log_fatal_count",

    "max_server_memory",
    "user_connections_setting",
    "cost_threshold",

    "venta_locks",
    "detalle_venta_locks",
    "inventario_locks",
    "kardex_locks",
    "caja_locks",
    "movimiento_caja_locks",
    "auditoria_locks",
]

_FEATURES = (
    FEATURES_SISTEMA
    + FEATURES_SESIONES
    + FEATURES_LOCKS
    + FEATURES_BUFFER
    + FEATURES_API
    + FEATURES_EVENTOS
    + FEATURES_SETTINGS
    + FEATURES_LOGS
)

FEATURES_SELECCIONADAS = [
    feature
    for feature in _FEATURES
    if feature["columna"] not in EXCLUIR_MEDICION_CORRUPTA
]

"""
Estas columnas identifican la corrida/carga y permiten
mantener trazabilidad sin formar parte del modelo.
"""

COLUMNAS_CONTEXTO = [
    "run_name",
    "experiment_id",
    "es_carga_normal",
]

def columnas_features():
    """
    Devuelve las columnas de las variables canónicas.
    """
    return [
        feature["columna"]
        for feature in FEATURES_SELECCIONADAS
    ]

def columnas_principales():
    """
    Devuelve las columnas seleccionadas como variables
    principales para el modelo.
    """
    return VARIABLES_PRINCIPALES.copy()

def columnas_contexto():
    """
    Devuelve las columnas utilizadas para identificar
    y contextualizar cada corrida.
    """
    return COLUMNAS_CONTEXTO.copy()
