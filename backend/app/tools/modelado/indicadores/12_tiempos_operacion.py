"""
12_tiempos_operacion.py
=======================
Mide la latencia de las operaciones principales (indicador I-5.2, meta <= 3 s):
login, carga del dashboard, consulta de anomalias y generacion de reporte.

Se conecta a la API v2 EN EJECUCION, inicia sesion para obtener el JWT y
cronometra ``n`` repeticiones por operacion (media y percentil 95).

Entrada : API en ejecucion + credenciales
Salida  : output/modelado/indicadores/tiempos_operacion.json
          output/modelado/indicadores/tiempos_operacion.csv

Variables de entorno (o argumentos):
  STEELNORT_API_URL  default http://localhost:8200/api/v2
  STEELNORT_USUARIO  default admin
  STEELNORT_CLAVE    requerida (o --clave)

Uso:
    python indicadores/12_tiempos_operacion.py --n 30
    python indicadores/12_tiempos_operacion.py --clave "Admin123!" --n 30
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

# Config del modelado (parents[1] = tools/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelado_config import DIR_MODELADO, log  # noqa: E402

DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")

# Operaciones principales (metodo, ruta relativa a la base de la API).
OPERACIONES = [
    ("dashboard", "GET", "/sistema/resumen"),
    ("anomalias", "GET", "/informes/anomalias"),
    ("alertas", "GET", "/deteccion/alertas"),
    ("reporte_resumen", "GET", "/informes/resumen"),
]


def pedir(url, metodo="GET", token=None, cuerpo=None, timeout=10):
    """Hace una peticion HTTP y devuelve (ok, codigo, segundos)."""
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    cabeceras = {"Content-Type": "application/json"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=datos, headers=cabeceras,
                                 method=metodo)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            return True, resp.status, time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return False, e.code, time.perf_counter() - t0
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, str(e), time.perf_counter() - t0


def estadisticas(tiempos):
    if not tiempos:
        return None
    arr = np.array(tiempos) * 1000.0  # ms
    return {
        "n": int(len(arr)),
        "media_ms": round(float(arr.mean()), 1),
        "p95_ms": round(float(np.percentile(arr, 95)), 1),
        "min_ms": round(float(arr.min()), 1),
        "max_ms": round(float(arr.max()), 1),
    }


def main():
    ap = argparse.ArgumentParser(description="I-5.2 tiempos por operacion")
    ap.add_argument("--base", default=os.getenv("STEELNORT_API_URL",
                                                "http://localhost:8200/api/v2"))
    ap.add_argument("--usuario", default=os.getenv("STEELNORT_USUARIO", "admin"))
    ap.add_argument("--clave", default=os.getenv("STEELNORT_CLAVE", ""))
    ap.add_argument("--n", type=int, default=30, help="repeticiones por operacion")
    args = ap.parse_args()

    base = args.base.rstrip("/")

    if not args.clave:
        log("Falta la clave. Usa --clave o la variable STEELNORT_CLAVE.")
        return

    # --- Login (tambien es una operacion medida) ---
    ok, cod, seg = pedir(f"{base}/auth/login", "POST",
                         cuerpo={"usuario": args.usuario, "clave": args.clave})
    if not ok:
        log(f"No se pudo iniciar sesion en {base} ({cod}).")
        log("Comprueba que el backend este en ejecucion y las credenciales sean validas.")
        return
    token = None
    # Reintento para capturar el token (el primer login ya se hizo).
    datos = json.dumps({"usuario": args.usuario, "clave": args.clave}).encode()
    req = urllib.request.Request(f"{base}/auth/login", data=datos,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        token = json.loads(resp.read().decode("utf-8")).get("access_token")
    log(f"Sesion iniciada como {args.usuario}. Token {'ok' if token else 'ausente'}.")

    resultados = {}
    todos = []
    for nombre, metodo, ruta in OPERACIONES:
        tiempos = []
        errores = 0
        for _ in range(args.n):
            ok, cod, seg = pedir(f"{base}{ruta}", metodo, token=token)
            if ok:
                tiempos.append(seg)
                todos.append(seg)
            else:
                errores += 1
        est = estadisticas(tiempos) or {"n": 0}
        est["errores"] = errores
        resultados[nombre] = est
        log(f"{nombre:<16} n={est['n']} media={est.get('media_ms')}ms "
            f"p95={est.get('p95_ms')}ms errores={errores}")

    t_prom = estadisticas(todos) if todos else None
    cumple = bool(t_prom and t_prom["media_ms"] <= 3000.0)

    salida = {
        "base_url": base,
        "n_por_operacion": args.n,
        "meta_ms": 3000,
        "operaciones": resultados,
        "global": t_prom,
        "cumple": cumple,
    }

    os.makedirs(DIR_VAL, exist_ok=True)
    ruta_json = os.path.join(DIR_VAL, "tiempos_operacion.json")
    with open(ruta_json, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=2)

    # CSV plano
    ruta_csv = os.path.join(DIR_VAL, "tiempos_operacion.csv")
    with open(ruta_csv, "w", encoding="utf-8") as fh:
        fh.write("operacion,n,media_ms,p95_ms,min_ms,max_ms,errores\n")
        for nombre, est in resultados.items():
            fh.write(f"{nombre},{est.get('n', 0)},{est.get('media_ms', '')},"
                     f"{est.get('p95_ms', '')},{est.get('min_ms', '')},"
                     f"{est.get('max_ms', '')},{est.get('errores', 0)}\n")

    print("\n=== I-5.2 TIEMPO DE RESPUESTA POR OPERACION ===")
    if t_prom:
        print(f"  global: media={t_prom['media_ms']}ms p95={t_prom['p95_ms']}ms "
              f"n={t_prom['n']}  ({'CUMPLE' if cumple else 'NO CUMPLE'} meta <= 3 s)")
    print(f"\nInformes: {ruta_json}")
    print(f"          {ruta_csv}")


if __name__ == "__main__":
    main()
