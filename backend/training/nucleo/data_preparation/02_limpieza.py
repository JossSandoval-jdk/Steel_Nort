"""
02_limpieza.py
==============

Paso 2 del Pipeline de Preparación de Datos (CRISP-DM):
Limpieza de Datos.

Procesa cada carga/corrida de manera independiente.

Fuentes de entrada por corrida:

    metrics.log
    events.log
    sqlserver_logs.log

Procesos realizados:
    - Parseo de archivos
    - Conversión de tipos
    - Normalización de timestamps
    - Eliminación/control de duplicados
    - Detección de registros malformados
    - Clasificación de eventos
    - Clasificación de mensajes de SQL Server

Salida:

    output/limpio/<corrida>/

con los archivos CSV correspondientes.

Este paso NO etiqueta anomalías.
"""

import json
import os
import re

import pandas as pd

import config


# ============================================================
# LOG
# ============================================================

def log(msg):
    print(f"[LIMPIEZA] {msg}", flush=True)


# ============================================================
# PARSER DE MÉTRICAS
# ============================================================

_RE_METRICS = re.compile(
    r"^(\S+\s+\S+)\s{2,}(\S+)\s+(\S+)$"
)


def limpiar_metrics(ruta):
    """
    Parseo del archivo metrics.log.

    Formato esperado:

        timestamp    metrica    valor

    Devuelve:
        DataFrame limpio
        Diccionario con estadísticas del proceso
    """

    registros = []

    descartadas = 0
    no_numericas = 0

    with open(
        ruta,
        encoding=config.ENCODING,
        errors="replace"
    ) as f:

        for i, linea in enumerate(f):

            # Saltar cabecera
            if i == 0:
                continue

            linea = linea.strip()

            if not linea:
                continue

            m = _RE_METRICS.match(linea)

            if not m:
                descartadas += 1
                continue

            ts, metrica, valor = m.groups()

            try:
                valor = float(valor)

            except ValueError:
                no_numericas += 1
                continue

            try:
                timestamp = pd.Timestamp(ts)

            except Exception:
                descartadas += 1
                continue

            registros.append(
                (
                    timestamp,
                    metrica,
                    valor
                )
            )

    df = pd.DataFrame(
        registros,
        columns=[
            "timestamp",
            "metrica",
            "valor"
        ]
    )

    return df, {
        "descartadas": descartadas,
        "no_numericas": no_numericas,
    }


# ============================================================
# CLASIFICACIÓN DE EVENTOS
# ============================================================

EVENTOS_SQL_SERVER_INTERNOS = {
    "TASK MANAGER",
    "TRACE QUEUE TASK",
    "SYSTEM_HEALTH_MONITOR",
    "ONDEMAND_TASK_QUEUE",
    "BRKR TASK",
    "CHECKPOINT",
    "HADR_AR_MGR_NOTIFICATION_WORKER",
}


def clasificar_evento(evento):
    """
    Clasifica un evento como:

        SQL_SERVER_INTERNAL
        USER
        UNKNOWN
    """

    command = str(
        evento.get("command") or ""
    ).strip().upper()

    event_name = str(
        evento.get("event_name") or ""
    ).strip().lower()

    # --------------------------------------------------------
    # Eventos internos de SQL Server
    # --------------------------------------------------------

    if command in EVENTOS_SQL_SERVER_INTERNOS:
        return "SQL_SERVER_INTERNAL"

    # --------------------------------------------------------
    # Eventos que no representan una consulta de usuario
    # --------------------------------------------------------

    if event_name in {
        "login",
        "logout",
        "lock_acquired",
        "lock_released",
        "wait_info",
        "xml_deadlock_report",
        "error_reported",
    }:
        return "UNKNOWN"

    # --------------------------------------------------------
    # Consultas SQL de usuario
    # --------------------------------------------------------

    if command.startswith(
        (
            "SELECT",
            "EXECUTE",
            "INSERT",
            "UPDATE",
            "DELETE",
            "MERGE",
            "CALL",
        )
    ):

        database = str(
            evento.get("database_name") or ""
        ).strip().lower()

        if database in {
            "steelnort",
            "",
        }:
            return "USER"

    return "UNKNOWN"


