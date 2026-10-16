"""Proteccion CSRF por doble-envio (cookie + cabecera ``X-CSRF-Token``).

La v2 autentica con un JWT que vive **en memoria** (no hay cookies de sesion),
asi que la superficie clasica de CSRF no existia. Aun asi se agrega esta capa
como **defensa en profundidad** (decision S1-8): si en el futuro las
credenciales pasaran a cookies, el control ya estaria en su sitio y probado.

Como funciona (patron de doble-envio):

  1. La API emite una cookie ``csrf_token`` (legible por JS, no ``HttpOnly``)
     con un valor aleatorio por navegador si aun no existe.
  2. En los metodos que cambian datos (``POST``/``PUT``/``PATCH``/``DELETE``)
     de ``/api/v2`` se exige la cabecera ``X-CSRF-Token`` con el mismo valor.
     Si falta o no coincide -> ``403``.

Una web ajena no puede leer la cookie (misma politica de origen) ni, por tanto,
reproducir la cabecera, de modo que no puede forzar una escritura autenticada.

Se eximen:

  - ``GET``/``HEAD``/``OPTIONS`` (no cambian datos; ``OPTIONS`` es el preflight).
  - ``POST /api/v2/auth/login``: aun no hay cookie y no tiene efectos laterales
    sobre datos del usuario.
  - Las rutas internas que llama el recolector o el servidor Node con la
    cabecera ``X-Internal-Token`` (``/telemetria/push`` e ``/internal/*``).
"""

from __future__ import annotations

import secrets

from starlette.responses import JSONResponse

from app.v2.config import settings

COOKIE = "csrf_token"
CABECERA = "X-CSRF-Token"
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}

# Rutas que no pasan por el control: el login (todavia no hay cookie) y la
# ingesta del recolector (llega con X-Internal-Token, no desde un navegador).
RUTAS_EXENTAS = {"/api/v2/auth/login", "/api/v2/telemetria/push"}

# Prefijos de rutas internas (Node <-> FastAPI), protegidas por token interno.
PREFIJOS_INTERNOS = ("/api/v2/internal/",)


def _exenta(request) -> bool:
    """True si la peticion no necesita validar el token CSRF."""
    if request.method in METODOS_SEGUROS:
        return True

    ruta = request.url.path
    if ruta in RUTAS_EXENTAS or ruta.startswith(PREFIJOS_INTERNOS):
        return True

    # Llamadas internas (recolector/Node): llegan con el token compartido, no
    # desde un navegador, asi que no son vulnerables a CSRF.
    esperado = settings.internal_token
    if esperado and request.headers.get("X-Internal-Token") == esperado:
        return True

    return False


def _poner_cookie(respuesta, request) -> None:
    """Emite la cookie del token CSRF cuando aun no existe."""
    respuesta.set_cookie(
        COOKIE,
        secrets.token_urlsafe(32),
        path="/",
        samesite="lax",
        secure=request.url.scheme == "https",
        httponly=False,  # el frontend debe poder leerla para el doble-envio
    )


async def proteger_csrf(request, call_next):
    """Valida el doble-envio y emite la cookie cuando falta."""
    falta_cookie = COOKIE not in request.cookies

    if not _exenta(request):
        cookie = request.cookies.get(COOKIE)
        cabecera = request.headers.get(CABECERA)
        if not cookie or not cabecera or not secrets.compare_digest(cookie, cabecera):
            # Se emite una cookie nueva para que el cliente pueda reintentar.
            respuesta = JSONResponse(
                {"detail": "Token CSRF ausente o invalido."},
                status_code=403,
            )
            if falta_cookie:
                _poner_cookie(respuesta, request)
            return respuesta

    respuesta = await call_next(request)
    if falta_cookie:
        _poner_cookie(respuesta, request)
    return respuesta
