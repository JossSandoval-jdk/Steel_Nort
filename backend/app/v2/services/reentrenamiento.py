"""Ejecución no bloqueante del pipeline cuando hay suficientes capturas."""

from __future__ import annotations

import csv
import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("steelnort.v2.reentrenamiento")
BACKEND = Path(__file__).resolve().parents[3]
MAX_MUESTRAS = int(os.getenv("STEELNORT_REENTRENAR_MUESTRAS", "1000"))
DIAS_MAXIMOS = int(os.getenv("STEELNORT_REENTRENAR_DIAS", "30"))
_lock = threading.Lock()
_en_curso = False


def revisar_umbral() -> None:
    """Lanza un candidato solo al acumular 1000 ventanas o cumplir 30 días."""
    with _lock:
        if _en_curso:
            return

    total = 0
    capturas = BACKEND / "training" / "captures" / "anomalias"
    for ruta in capturas.glob("anomalias_*.csv"):
        try:
            with ruta.open(encoding="utf-8-sig", newline="") as archivo:
                total += max(0, sum(1 for _ in csv.reader(archivo)) - 1)
        except OSError:
            log.exception("No se pudo contar la captura %s", ruta)

    estado_path = capturas / "estado_reentrenamiento.json"
    try:
        estado = json.loads(estado_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        artefactos = list((BACKEND / "ml" / "artifacts").glob("*.joblib"))
        marca = max((ruta.stat().st_mtime for ruta in artefactos), default=datetime.now().timestamp())
        estado = {
            "muestras_procesadas": 0,
            "ultimo_candidato": datetime.fromtimestamp(marca).isoformat(),
        }

    nuevas = max(0, total - int(estado.get("muestras_procesadas", 0)))
    if nuevas == 0:
        return
    try:
        ultimo = datetime.fromisoformat(estado["ultimo_candidato"])
    except (KeyError, TypeError, ValueError):
        ultimo = datetime.now()
    vencido = datetime.now() - ultimo >= timedelta(days=DIAS_MAXIMOS)
    if nuevas < MAX_MUESTRAS and not vencido:
        return

    with _lock:
        if _en_curso:
            return
        _en_curso = True

    hilo = threading.Thread(target=_ejecutar, name="reentrenamiento-candidato", daemon=True)
    hilo.start()


def _ejecutar() -> None:
    global _en_curso
    backend = BACKEND
    script = backend / "training" / "reentrenar_capturas.py"
    archivo_log = backend / "training" / "captures" / "reentrenamiento.log"
    try:
        archivo_log.parent.mkdir(parents=True, exist_ok=True)
        with archivo_log.open("a", encoding="utf-8") as salida:
            resultado = subprocess.run(
                [sys.executable, str(script)],
                cwd=backend,
                stdout=salida,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if resultado.returncode:
            log.error("El pipeline de candidato terminó con código %s", resultado.returncode)
    except Exception:
        log.exception("No se pudo iniciar el pipeline de reentrenamiento")
    finally:
        with _lock:
            _en_curso = False