# ============================================================
# PARSER DE EVENTS.LOG
# ============================================================

def limpiar_events(ruta):
    """
    Procesa events.log.

    Cada línea debe contener un objeto JSON.

    Realiza:
        - Validación JSON
        - Detección de duplicados
        - Normalización de timestamp
        - Clasificación del evento
    """

    registros = []

    malformados = 0

    vistos = set()

    duplicados = set()

    with open(
        ruta,
        encoding=config.ENCODING,
        errors="replace"
    ) as f:

        for linea in f:

            linea = linea.strip()

            if not linea:
                continue

            try:
                obj = json.loads(linea)

            except json.JSONDecodeError:
                malformados += 1
                continue

            # ------------------------------------------------
            # Detectar duplicados
            # ------------------------------------------------

            clave = linea

            if clave in vistos:
                duplicados.add(clave)

            vistos.add(clave)

            obj["_linea"] = clave

            registros.append(obj)

    df = pd.DataFrame(registros)

    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

    if not df.empty and "timestamp" in df.columns:

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            errors="coerce"
        )

    # --------------------------------------------------------
    # Clasificación
    # --------------------------------------------------------

    if not df.empty:

        df["process_type"] = df.apply(
            clasificar_evento,
            axis=1
        )

        # Rellenar campos vacíos para evitar NaN
        for col in df.columns:
            if col == "timestamp":
                continue
            if df[col].dtype == "object":
                df[col] = df[col].fillna("")
            else:
                df[col] = df[col].fillna(0)

    return df, {
        "malformados": malformados,
        "duplicados": len(duplicados),
    }


# ============================================================
# PARSER DE SQL SERVER LOGS
# ============================================================

_RE_SQLSERVER_LOG = re.compile(
    r"^(\d{4}-\d{2}-\d{2} "
    r"\d{2}:\d{2}:\d{2}\.\d+)"
    r"\s+(\S+)\s+(.*)$"
)


def limpiar_sqlserver_logs(ruta):
    """
    Procesa sqlserver_logs.log.

    Extrae:
        - timestamp
        - proceso
        - mensaje

    Además clasifica el mensaje por categoría.
    """

    registros = []

    descartadas = 0

    with open(
        ruta,
        encoding=config.ENCODING,
        errors="replace"
    ) as f:

        for linea in f:

            linea = linea.rstrip("\n")

            if not linea.strip():
                continue

            m = _RE_SQLSERVER_LOG.match(linea)

            if not m:
                descartadas += 1
                continue

            timestamp_raw = m.group(1)
            proceso = m.group(2)
            mensaje = m.group(3)

            try:
                timestamp = pd.Timestamp(
                    timestamp_raw
                )

            except Exception:
                descartadas += 1
                continue

            registros.append({
                "timestamp": timestamp,
                "proceso": proceso,
                "error_level": None,
                "error_message": mensaje,
                "mensaje": mensaje,
            })

    df = pd.DataFrame(registros)

    if not df.empty:

        # ----------------------------------------------------
        # Normalización del mensaje
        # ----------------------------------------------------

        texto = (
            df["error_message"]
            .fillna("")
            .astype(str)
            .str.lower()
        )

        # ----------------------------------------------------
        # Extraer severidad
        # ----------------------------------------------------

        severidad = texto.str.extract(
            r"severity\s*(?:level)?\s*[:=]?\s*(\d+)",
            expand=False
        )

        severidad = pd.to_numeric(
            severidad,
            errors="coerce"
        )

        df["error_level"] = severidad

        # Rellenar campos vacíos para evitar NaN
        for col in df.columns:
            if col == "timestamp":
                continue
            if df[col].dtype == "object":
                df[col] = df[col].fillna("")
            else:
                df[col] = df[col].fillna(0)

        # ----------------------------------------------------
        # Clasificación inicial
        # ----------------------------------------------------

        df["log_category"] = "INFO"

        # Startup
        df.loc[
            texto.str.contains(
                "start|startup|starting|recovery|ready for client",
                regex=True,
                na=False
            ),
            "log_category"
        ] = "STARTUP"

        # Configuration
        df.loc[
            texto.str.contains(
                "configuration|configured|setting|parameter",
                regex=True,
                na=False
            ),
            "log_category"
        ] = "CONFIGURATION"

        # Warning
        df.loc[
            texto.str.contains(
                "warning|advertencia",
                regex=True,
                na=False
            ),
            "log_category"
        ] = "WARNING"

        # Performance
        df.loc[
            texto.str.contains(
                "performance|slow|timeout|latency",
                regex=True,
                na=False
            ),
            "log_category"
        ] = "PERFORMANCE"

        # Fatal
        df.loc[
            texto.str.contains(
                "fatal",
                regex=False,
                na=False
            )
            |
            severidad.between(
                20,
                25
            ),
            "log_category"
        ] = "FATAL"

        # Error
        df.loc[
            texto.str.contains(
                "error",
                regex=False,
                na=False
            ),
            "log_category"
        ] = "ERROR"

    return df, {
        "descartadas": descartadas
    }


