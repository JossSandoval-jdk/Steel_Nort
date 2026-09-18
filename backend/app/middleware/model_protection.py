"""Middleware de PROTECCION de rutas del modelo ML.

Exige un JWT valido (header Authorization: Bearer o ``?token=``) para las
rutas sensibles del modelo, configuradas en
``settings.model_protect_prefixes``.

Es una capa de defensa adicional: la autorizacion fino-granular sigue
haciendose con las dependencias ``get_current_user`` /
``require_permission`` en cada endpoint. Rutas de salud y login quedan exentas.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.security import decode_access_token


class ModelProtectionMiddleware(BaseHTTPMiddleware):
    """Valida el JWT en acceso a las rutas protegidas del modelo."""

    async def dispatch(self, request: Request, call_next):
        ruta = request.url.path

        if not _ruta_protegida(ruta):
            return await call_next(request)

        token = _extraer_token(request)
        if token is None or decode_access_token(token) is None:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        "Se requiere token valido para acceder a esta ruta "
                        "del modelo ML."
                    )
                },
            )

        return await call_next(request)


def _ruta_protegida(ruta: str) -> bool:
    for prefijo in settings.model_protect_prefixes:
        if prefijo and ruta.startswith(prefijo):
            return True
    return False


def _extraer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.removeprefix("Bearer ").strip()
    token = request.query_params.get("token")
    return token.strip() if token else None