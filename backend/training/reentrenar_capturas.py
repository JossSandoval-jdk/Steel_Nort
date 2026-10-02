"""Prepara y modela capturas anómalas al llegar a 1000 ventanas o 30 días.

Genera un candidato de diagnóstico en ``training/output/modelado_v2``.
No promueve artefactos a producción: las capturas son anomalías y no deben
mezclarse con las corridas normales que forman el baseline del detector.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CAPTURAS = BACKEND / "training" / "captures" / "anomalias"
ESTADO = CAPTURAS / "estado_reentrenamiento.json"
MAX_MUESTRAS = int(os.getenv("STEELNORT_REENTRENAR_MUESTRAS", "1000"))
DIAS_MAXIMOS = int(os.getenv("STEELNORT_REENTRENAR_DIAS", "30"))

PREPARACION = BACKEND / "training" / "nucleo" / "data_preparation"
MODELADO = BACKEND / "training" / "nucleo" / "modeling"
PASOS_PREPARACION = (
    "00_inventario.py",
    "01_seleccion.py",
    "02_limpieza.py",
    "03_transformacion.py",
    "04_integracion.py",
)
PASOS_MODELADO = (
    "01_muestras.py",
    "02_correlacion.py",
    "03_deteccion_isolation_forest.py",
    "04_reglas_motor.py",
    "05_diagnostico_resultados.py",
)


def contar_muestras() -> int:
    total = 0
    for ruta in CAPTURAS.glob("anomalias_*.csv"):
        try:
            with ruta.open(encoding="utf-8-sig", newline="") as archivo:
                total += max(0, sum(1 for _ in csv.reader(archivo)) - 1)
        except OSError as error:
            print(f"[REENTRENAMIENTO] No se pudo leer {ruta.name}: {error}", flush=True)
    return total


def leer_estado() -> dict:
    if ESTADO.is_file():
        try:
            return json.loads(ESTADO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    artefactos = list((BACKEND / "ml" / "artifacts").glob("*.joblib"))
    ultima = max((p.stat().st_mtime for p in artefactos), default=datetime.now().timestamp())
    return {
        "muestras_procesadas": 0,
        "ultimo_candidato": datetime.fromtimestamp(ultima).isoformat(),
    }


def debe_ejecutar(total: int, estado: dict, ahora: datetime) -> tuple[bool, str]:
    nuevas = max(0, total - int(estado.get("muestras_procesadas", 0)))
    if nuevas == 0:
        return False, "No hay capturas nuevas."
    if nuevas >= MAX_MUESTRAS:
        return True, f"Se alcanzaron {nuevas} ventanas anómalas nuevas."

    try:
        ultimo = datetime.fromisoformat(estado["ultimo_candidato"])
    except (KeyError, TypeError, ValueError):
        ultimo = ahora
    if ahora - ultimo >= timedelta(days=DIAS_MAXIMOS):
        return True, f"Han pasado {DIAS_MAXIMOS} días con {nuevas} ventanas nuevas."
    return False, f"{nuevas}/{MAX_MUESTRAS} ventanas nuevas; todavía no vence el plazo."


def ejecutar_pasos(carpeta: Path, pasos: tuple[str, ...], entorno: dict) -> bool:
    for nombre in pasos:
        script = carpeta / nombre
        if not script.is_file():
            print(f"[REENTRENAMIENTO] Falta {script}", flush=True)
            return False
        print(f"[REENTRENAMIENTO] Ejecutando {nombre}", flush=True)
        resultado = subprocess.run(
            [sys.executable, str(script)], cwd=carpeta, env=entorno, check=False
        )
        if resultado.returncode:
            print(f"[REENTRENAMIENTO] Falló {nombre}: {resultado.returncode}", flush=True)
            return False
    return True


def main() -> None:
    total = contar_muestras()
    estado = leer_estado()
    ahora = datetime.now()
    ejecutar, motivo = debe_ejecutar(total, estado, ahora)
    print(f"[REENTRENAMIENTO] {motivo}", flush=True)
    if not ejecutar:
        return

    entorno = os.environ.copy()
    entorno["STEELNORT_OUTPUT_DIR"] = str(BACKEND / "training" / "output")
    entorno.setdefault("STEELNORT_DATASET_SET", "integrado_v2")
    entorno.setdefault("STEELNORT_MODELADO_SET", "modelado_v2")

    if not ejecutar_pasos(PREPARACION, PASOS_PREPARACION, entorno):
        return
    if not ejecutar_pasos(MODELADO, PASOS_MODELADO, entorno):
        return

    estado.update({
        "muestras_procesadas": total,
        "ultimo_candidato": ahora.isoformat(),
        "promovido": False,
    })
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[REENTRENAMIENTO] Candidato listo; no se promovió a producción.", flush=True)


if __name__ == "__main__":
    main()