# ============================================================
# LIMPIEZA DE UNA CORRIDA
# ============================================================

def limpiar_corrida(corrida):
    """
    Ejecuta la limpieza completa de una carga/corrida.

    Cada corrida se procesa independientemente.
    """

    dir_corrida = os.path.join(
        config.OUTPUT_BASE_DIR,
        corrida
    )

    dir_salida = os.path.join(
        config.DIR_LIMPIO,
        corrida
    )

    os.makedirs(
        dir_salida,
        exist_ok=True
    )

    resumen = {
        "corrida": corrida
    }

    # ========================================================
    # 1. METRICS.LOG
    # ========================================================

    ruta_m = os.path.join(
        dir_corrida,
        config.NOMBRE_METRICAS
    )

    if os.path.isfile(ruta_m):

        df_m, info = limpiar_metrics(ruta_m)

        salida = os.path.join(
            dir_salida,
            config.NOMBRE_METRICAS_LIMPIO
        )

        df_m.to_csv(
            salida,
            index=False,
            encoding="utf-8-sig"
        )

        resumen.update({
            "metrics_validas": len(df_m),
            "metrics_descartadas": info["descartadas"],
            "metrics_no_numericas": info["no_numericas"],
        })

        log(
            f"   metrics.log: "
            f"validas={len(df_m)} "
            f"descartadas={info['descartadas']} "
            f"no_numericas={info['no_numericas']}"
        )

    else:

        resumen.update({
            "metrics_validas": 0,
            "metrics_descartadas": 0,
            "metrics_no_numericas": 0,
        })

        log(
            "   metrics.log: NO ENCONTRADO"
        )

    # ========================================================
    # 2. EVENTS.LOG
    # ========================================================

    ruta_e = os.path.join(
        dir_corrida,
        config.NOMBRE_EVENTS
    )

    if os.path.isfile(ruta_e):

        df_e, info = limpiar_events(ruta_e)

        salida_limpio = os.path.join(
            dir_salida,
            config.NOMBRE_EVENTS_LIMPIO
        )

        salida_preparado = os.path.join(
            dir_salida,
            config.NOMBRE_EVENTOS_PREPARADOS
        )

        df_e.to_csv(
            salida_limpio,
            index=False,
            encoding="utf-8-sig"
        )

        df_e.to_csv(
            salida_preparado,
            index=False,
            encoding="utf-8-sig"
        )

        resumen.update({
            "events_validos": len(df_e),
            "events_malformados": info["malformados"],
            "events_duplicados": info["duplicados"],
        })

        log(
            f"   events.log: "
            f"validos={len(df_e)} "
            f"malformados={info['malformados']} "
            f"duplicados={info['duplicados']}"
        )

    else:

        resumen.update({
            "events_validos": 0,
            "events_malformados": 0,
            "events_duplicados": 0,
        })

        log(
            "   events.log: NO ENCONTRADO"
        )

    # ========================================================
    # 3. SQLSERVER_LOGS.LOG
    # ========================================================

    ruta_s = os.path.join(
        dir_corrida,
        config.NOMBRE_SQLSERVER_LOGS
    )

    if os.path.isfile(ruta_s):

        df_s, info = limpiar_sqlserver_logs(
            ruta_s
        )

        salida_limpio = os.path.join(
            dir_salida,
            config.NOMBRE_SQLSERVER_LOGS_LIMPIO
        )

        salida_preparado = os.path.join(
            dir_salida,
            config.NOMBRE_LOGS_PREPARADOS
        )

        df_s.to_csv(
            salida_limpio,
            index=False,
            encoding="utf-8-sig"
        )

        df_s.to_csv(
            salida_preparado,
            index=False,
            encoding="utf-8-sig"
        )

        resumen.update({
            "sqlserver_validas": len(df_s),
            "sqlserver_descartadas": info["descartadas"],
        })

        log(
            f"   sqlserver_logs.log: "
            f"validas={len(df_s)} "
            f"descartadas={info['descartadas']}"
        )

    else:

        resumen.update({
            "sqlserver_validas": 0,
            "sqlserver_descartadas": 0,
        })

        log(
            "   sqlserver_logs.log: NO ENCONTRADO"
        )

    return resumen


