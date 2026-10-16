"""Escaneo basico de la API v2 y del front (evidencia de S1-14).

OWASP ZAP no esta instalado en el equipo del proyecto, asi que este escaneo se
hace con el propio entorno (urllib, sin dependencias nuevas). No sustituye a
ZAP: cubre huella del servidor, cabeceras de seguridad, documentacion expuesta,
metodos no esperados, recursos sensibles del servidor de Vite y el control de
acceso de las rutas internas.

Uso:  python escaneo_api.py   (con el backend en 8200 y Vite en 5173)
El informe se guarda en docs/escaneos/escaneo_api_AAAAMMDD.txt
"""

from __future__ import annotations

import datetime
import urllib.error
import urllib.request

INFORME = r"D:\SteelNort_web_v2\docs\escaneos\escaneo_api_2026-10-14.txt"

lineas: list[str] = []


def apuntar(texto: str) -> None:
    print(texto)
    lineas.append(texto)


def pedir(url, metodo="GET", cabeceras=None):
    """Devuelve (estado, cabeceras, cuerpo). -1 si no hubo respuesta."""
    peticion = urllib.request.Request(url, method=metodo, headers=cabeceras or {})
    try:
        with urllib.request.urlopen(peticion, timeout=10) as respuesta:
            return respuesta.status, dict(respuesta.headers), respuesta.read(300)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read(300)
    except Exception as error:  # noqa: BLE001 (basta para un informe)
        return -1, {}, str(error).encode()


def valor(cabeceras, clave):
    """Busca una cabecera sin distinguir mayusculas (h11 las manda en minuscula)."""
    for nombre, contenido in cabeceras.items():
        if nombre.lower() == clave.lower():
            return contenido
    return "(ausente)"


def revisar(etiqueta, url, metodo="GET", cabeceras=None, claves=(), muestra=False):
    estado, cabeceras_resp, cuerpo = pedir(url, metodo, cabeceras)
    apuntar("%-48s %-7s -> %s   (%s)" % (etiqueta, metodo, estado, valor(cabeceras_resp, "Content-Type")))
    for clave in claves:
        apuntar("     %s: %s" % (clave, valor(cabeceras_resp, clave)))
    if muestra and cuerpo:
        apuntar("     cuerpo (%d bytes): %s" % (len(cuerpo), cuerpo[:120].decode("utf-8", "replace").replace("\n", " ")))
    return estado, cabeceras_resp, cuerpo


apuntar("Escaneo basico de la API v2 y del front - " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
apuntar("ZAP no esta instalado: escaneo con el propio entorno (urllib). No sustituye a ZAP.")
apuntar("")
apuntar("== 1. Huella del servidor y cabeceras de seguridad (backend 8200) ==")
revisar(
    "GET /api/v2/salud",
    "http://127.0.0.1:8200/api/v2/salud",
    claves=("Server", "X-Powered-By", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"),
)
apuntar("")
apuntar("== 2. Documentacion expuesta sin sesion ==")
revisar("GET /docs (Swagger UI)", "http://127.0.0.1:8200/docs")
revisar("GET /openapi.json (esquema)", "http://127.0.0.1:8200/openapi.json")
revisar("GET /redoc", "http://127.0.0.1:8200/redoc")
apuntar("")
apuntar("== 3. Metodos no esperados ==")
revisar("TRACE /api/v2/salud", "http://127.0.0.1:8200/api/v2/salud", metodo="TRACE")
revisar("DELETE /api/v2/salud", "http://127.0.0.1:8200/api/v2/salud", metodo="DELETE", muestra=True)
apuntar("")
apuntar("== 4. Recursos sensibles en el servidor de Vite (5173) ==")
revisar("GET /.env", "http://127.0.0.1:5173/.env", muestra=True)
revisar("GET /.git/config", "http://127.0.0.1:5173/.git/config", muestra=True)
revisar("GET /package.json", "http://127.0.0.1:5173/package.json")
revisar("GET /src/services/api.js (fuente, normal en dev)", "http://127.0.0.1:5173/src/services/api.js")
apuntar("")
apuntar("== 5. Servidor Node de produccion (3000) ==")
revisar("GET / (Node)", "http://127.0.0.1:3000/", claves=("X-Powered-By", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"))
revisar("GET /.env (Node)", "http://127.0.0.1:3000/.env", muestra=True)
apuntar("")
apuntar("== 6. Rutas internas sin credencial (control S1-18) ==")
revisar("GET /api/v2/telemetria/actual (sin token)", "http://127.0.0.1:8200/api/v2/telemetria/actual", muestra=True)
revisar("POST /api/v2/telemetria/push (sin token)", "http://127.0.0.1:8200/api/v2/telemetria/push", metodo="POST", muestra=True)
apuntar("")
apuntar("== 7. CORS con origen ajeno ==")
revisar(
    "GET /api/v2/salud con Origin ajeno",
    "http://127.0.0.1:8200/api/v2/salud",
    cabeceras={"Origin": "http://evil.example.com"},
    claves=("Access-Control-Allow-Origin",),
)

with open(INFORME, "w", encoding="utf-8") as archivo:
    archivo.write("\n".join(lineas) + "\n")

print()
print("informe guardado en", INFORME)
