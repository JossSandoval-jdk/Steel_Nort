"""
utils.py
========

Funciones compartidas del pipeline.
"""

import json
import os
from pathlib import Path

import config


def log(msg):
    print(f"[UTILS] {msg}", flush=True)


def _subcarpetas_con_logs(carpeta):
    """Subcarpetas con al menos un archivo de entrada."""
    if not os.path.isdir(carpeta):
        return []
    return [
        d for d in sorted(os.listdir(carpeta))
        if os.path.isdir(os.path.join(carpeta, d))
        and any(
            os.path.isfile(os.path.join(carpeta, d, f))
            for f in config.ARCHIVOS_ENTRADA
        )
    ]


def descubrir_corridas(raiz=None):
    """Devuelve {corrida: {grupo, ruta}}."""
    raiz = Path(raiz) if raiz else config.OUTPUT_BASE_DIR
    corridas = {}

    def _marcar(carpeta, grupo):
        for d in _subcarpetas_con_logs(carpeta):
            corridas.setdefault(d, {"grupo": grupo, "ruta": str(Path(carpeta) / d)})

    _marcar(config.DIR_ANOMALIAS, "anomalias")
    _marcar(config.DIR_BASELINE, "baseline")

    for d in sorted(os.listdir(raiz)):
        p = raiz / d
        if not p.is_dir():
            continue
        if d in config.DIRS_ARTEFACTO or d in ("anomalias", "baseline"):
            continue
        if _subcarpetas_con_logs(p):
            _marcar(p, "legacy")
        elif any(os.path.isfile(p / f) for f in config.ARCHIVOS_ENTRADA):
            corridas.setdefault(d, {"grupo": "raiz", "ruta": str(p)})

    return corridas


def leer_origen(ruta_corrida, grupo=None):
    """Lee origen.json; si no existe, infiere es_carga_normal del grupo."""
    origen = {"origen": config.TIPO_ORIGEN_LEGADO}
    p = Path(ruta_corrida) / config.NOMBRE_ORIGEN
    if p.is_file():
        try:
            with open(p, encoding="utf-8") as f:
                origen.update(json.load(f))
        except Exception as e:
            log(f"Advertencia leyendo {p}: {e}")

    if "es_carga_normal" not in origen and grupo:
        origen["es_carga_normal"] = (grupo == "baseline")
    return origen