"""Middleware de LOGGER de requests.

Registra en ``steelnort.http`` cada request que atraviesa la API:
metodo, ruta, status, duracion y la IP del cliente (respetando proxy).
Nunca interfiere con la respuesta: solo observa.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = logging.getLogger("steelnort.http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Anota cada request saliente a nivel INFO."""

    async def dispatch(self, request: Request, call_next):
        inicio = time.perf_counter()

        ip = request.client.host if request.client else "-"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()

        response = await call_next(request)
        duracion_ms = (time.perf_counter() - inicio) * 1000

        log.info(
            "%s %s -> %s %.1fms ip=%s",
            request.method,
            request.url.path,
            response.status_code,
            duracion_ms,
            ip,
        )
        return response