"""Validador end-to-end del detector de anomalias SteelNort.

Inyecta por el ENDPOINT REAL de telemetria (/telemetria/muestras) una
carga de trabajo mezclada - datos normales y anomalias - y muestra en el
terminal en que clase cae CADA ventana, igual que lo hace el backend.

VALIDACION:
  1. Abre sesion en la API (login JWT).
  2. Envia ~15 muestras NORMALES  -> el backend loguea "NORMAL".
  3. Envia ~8  muestras ANOMALAS  -> el backend loguea "ANOMALIA".
  4. Envia ~12 muestras NORMALES otra vez.
  5. Imprime resumen y estado del detector; consulta /telemetria/estado.

Uso (con el backend PRENDIDO en :8000):
    python tools/simular_carga.py
    set STEELNORT_API=http://localhost:8000   # si el API esta en otro puerto
    set STEELNORT_ADMIN_EMAIL=admin@steelnort.com
    set STEELNORT_ADMIN_PASSWORD=Admin123!
"""

from __future__ import annotations

import os
import random
import time
from datetime import datetime

import requests

API_BASE = os.getenv("STEELNORT_API", "http://localhost:8000")
ADMIN_EMAIL = os.getenv("STEELNORT_ADMIN_EMAIL", "admin@steelnort.com")
ADMIN_PASSWORD = os.getenv("STEELNORT_ADMIN_PASSWORD", "Admin123!")
NODO = os.getenv("STEELNORT_NODO_SIM", "SERVIDOR-SIM")
IP_NODO = os.getenv("STEELNORT_NODO_IP_SIM", "10.0.1.77")

FEATURES = [
    "active_sessions", "api_latency_ms", "cpu_sys", "cpu_time_sum_ms",
    "cpu_usr", "cpu_wai", "disk_read_per_sec", "disk_write_per_sec",
    "duration_avg_ms", "duration_max_ms", "load1", "lock_waits",
    "memory_percent", "page_life_expectancy", "query_count", "total_reads",
    "total_writes", "transactions_per_sec", "wait_log_count",
]

VENTANA = 10


def _normal() -> dict:
    return {f: round(random.gauss(0.5, 0.1), 4) for f in FEATURES}


def _anomalia() -> dict:
    muestra = {f: round(random.gauss(0.5, 0.1), 4) for f in FEATURES}
    for f in random.sample(FEATURES, 5):
        muestra[f] = round(random.gauss(8.0, 2.0), 4)
    return muestra


def _login() -> str:
    resp = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    if resp.status_code != 200:
        raise SystemExit(
            f"ERROR login ({resp.status_code}): {resp.text[:300]}\n"
            "Revisa que el backend este prendido y las credenciales."
        )
    return resp.json()["access_token"]


def _publicar(token: str, fase: str, cantidad: int, mostrar: bool) -> list[bool]:
    """Publica ``cantidad`` muestras; devuelve la clasificacion real."""
    cabeceras = {"Authorization": f"Bearer {token}"}
    resultados: list[bool] = []
    generador = (_normal if fase == "normal" else _anomalia)
    esperado = "NORMAL" if fase == "normal" else "ANOMALIA"
    for i in range(1, cantidad + 1):
        payload = {
            "nodo": NODO,
            "ip": IP_NODO,
            "muestra": generador(),
        }
        resp = requests.post(f"{API_BASE}/telemetria/muestras",
                             json=payload, headers=cabeceras, timeout=15)
        if resp.status_code != 200:
            print(f"  [{i:3d}] ERROR HTTP {resp.status_code}: {resp.text[:200]}")
            continue
        pred = resp.json().get("prediccion")
        if pred is None:
            # La ventana aun no llego a 10 muestras.
            if mostrar:
                hmm = f"[{i:3d}] ({i}/{VENTANA}) llenando ventana..."
                print(f"  {hmm}")
            continue
        es_anom = bool(pred["es_anomalia"])
        resultados.append(es_anom)
        if mostrar:
            marca = "ANOMALIA" if es_anom else "NORMAL"
            ok = "( OK - coincide )" if marca == esperado else "( NO coincide )"
            print(
                f"  [{i:3d}] {marca:<9} score={pred['score']:<9.4f} "
                f"umbral={pred['umbral']:.4f} {ok}"
            )
        time.sleep(0.05)
    return resultados


def main() -> None:
    print(f"Conectando a {API_BASE} con {ADMIN_EMAIL} ...")
    token = _login()
    print(f"Sesion OK. Nodo simulado: {NODO} ({IP_NODO})")
    print()

    print("FASE 1 - Carga NORMAL (15 muestras):")
    normales_1 = _publicar(token, "normal", 15, mostrar=True)
    print(f"  -> {sum(1 for a in normales_1 if not a)} NORMAL / "
          f"{sum(normales_1)} ANOMALIA")
    print()

    print("FASE 2 - Inyeccion de ANOMALIAS (8 muestras):")
    anomalias = _publicar(token, "anomalia", 8, mostrar=True)
    print(f"  -> {sum(1 for a in anomalias if not a)} NORMAL / "
          f"{sum(anomalias)} ANOMALIA")
    print()

    print("FASE 3 - Vuelta a carga NORMAL (12 muestras):")
    normales_2 = _publicar(token, "normal", 12, mostrar=True)
    print(f"  -> {sum(1 for a in normales_2 if not a)} NORMAL / "
          f"{sum(normales_2)} ANOMALIA")
    print()

    print("=" * 60)
    total_n = sum(1 for a in normales_1 + normales_2 if not a)
    total_a = sum(anomalias)
    print(f"RESUMEN: {total_n} NORMALES | {total_a} ANOMALIAS detectadas")
    confiables = total_n >= 10 and total_a >= 5
    print("MODELO VALIDADO ✔  -> la clasificacion coincide con la carga"
          if confiables
          else "Revisa umbrales/ventana: la separacion no fue clara.")
    print()

    # Estado del detector despues de la validacion.
    try:
        est = requests.get(f"{API_BASE}/telemetria/estado",
                           headers={"Authorization": f"Bearer {token}"},
                           timeout=15).json()
        det = est.get("detector", {})
        print("Estado del detector:")
        print(f"  umbral_actual={det.get('umbral_actual')} "
              f"({det.get('umbral_nombre')}) features={len(det.get('features', []))}")
        print(f"  ventanas_llenas={det.get('ventanas_llenas')}")
    except Exception as exc:  # noqa: BLE001
        print(f"No se pudo consultar /telemetria/estado: {exc}")


if __name__ == "__main__":
    main()