"""
13_disponibilidad.py
====================
Mide la disponibilidad del sistema (indicador I-5.4, meta >= 95 %) haciendo
ping periodico al endpoint de salud durante una ventana de observacion:

    Disponibilidad = pings_ok / pings_totales * 100

Entrada : API en ejecucion (endpoint /salud)
Salida  : output/modelado/indicadores/disponibilidad.json

Variables de entorno (o argumentos):
  STEELNORT_API_URL  default http://localhost:8200/api/v2

Uso:
    python indicadores/13_disponibilidad.py --pings 30 --intervalo 10
    python indicadores/13_disponibilidad.py --duracion 3600  # 1 hora
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Config del modelado (parents[1] = tools/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelado_config import DIR_MODELADO, log  # noqa: E402

DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")


def ping(url, timeout=5):
    """Un ping al endpoint de salud. Devuelve (ok, codigo, ms)."""
    req = urllib.request.Request(url, method="GET")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            return True, resp.status, (time.perf_counter() - t0) * 1000.0
    except urllib.error.HTTPError as e:
        return False, e.code, (time.perf_counter() - t0) * 1000.0
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, str(e), (time.perf_counter() - t0) * 1000.0


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    ap = argparse.ArgumentParser(description="I-5.4 disponibilidad del sistema")
    ap.add_argument("--base", default=os.getenv("STEELNORT_API_URL",
                                                "http://localhost:8200/api/v2"))
    ap.add_argument("--pings", type=int, default=30, help="numero de pings")
    ap.add_argument("--intervalo", type=float, default=10.0,
                    help="segundos entre pings")
    ap.add_argument("--duracion", type=float, default=0.0,
                    help="si > 0, ignora --pings y mide durante N segundos")
    args = ap.parse_args()

    url = f"{args.base.rstrip('/')}/salud"
    muestras = []
    ok_total = 0
    log(f"Ping a {url} (intervalo {args.intervalo}s)...")

    inicio = time.time()
    i = 0
    while True:
        i += 1
        ok, cod, ms = ping(url)
        ok_total += int(ok)
        muestras.append({"i": i, "fec": ahora(), "ok": bool(ok),
                         "codigo": cod, "ms": round(ms, 1)})
        if args.duracion > 0:
            if time.time() - inicio >= args.duracion:
                break
        elif i >= args.pings:
            break
        time.sleep(args.intervalo)

    total = len(muestras)
    disponibilidad = ok_total / total if total else 0.0
    latencias = [m["ms"] for m in muestras if m["ok"]]

    salida = {
        "url": url,
        "fec_inicio": muestras[0]["fec"] if muestras else ahora(),
        "fec_fin": muestras[-1]["fec"] if muestras else ahora(),
        "pings_totales": total,
        "pings_ok": ok_total,
        "pings_fallidos": total - ok_total,
        "disponibilidad": round(disponibilidad, 4),
        "meta": 0.95,
        "cumple": bool(disponibilidad >= 0.95),
        "latencia_media_ms": round(sum(latencias) / len(latencias), 1) if latencias else None,
        "muestras": muestras,
    }

    os.makedirs(DIR_VAL, exist_ok=True)
    ruta = os.path.join(DIR_VAL, "disponibilidad.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=2)

    print("\n=== I-5.4 DISPONIBILIDAD ===")
    print(f"  pings={total} ok={ok_total} fallidos={total - ok_total}")
    print(f"  disponibilidad = {disponibilidad:.2%}  "
          f"({'CUMPLE' if disponibilidad >= 0.95 else 'NO CUMPLE'} meta >= 95 %)")
    print(f"\nInforme: {ruta}")


if __name__ == "__main__":
    main()
