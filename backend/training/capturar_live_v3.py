"""
capturar_live_v3.py
===================

Captura un baseline normal del estado LIVE de produccion (lo que el daemon
está empujando al backend) y lo guarda como CSV con el mismo formato del
dataset integrado, para poder reentrenar (v3) con la realidad actual.

Uso (desde la raiz del backend):
    .venv\\Scripts\\python.exe training\\capturar_live_v3.py [minutos]

Variables de entorno (todas opcionales):
    STEELNORT_CAPTURA_MIN       duracion en minutos (default 30)
    STEELNORT_CAPTURA_RUN       nombre del run (default normal_live_<fecha>)
    STEELNORT_CAPTURA_INTERVAL  segundos entre muestras (default 8)
    STEELNORT_CAPTURA_SALIDA    ruta del CSV de salida (default
                                training/output/integrado_v3/captura_live.csv)
"""

import csv
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BACKEND, ".env"))
except Exception:
    pass

from app.collector.config import (  # noqa: E402
    STREAM_API_URL,
    STREAM_USER,
    STREAM_PASSWORD,
    STREAM_NDO_NOM,
)

BASE_DATASET = os.path.join(
    BACKEND, "training", "output", "integrado_v2",
    "dataset_steelnort_preparado.csv",
)

CONTEXTO = {
    "run_name", "grupo", "wait_lck_count", "wait_io_count",
    "wait_log_count", "experiment_id",
}


def _login():
    body = json.dumps({"email": STREAM_USER, "password": STREAM_PASSWORD}).encode()
    req = urllib.request.Request(
        f"{STREAM_API_URL}/auth/login", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["access_token"]


def _estado(token):
    req = urllib.request.Request(
        f"{STREAM_API_URL}/telemetria/estado",
        headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _columnas_datos():
    with open(BASE_DATASET, encoding="utf-8-sig") as f:
        cols = next(csv.reader(f))
    return [c for c in cols]


def _nodo(estado):
    nodos = estado.get("nodos", {})
    if STREAM_NDO_NOM in nodos and nodos[STREAM_NDO_NOM].get("ultima"):
        return STREAM_NDO_NOM
    for nombre, info in nodos.items():
        if info.get("ultima"):
            return nombre
    raise RuntimeError("No hay nodos con muestra en /telemetria/estado. "
                       "Revisa que el daemon este corriendo.")


def main():
    minutos = float(sys.argv[1]) if len(sys.argv) > 1 else float(
        os.getenv("STEELNORT_CAPTURA_MIN", "30"))
    run = os.getenv(
        "STEELNORT_CAPTURA_RUN",
        "normal_live_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    intervalo = float(os.getenv("STEELNORT_CAPTURA_INTERVAL", "8"))
    salida = os.getenv(
        "STEELNORT_CAPTURA_SALIDA",
        os.path.join(BACKEND, "training", "output", "integrado_v3",
                     "captura_live.csv"))

    columnas = _columnas_datos()
    datos_cols = [c for c in columnas if c not in CONTEXTO]

    token = _login()
    est = _estado(token)
    nodo = _nodo(est)
    print(f"[CAPTURA] nodo={nodo} | run={run} | {minutos:.0f} min "
          f"cada {intervalo:.0f}s -> {salida}", flush=True)

    os.makedirs(os.path.dirname(salida), exist_ok=True)
    fin = time.time() + minutos * 60
    filas = 0
    avisado = False
    with open(salida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(columnas)
        while time.time() < fin:
            try:
                est = _estado(token)
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    token = _login()
                    est = _estado(token)
                else:
                    print(f"[CAPTURA] error estado: {e}", flush=True)
            muestra = est["nodos"][nodo]["ultima"] or {}
            hace = float(est["nodos"][nodo].get("hace_seg", 999) or 999)
            if hace > 40 and not avisado:
                print("[CAPTURA] AVISO: el nodo no se actualiza "
                      f"(hace {hace:.0f}s). ¿El daemon sigue corriendo?",
                      flush=True)
                avisado = True
            valores = []
            for c in datos_cols:
                if c == "timestamp":
                    valores.append(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                else:
                    v = muestra.get(c, 0.0)
                    valores.append("%.6g" % float(v or 0.0))
            valores += [run, "baseline", "0", "0", "0", run]
            w.writerow(valores)
            filas += 1
            if filas % 15 == 0:
                print(f"[CAPTURA] {filas} filas | restan "
                      f"{max(0.0, fin - time.time()) / 60:.1f} min", flush=True)
            time.sleep(intervalo)
    print(f"[CAPTURA] LISTO: {filas} filas -> {salida}", flush=True)


if __name__ == "__main__":
    main()