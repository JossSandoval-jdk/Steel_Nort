"""Middleware de SEGURIDAD (headers).

Agrega headers de seguridad estandar y borra la cabecera ``server``
para no revelar la tecnologia. HSTS solo se emite sobre HTTPS (el
backend local no la necesita y romperia ``http://localhost``).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Aplica los headers de seguridad sobre TODAS las respuestas."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        for nombre, valor in _HEADERS.items():
            response.headers[nombre] = valor

        if request.scope.get("scheme") == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # No revelar tecnologia del servidor.
        response.headers["server"] = ""

        return response