# ============================================================
# MAIN
# ============================================================

def main():

    # ========================================================
    # 1. VALIDAR DIRECTORIO
    # ========================================================

    if not os.path.isdir(
        config.OUTPUT_BASE_DIR
    ):

        log(
            f"Directorio de datos no encontrado: "
            f"{config.OUTPUT_BASE_DIR}"
        )

        return

    # ========================================================
    # 2. OBTENER CARGAS / CORRIDAS
    # ========================================================

    # Excluir carpetas de salida del propio pipeline.
    dirs_salida = {
        os.path.basename(d)
        for d in (
            config.DIR_DATASETS,
            config.DIR_INVENTARIO,
            config.DIR_LIMPIO,
            config.DIR_INTEGRADO,
        )
    }

    corridas = sorted([
        d
        for d in os.listdir(
            config.OUTPUT_BASE_DIR
        )
        if os.path.isdir(
            os.path.join(
                config.OUTPUT_BASE_DIR,
                d
            )
        )
        and d not in dirs_salida
    ])

    log(
        f"Corridas a limpiar "
        f"({len(corridas)}): {corridas}"
    )

    if not corridas:

        log(
            "No se encontraron cargas/corridas."
        )

        return

    # ========================================================
    # 3. PROCESAR CADA CARGA
    # ========================================================

    resumenes = []

    for corrida in corridas:

        log(
            f"-- Limpiando corrida: {corrida}"
        )

        resumen = limpiar_corrida(
            corrida
        )

        resumenes.append(
            resumen
        )

    # ========================================================
    # 4. RESUMEN GLOBAL
    # ========================================================

    df_resumen = pd.DataFrame(
        resumenes
    )

    os.makedirs(
        config.DIR_LIMPIO,
        exist_ok=True
    )

    ruta = os.path.join(
        config.DIR_LIMPIO,
        "resumen_limpieza_global.csv"
    )

    df_resumen.to_csv(
        ruta,
        index=False,
        encoding="utf-8-sig"
    )

    log(
        f"Resumen global en: {ruta}"
    )

    # ========================================================
    # 5. MOSTRAR RESUMEN
    # ========================================================

    print(
        "\n=== RESUMEN LIMPIEZA GLOBAL ==="
    )

    columnas_resumen = [
        "corrida",
        "metrics_validas",
        "events_validos",
        "events_duplicados",
        "sqlserver_validas",
        "sqlserver_descartadas",
    ]

    # Solo mostrar columnas existentes
    columnas_existentes = [
        c
        for c in columnas_resumen
        if c in df_resumen.columns
    ]

    print(
        df_resumen[
            columnas_existentes
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()