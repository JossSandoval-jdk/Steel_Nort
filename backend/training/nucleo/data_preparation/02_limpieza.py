"""
02_limpieza.py
==============

Paso 3: limpieza de logs crudos por corrida.

Entrada: metrics.log, events.log, sqlserver_logs.log
Salida:  output/limpio_v2/<corrida>/*_limpio.csv
"""

import json
import os
import re

import pandas as pd

import config
import utils

def log(msg):
    print(f"[LIMPIEZA] {msg}", flush=True)


# ==========================================
# MÉTRICAS
# ==========================================

_RE_METRICAS = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(\S+)\s*$"
)


def limpiar_metricas(ruta):
    registros = []
    descartadas = 0
    no_numericas = 0

    with open(ruta, encoding=config.ENCODING, errors="replace") as f:
        next(f, None)  # saltar cabecera

        for linea in f:
            linea = linea.rstrip("\n")
            if not linea.strip():
                continue

            m = _RE_METRICAS.match(linea)
            if not m:
                descartadas += 1
                continue

            ts_raw, metrica, valor_raw = m.groups()

            try:
                valor = float(valor_raw)
            except ValueError:
                no_numericas += 1
                continue

            try:
                ts = pd.Timestamp(ts_raw)
            except Exception:
                descartadas += 1
                continue

            registros.append((ts, metrica, valor))

    df = pd.DataFrame(registros, columns=["timestamp", "metrica", "valor"])

    # Excluir métricas corruptas definidas en config
    if not df.empty:
        df = df[~df["metrica"].isin(config.EXCLUIR_MEDICION_CORRUPTA)]

    return df, {
        "validas": len(df),
        "descartadas": descartadas,
        "no_numericas": no_numericas,
    }


# ==========================================
# EVENTOS
# ==========================================

def limpiar_eventos(ruta):
    registros = []
    malformados = 0

    with open(ruta, encoding=config.ENCODING, errors="replace") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                registros.append(json.loads(linea))
            except json.JSONDecodeError:
                malformados += 1

    df = pd.DataFrame(registros)

    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).reset_index(drop=True)

    return df, {"validos": len(df), "malformados": malformados}


# ==========================================
# SQLSERVER LOGS
# ==========================================

_RE_SQLSERVER = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+(\S+)\s+(.*)$"
)


def limpiar_sqlserver_logs(ruta):
    registros = []
    descartadas = 0

    with open(ruta, encoding=config.ENCODING, errors="replace") as f:
        for linea in f:
            linea = linea.rstrip("\n")
            if not linea.strip():
                continue

            m = _RE_SQLSERVER.match(linea)
            if not m:
                descartadas += 1
                continue

            ts_raw, proceso, mensaje = m.groups()

            try:
                ts = pd.Timestamp(ts_raw)
            except Exception:
                descartadas += 1
                continue

            registros.append({
                "timestamp": ts,
                "proceso": proceso,
                "mensaje": mensaje,
            })

    df = pd.DataFrame(registros)
    return df, {"validas": len(df), "descartadas": descartadas}


# ==========================================
# ORQUESTACIÓN
# ==========================================

def limpiar_corrida(corrida, ruta_corrida):
    dir_salida = os.path.join(config.DIR_LIMPIO, corrida)
    os.makedirs(dir_salida, exist_ok=True)

    resumen = {"corrida": corrida}

    # Métricas
    ruta_m = os.path.join(ruta_corrida, config.NOMBRE_METRICAS)
    if os.path.isfile(ruta_m):
        df_m, info = limpiar_metricas(ruta_m)
        df_m.to_csv(
            os.path.join(dir_salida, config.NOMBRE_METRICAS_LIMPIO),
            index=False, encoding="utf-8-sig",
        )
        resumen["metricas_validas"] = info["validas"]
        log(f"   metrics.log: {info['validas']} válidas")
    else:
        resumen["metricas_validas"] = 0
        log("   metrics.log: NO ENCONTRADO")

    # Eventos
    ruta_e = os.path.join(ruta_corrida, config.NOMBRE_EVENTS)
    if os.path.isfile(ruta_e):
        df_e, info = limpiar_eventos(ruta_e)
        df_e.to_csv(
            os.path.join(dir_salida, config.NOMBRE_EVENTS_LIMPIO),
            index=False, encoding="utf-8-sig",
        )
        resumen["eventos_validos"] = info["validos"]
        log(f"   events.log: {info['validos']} válidos")
    else:
        resumen["eventos_validos"] = 0
        log("   events.log: NO ENCONTRADO")

    # SQL Server logs
    ruta_s = os.path.join(ruta_corrida, config.NOMBRE_SQLSERVER_LOGS)
    if os.path.isfile(ruta_s):
        df_s, info = limpiar_sqlserver_logs(ruta_s)
        df_s.to_csv(
            os.path.join(dir_salida, config.NOMBRE_SQLSERVER_LOGS_LIMPIO),
            index=False, encoding="utf-8-sig",
        )
        resumen["sqlserver_validas"] = info["validas"]
        log(f"   sqlserver_logs.log: {info['validas']} válidas")
    else:
        resumen["sqlserver_validas"] = 0
        log("   sqlserver_logs.log: NO ENCONTRADO")

    return resumen


def main():
    if not os.path.isdir(config.OUTPUT_BASE_DIR):
        log(f"Directorio no encontrado: {config.OUTPUT_BASE_DIR}")
        return

    corridas_info = utils.descubrir_corridas()
    corridas = sorted(
        corridas_info,
        key=lambda c: (corridas_info[c]["grupo"] != "baseline", c),
    )

    log(f"Corridas a limpiar ({len(corridas)}): {corridas}")
    if not corridas:
        log("No se encontraron corridas.")
        return

    resumenes = []
    for corrida in corridas:
        log(f"-- Limpiando: {corrida}")
        resumen = limpiar_corrida(
            corrida,
            ruta_corrida=corridas_info[corrida]["ruta"],
        )
        resumen["grupo"] = corridas_info[corrida]["grupo"]
        resumenes.append(resumen)

    # Resumen global
    df_resumen = pd.DataFrame(resumenes)
    os.makedirs(config.DIR_LIMPIO, exist_ok=True)
    ruta = os.path.join(config.DIR_LIMPIO, "resumen_limpieza_global.csv")
    df_resumen.to_csv(ruta, index=False, encoding="utf-8-sig")

    print("\n=== RESUMEN LIMPIEZA GLOBAL ===")
    columnas = ["corrida", "grupo", "metricas_validas", "eventos_validos", "sqlserver_validas"]
    existentes = [c for c in columnas if c in df_resumen.columns]
    print(df_resumen[existentes].to_string(index=False))


if __name__ == "__main__":
    main()