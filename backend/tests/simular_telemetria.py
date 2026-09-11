"""Simulador de carga de trabajo e inyeccion de anomalias para SteelNort.

Genera muestras de telemetria equivalentes a las que envia el daemon
(collector) y las publica en ``POST /telemetria/muestras``.

Metodo:
  - Carga ``scaler.joblib`` y la lista de features del pkl de entrenamiento.
  - Compone cada muestra en el espacio estandarizado (z) del modelo y la
    invierte al espacio "crudo" con el scaler. El detector vuelve a
    escalar con el MISMO scaler, asi que la puntuacion es exacta:
      normal   -> z ~ N(0, 1)        -> score alto (no anomalo)
      anomalia -> z = 6..10 extremo  -> score bajo  (anomalia segura)

Uso:
    # Carga normal por 15 muestras y luego 6 anomalias en el nodo "Nodo A"
    python tests/simular_telemetria.py --normales 15 --anomalias 6

    # Solo normal, mas nodos, mas lento
    python tests/simular_telemetria.py --nodos "A,B,C" --normales 12 --intervalo 1

    # Contra FastAPI directo (sin Express)
    python tests/simular_telemetria.py --base http://localhost:8089

Requiere el backend levantado y el usuario STREAM_* del .env (admin por defecto).
"""

from __future__ import annotations

import argparse
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
SCALER = BASE_DIR / "ml" / "artifacts" / "scaler.joblib"
TRAIN_PKL = (
    BASE_DIR / "training" / "datasets" / "dataset_muestras_train.pkl"
)
FEATURES_MODELO = 22  # features del pkl de entrenamiento

DEFAULT_BASE = os.getenv("STREAM_API_URL", "http://localhost:3000")
DEFAULT_USER = os.getenv("STREAM_USER", "admin@steelnort.com")
DEFAULT_PASS = os.getenv("STREAM_PASSWORD", "Admin123!")


def cargar_scaler():
    """Devuelve (features, mean, scale) en el orden del pkl de entrenamiento."""
    if not TRAIN_PKL.exists() or not SCALER.exists():
        raise SystemExit(
            f"No se encontraron artefactos del modelo:\n  {TRAIN_PKL}\n  {SCALER}"
        )
    train = joblib.load(TRAIN_PKL)
    scaler = joblib.load(SCALER)
    feats = list(train["features"])
    mean = np.asarray(scaler.mean_, dtype="float64")
    scale = np.asarray(scaler.scale_, dtype="float64")
    if len(mean) != FEATURES_MODELO:
        raise SystemExit(f"Scaler inesperado: {len(mean)} features (esperaba 22)")
    return feats, mean, scale


def componer_muestra(feats, mean, scale, z_values, ts, fecha):
    """Invierte z -> crudo con el scaler y arma el dict de la muestra."""
    muestra = {}
    for i, nombre in enumerate(feats):
        muestra[nombre] = float(z_values[i] * scale[i] + mean[i])
    muestra["ts"] = ts
    muestra["fecha_str"] = fecha
    return muestra


def z_normal(seed):
    """Vector z tipico normal, acotado para no disparar falsos positivos."""
    return np.random.default_rng(seed).normal(0.0, 0.5, FEATURES_MODELO).clip(-1.5, 1.5)


def z_extremo(seed_idx):
    """Vector z claramente anomalo, fuera de distribucion del modelo.

    Se disparan ~18 de las 22 variables a z 6..9 (las restantes mantienen
    ruido normal). A partir de la 2a muestra consecutiva el IsolationForest
    puntua por debajo de q01 y marca la anomalia.
    """
    rng = np.random.default_rng(seed_idx)
    z = rng.normal(0.0, 0.3, FEATURES_MODELO).clip(-1.0, 1.0)
    calientes = rng.choice(FEATURES_MODELO, size=18, replace=False)
    for i in calientes:
        z[i] = rng.uniform(6.0, 9.0)
    return z


def login(base, user, passwd):
    resp = requests.post(
        f"{base.rstrip('/')}/api/auth/login",
        json={"email": user, "password": passwd},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def publicar(base, token, nodo, ip, muestra, indent):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(
        f"{base.rstrip('/')}/api/telemetria/muestras",
        json={"nodo": nodo, "ip": ip, "muestra": muestra},
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


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
    ap.add_argument("--intervalo", type=float, default=0.5,
                    help="Segundos entre muestras")
    ap.add_argument("--ip", default="127.0.0.1")
    args = ap.parse_args()

    feats, mean, scale = cargar_scaler()
    nodos = [n.strip() for n in args.nodos.split(",") if n.strip()]

    print(f"[*] Login en {args.base} ...")
    try:
        token = login(args.base, args.user, args.password)
    except Exception as exc:
        raise SystemExit(f"Login fallido (el backend esta arriba?): {exc}") from exc
    print("[*] Login OK")

    resumen = {n: {"enviadas": 0, "anomalias_detect": 0, "predicciones": 0}
               for n in nodos}

    try:
        for nodo in nodos:
            # 1) carga normal
            for k in range(args.normales):
                ts = time.time()
                muestra = componer_muestra(
                    feats, mean, scale, z_normal(k),
                    ts, None,
                )
                out = publicar(args.base, token, nodo, args.ip, muestra, 2)
                resumen[nodo]["enviadas"] += 1
                pred = out.get("prediccion")
                if pred is not None:
                    resumen[nodo]["predicciones"] += 1
                    if pred.get("es_anomalia"):
                        resumen[nodo]["anomalias_detect"] += 1
                estado = "ok" if not pred or not pred.get("es_anomalia") else "!!"
                print(f"[{nodo}] normal   #{k+1} -> {estado}")
                time.sleep(args.intervalo)

            # 2) inyeccion de anomalias
            for k in range(args.anomalias):
                ts = time.time()
                muestra = componer_muestra(
                    feats, mean, scale, z_extremo(k), ts, None,
                )
                out = publicar(args.base, token, nodo, args.ip, muestra, 2)
                resumen[nodo]["enviadas"] += 1
                pred = out.get("prediccion")
                if pred is not None:
                    resumen[nodo]["predicciones"] += 1
                    if pred.get("es_anomalia"):
                        resumen[nodo]["anomalias_detect"] += 1
                estado = "!! ANOMALIA" if (pred and pred.get("es_anomalia")) else "-"
                print(f"[{nodo}] inyec.   #{k+1} -> {estado}")
                time.sleep(args.intervalo)
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