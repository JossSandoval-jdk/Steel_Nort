"""
02_limpieza.py
==============
Limpieza de logs crudos por corrida.

No escribe nada a disco: devuelve DataFrames limpios en memoria.
Lo consume 03_transformacion.py.
"""

import json
import os
import re

import pandas as pd

from pipeline_config import config


def log(msg):
    print(f"[LIMPIEZA] {msg}", flush=True)


# ==========================================
# Métricas
# ==========================================
_RE_METRICAS = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(\S+)\s*$"
)


def limpiar_metricas(ruta):
    """Parsea metrics.log → DataFrame(timestamp, metrica, valor)."""
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

    # Excluir métricas marcadas como corruptas en config
    if not df.empty:
        df = df[~df["metrica"].isin(config.EXCLUIR_MEDICION_CORRUPTA)]

    return df, {"validas": len(df), "descartadas": descartadas,
                "no_numericas": no_numericas}


# ==========================================
# Eventos
# ==========================================
def limpiar_eventos(ruta):
    """Parsea events.log (JSON por línea) → DataFrame."""
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
# SQL Server logs
# ==========================================
_RE_SQLSERVER = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+(\S+)\s+(.*)$"
)


def limpiar_sqlserver_logs(ruta):
    """Parsea sqlserver_logs.log → DataFrame(timestamp, proceso, mensaje)."""
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

            registros.append({"timestamp": ts, "proceso": proceso,
                              "mensaje": mensaje})

    return pd.DataFrame(registros), {"validas": len(registros),
                                     "descartadas": descartadas}


# ==========================================
# Limpieza por corrida
# ==========================================
def limpiar_corrida(corrida, ruta_corrida):
    """Limpia los 3 logs. Devuelve un dict con DataFrames y métricas."""
    out = {"corrida": corrida}

    # Métricas
    ruta = os.path.join(ruta_corrida, config.NOMBRE_METRICAS)
    if os.path.isfile(ruta):
        df, info = limpiar_metricas(ruta)
        out["metricas"] = df
        log(f"   metrics.log: {info['validas']} válidas")
    else:
        out["metricas"] = pd.DataFrame()
        log("   metrics.log: NO ENCONTRADO")

    # Eventos
    ruta = os.path.join(ruta_corrida, config.NOMBRE_EVENTS)
    if os.path.isfile(ruta):
        df, info = limpiar_eventos(ruta)
        out["eventos"] = df
        log(f"   events.log: {info['validos']} válidos")
    else:
        out["eventos"] = pd.DataFrame()
        log("   events.log: NO ENCONTRADO")

    # SQL Server logs
    ruta = os.path.join(ruta_corrida, config.NOMBRE_SQLSERVER_LOGS)
    if os.path.isfile(ruta):
        df, info = limpiar_sqlserver_logs(ruta)
        out["sqlserver"] = df
        log(f"   sqlserver_logs.log: {info['validas']} válidas")
    else:
        out["sqlserver"] = pd.DataFrame()
        log("   sqlserver_logs.log: NO ENCONTRADO")

    return out