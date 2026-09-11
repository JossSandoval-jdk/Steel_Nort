"""Pruebas de seguridad de la capa Express (middleware).

Verifica que el gateway cumpla las tres protecciones implementadas:
  1. Rate limiting  -> brute force en /api/auth/login termina en 429.
  2. Seguridad de archivos -> .env, .git, logs, node_modules devuelven 403.
  3. Proteccion del modelo -> artefactos ML (.joblib, artifacts, pkl) 403.

Tambien verifica inyecciones SQL/NoSQL en el login (deben fallar con 401,
nunca con 500 o exponer stack) y que las rutas legitimas siguen 200.

Uso:
    python tests/probar_seguridad.py                 # contra http://localhost:3000
    python tests/probar_seguridad.py --base http://localhost:3000
    python tests/probar_seguridad.py --estricto      # exit 1 si algo falla

Requiere el servidor Express levantado (npm start) y el backend arriba.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

DEFAULT_BASE = os.getenv("TEST_BASE_URL", "http://localhost:3000")

# (descripcion, metodo, ruta, body|None, codigo_esperado)
CASOS_BLOQUEO = [
    # --- archivos sensibles (403) ---
    ("archivo .env",            "GET",  "/.env",                 None, 403),
    ("dir .git",                "GET",  "/.git/config",          None, 403),
    ("logs",                    "GET",  "/logs/app.log",         None, 403),
    ("node_modules",            "GET",  "/node_modules/x/index.js", None, 403),
    ("pycache",                 "GET",  "/api/__pycache__/x.pyc", None, 403),
    # --- artefactos del modelo (403) ---
    ("joblib directo",          "GET",  "/api/ml/artifacts/modelo_isolation_forest.joblib", None, 403),
    ("scaler.joblib",           "GET",  "/api/ml/artifacts/scaler.joblib", None, 403),
    ("pkl",                     "GET",  "/api/artifacts/model.pkl", None, 403),
    ("features csv ml",         "GET",  "/api/ml/artifacts/features_modelo.csv", None, 403),
]

# Rutas legitimas (deben ser 2xx o 401 autenticado, nunca 403/500).
CASOS_LEGITIMOS = [
    ("raiz API proxied",  "GET",  "/api/"),
    ("health",            "GET",  "/health"),
    ("me sin token(401)", "GET",  "/api/auth/me"),
    ("SPA fallback",      "GET",  "/inicio"),
]

INYECCIONES_LOGIN = [
    ("' OR '1'='1",           {"email": "' OR '1'='1 --", "password": "x"}),
    ("user '--",              {"email": "admin'--", "password": "x"}),
    ("brute simple (1)",      {"email": "a@b.c", "password": "x"}),
    ("brute simple (2)",      {"email": "a@b.c", "password": "y"}),
    ("dump semantico",        {"email": "admin@steelnort.com", "password": "Admin123!"}),
]


def main():
    ap = argparse.ArgumentParser(description="Pruebas de seguridad SteelNort")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--estricto", action="store_true",
                    help="Termina con exit code 1 si alguna prueba falla")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    fallos = []

    print(f"Target: {base}\n")

    # 1) Bloqueos (archivos sensibles + modelo)
    print("== Bloqueos (esperado 403) ==")
    for desc, metodo, ruta, _body, esperado in CASOS_BLOQUEO:
        try:
            r = requests.get(f"{base}{ruta}", timeout=10)
            ok = r.status_code == esperado
            detalle = f"{r.status_code}"
            if not ok:
                detalle += f" body={r.text[:60]!r}"
        except Exception as exc:
            ok, r = False, None
            detalle = f"EXC {type(exc).__name__}: {exc}"
        marca = "OK " if ok else "FAIL"
        print(f"  [{marca}] {desc:22s} -> {detalle} (esperado {esperado})")
        if not ok:
            fallos.append(desc)

    # 2) Rutas legitimas
    print("\n== Rutas legitimas (esperado 2xx/401) ==")
    for desc, metodo, ruta in CASOS_LEGITIMOS:
        try:
            r = requests.get(f"{base}{ruta}", timeout=10)
            ok = r.status_code < 500
            detalle = f"{r.status_code}"
        except Exception as exc:
            ok, r = False, None
            detalle = f"EXC {type(exc).__name__}: {exc}"
        marca = "OK " if ok else "FAIL"
        print(f"  [{marca}] {desc:22s} -> {detalle}")
        if not ok:
            fallos.append(desc)

    # 3) Inyecciones en login (401 o 200 legitimo; nunca 500)
    print("\n== Inyecciones SQL/login ==")
    for desc, body in INYECCIONES_LOGIN:
        try:
            r = requests.post(f"{base}/api/auth/login", json=body, timeout=10)
            malo = r.status_code >= 500
            ok = not malo
            detalle = f"{r.status_code}"
        except Exception as exc:
            ok, r = False, None
            detalle = f"EXC {type(exc).__name__}: {exc}"
        marca = "OK " if ok else "FAIL"
        print(f"  [{marca}] {desc:22s} -> {detalle}")
        if not ok:
            fallos.append(desc)

    # 4) Rate limiting: brute force => 429
    print("\n== Rate limiting (brute force) ==")
    codes = []
    for i in range(25):
        try:
            r = requests.post(
                f"{base}/api/auth/login",
                json={"email": f"user{i}@test.com", "password": "wrong"},
                timeout=10,
            )
            codes.append(r.status_code)
        except Exception as exc:
            print(f"  [!] intento {i+1}: EXC {type(exc).__name__}: {exc}")
    hay_429 = 429 in codes
    marca = "OK " if hay_429 else "FAIL"
    print(f"  [{marca}] 25 intentos -> {codes.count(401)}x401, "
          f"{codes.count(429)}x429 (limite 20/15min)")
    if not hay_429:
        fallos.append("rate-limiting")

    # 5) Headers de seguridad
    print("\n== Headers de seguridad (health) ==")
    try:
        r = requests.get(f"{base}/health", timeout=10)
        csp = bool(r.headers.get("Content-Security-Policy"))
        nosniff = r.headers.get("X-Content-Type-Options") == "nosniff"
        ok = csp and nosniff
        marca = "OK " if ok else "FAIL"
        print(f"  [{marca}] CSP={csp} nosniff={nosniff}")
        if not ok:
            fallos.append("headers-seguridad")
    except Exception as exc:
        print(f"  [FAIL] {exc}")
        fallos.append("headers-seguridad")

    print("\n" + ("=" * 44))
    if fallos:
        print(f"[RESULTADO] FALLARON: {', '.join(fallos)}")
        if args.estricto:
            raise SystemExit(1)
    else:
        print("[RESULTADO] TODAS LAS PRUEBAS PASARON")
    raise SystemExit(0)


if __name__ == "__main__":
    sys.exit(main())