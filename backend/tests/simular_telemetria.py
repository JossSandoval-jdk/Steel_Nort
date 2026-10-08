"""Simulador de carga de trabajo e inyeccion de anomalias para SteelNort.

Genera muestras de telemetria equivalentes a las que envia el daemon
(collector) y las publica en ``POST /api/v2/telemetria/push``.

Metodo:
  - Toma las muestras NORMALES del propio dataset de train
    (dataset_muestras_train.pkl, reconstruido en crudo via scaler), asi
    que caen siempre dentro de la distribucion del modelo: un sintetico
    con ruido i.i.d. rompe las correlaciones entre variables y todo
    puntua como anomalo.
  - Las ANOMALIAS toman una muestra real y calientan (z 6..9 via el
    scaler) las variables que puntua el detector (features_modelo.csv).
  - Cada nodo tiene su propia serie: normal -> anomalias -> cierre
    normal, con la ventana [features x 10] del detector llenandose,
    disparando y recuperandose.

Uso:
    # Carga normal por 15 muestras, 6 anomalias y cierre normal (12)
    python tests/simular_telemetria.py --normales 15 --anomalias 6

    # Solo normal, mas nodos, mas lento
    python tests/simular_telemetria.py --nodos "A,B,C" --normales 12 --intervalo 1

    # Contra FastAPI directo (por defecto la API v2 del run_backend.bat)
    python tests/simular_telemetria.py --base http://localhost:8200/api/v2

Requiere el backend levantado y las credenciales STREAM_* del .env.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

try:
    import joblib
    import numpy as np
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Faltan dependencias (joblib/numpy/requests). Use el entorno: "
        ".venv\\Scripts\\python.exe tests\\simular_telemetria.py"
    ) from exc

BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except Exception:  # pragma: no cover
    pass

SCALER = BASE_DIR / "ml" / "artifacts" / "scaler.joblib"
FEATURES_MODELO_CSV = BASE_DIR / "ml" / "artifacts" / "features_modelo.csv"
TRAIN_PKL = (
    BASE_DIR / "training" / "datasets" / "dataset_muestras_train.pkl"
)

DEFAULT_BASE = os.getenv("STREAM_API_URL", "http://localhost:8200/api/v2")
DEFAULT_USER = os.getenv("STREAM_USER", "")
DEFAULT_PASS = os.getenv("STREAM_PASSWORD", "")


def cargar_scaler():
    """Devuelve (features, mean, scale, idx_modelo) alineados al pkl.

    - features/mean/scale: en el orden del pkl de entrenamiento (54 vars).
    - idx_modelo: posiciones de las variables que puntua el detector
      (features_modelo.csv); son las que se calientan en la inyeccion.
    """
    if not TRAIN_PKL.exists() or not SCALER.exists():
        raise SystemExit(
            f"No se encontraron artefactos del modelo:\n  {TRAIN_PKL}\n  {SCALER}"
        )
    train = joblib.load(TRAIN_PKL)
    scaler = joblib.load(SCALER)
    feats = list(train["features"])
    mean = np.asarray(scaler.mean_, dtype="float64")
    scale = np.asarray(scaler.scale_, dtype="float64")
    if len(mean) != len(feats):
        raise SystemExit(
            f"Scaler inconsistente: {len(mean)} features vs pkl {len(feats)}"
        )
    modelo = set()
    if FEATURES_MODELO_CSV.exists():
        with open(FEATURES_MODELO_CSV, encoding="utf-8-sig") as fh:
            modelo = {r[0].strip() for r in csv.reader(fh) if r and r[0].strip()
                      and r[0].strip().lower() != "columna"}
    idx_modelo = [i for i, f in enumerate(feats) if f in modelo]
    if not idx_modelo:
        raise SystemExit("Ninguna feature de features_modelo.csv esta en el pkl.")
    return feats, mean, scale, idx_modelo


class Serie:
    """Muestras sinteticas ancladas al dataset REAL de train.

    Los normales son muestras del propio pkl (ventanas solapadas
    reconstruidas en crudo), asi que caen siempre dentro de la
    distribucion del modelo: un sintetizador con ruido i.i.d. o AR(1)
    rompe las correlaciones entre variables (memory_used_mb vs
    memory_percent, cpu_usr vs cpu_sys, ...) y todo puntua como anomalo.

    Las anomalias toman la muestra real y calientan (z 6..9 via el
    scaler) las variables que puntua el detector (features_modelo.csv).
    """

    def __init__(self, feats, mean, scale, idx_modelo, semilla: int = 0):
        self.rng = np.random.default_rng(semilla)
        self.feats = feats
        self.mean = mean
        self.scale = scale
        self.idx_modelo = idx_modelo
        pkl = joblib.load(TRAIN_PKL)
        X = np.asarray(pkl["X"], dtype="float64")  # [n_ventanas, V, F]
        # Las ventanas se solapan en 9 muestras: la ultima de la ventana i
        # es la primera de la i+1, asi que con [X[0] + X[1:, -1]] se
        # reconstruye la serie cruda continua del entrenamiento.
        serie = np.vstack([X[0], X[1:, -1]])
        serie = np.nan_to_num(serie, nan=0.0)
        self.serie_raw = serie * scale + mean
        self.i = int(self.rng.integers(0, len(self.serie_raw)))

    def _siguiente(self):
        raw = self.serie_raw[self.i % len(self.serie_raw)].copy()
        self.i += 1
        return raw

    def normal(self, _k=None):
        """Muestra real del train: distribucion garantizada."""
        return self._siguiente()

    def anomalo(self, _k=None):
        """Muestra real con las variables del modelo fuera de escala."""
        raw = self._siguiente()
        for i in self.idx_modelo:
            z = self.rng.uniform(6.0, 9.0)
            raw[i] = self.mean[i] + z * self.scale[i]
        return raw

    def muestra(self, raw, ts):
        """Convierte el vector crudo en la muestra JSON del push."""
        out = {nombre: float(raw[i]) for i, nombre in enumerate(self.feats)}
        out["ts"] = ts
        out["fecha_str"] = None
        return out


def login(base, user, passwd):
    resp = requests.post(
        f"{base.rstrip('/')}/auth/login",
        json={"usuario": user, "clave": passwd},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def publicar(base, token, nodo, ip, muestra, indent):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = requests.post(
        f"{base.rstrip('/')}/telemetria/push",
        json={"nodo": nodo, "ip": ip, "muestra": muestra,
              "eventos": [], "logs": []},
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def registrar(resumen, nodo, out):
    """Traduce la respuesta de /telemetria/push al resumen del simulador."""
    if out.get("estado") != "evaluado":
        return  # ventana todavia acumulando
    resumen[nodo]["predicciones"] += 1
    if out.get("alerta_nueva") or out.get("es_anomalia"):
        resumen[nodo]["anomalias_detect"] += 1


def main():
    ap = argparse.ArgumentParser(description="Simulador de telemetria SteelNort")
    ap.add_argument("--base", default=DEFAULT_BASE, help="URL base del gateway")
    ap.add_argument("--user", default=DEFAULT_USER)
    ap.add_argument("--password", default=DEFAULT_PASS)
    ap.add_argument("--nodos", default="Nodo A", help="Coma separada de nodos")
    ap.add_argument("--normales", type=int, default=15,
                    help="Muestras normales por nodo (>=10 llenan la ventana)")
    ap.add_argument("--anomalias", type=int, default=6,
                    help="Muestras anomalas a inyectar al final por nodo")
    ap.add_argument("--cierre", type=int, default=12,
                    help="Muestras normales de vuelta tras la inyeccion (0 desactiva)")
    ap.add_argument("--intervalo", type=float, default=0.5,
                    help="Segundos entre muestras")
    ap.add_argument("--ip", default="127.0.0.1")
    args = ap.parse_args()

    feats, mean, scale, idx_modelo = cargar_scaler()
    nodos = [n.strip() for n in args.nodos.split(",") if n.strip()]

    print(f"[*] Login en {args.base} ...")
    token = None
    try:
        token = login(args.base, args.user, args.password)
        print("[*] Login OK")
    except Exception as exc:
        # /telemetria/push no exige token: seguimos sin el.
        print(f"[!] Login no disponible ({exc}); sigo sin token.")

    resumen = {n: {"enviadas": 0, "anomalias_detect": 0, "predicciones": 0}
               for n in nodos}

    def fase(nodo, etiqueta, n_muestras, generador, serie):
        for k in range(n_muestras):
            muestra = serie.muestra(generador(k), time.time())
            out = publicar(args.base, token, nodo, args.ip, muestra, 2)
            resumen[nodo]["enviadas"] += 1
            registrar(resumen, nodo, out)
            anom = out.get("alerta_nueva") or out.get("es_anomalia")
            if out.get("estado") != "evaluado":
                estado = f"llenando ventana ({out.get('estado')})"
            else:
                estado = "!! ANOMALIA" if anom else "ok"
            print(f"[{nodo}] {etiqueta:<9} #{k+1} -> {estado}")
            time.sleep(args.intervalo)

    try:
        for nodo in nodos:
            serie = Serie(feats, mean, scale, idx_modelo,
                          semilla=len(nodo) * 7 + 1)
            fase(nodo, "normal", args.normales, serie.normal, serie)
            fase(nodo, "inyec.", args.anomalias, serie.anomalo, serie)
            if args.cierre:
                fase(nodo, "cierre", args.cierre, serie.normal, serie)
    except requests.exceptions.HTTPError as exc:
        print(f"[!] Error HTTP: {exc}")
        if exc.response is not None:
            try:
                print(json.dumps(exc.response.json(), indent=2))
            except Exception:
                print(exc.response.text)
        raise SystemExit(1)

    print("\n=== RESUMEN ===")
    for nodo, r in resumen.items():
        det = r["anomalias_detect"] if r["predicciones"] else "n/a"
        print(
            f"  {nodo}: enviadas={r['enviadas']} predicciones={r['predicciones']} "
            f"anomalias_detectadas={det}"
        )
    if any(r["predicciones"] and not r["anomalias_detect"] for r in resumen.values()):
        print("\n[!] Ninguna anomalia detectada: revise el umbral o el modelo.")
    else:
        print("\n[OK] Detector respondio correctamente en las inyecciones.")


if __name__ == "__main__":
    main()