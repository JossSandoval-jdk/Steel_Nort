"""Middleware de RATE LIMIT (por IP).

Limita el numero de requests por IP dentro de una ventana fija
(``settings.rate_limit_max`` requests cada ``settings.rate_limit_window_seconds``
segundos). Superado el limite devuelve 429 con ``Retry-After``.

Implementacion en memoria (token bucket simplificado) adecuada para un
backend de un solo proceso. Rutas excluidas (health probes) se listan en
``settings.rate_limit_skip``.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Control de trafico por IP con ventana fija."""

    def __init__(self, app):
        super().__init__(app)
        self._contadores: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _ruta_excluida(self, ruta: str) -> bool:
        for prefijo in settings.rate_limit_skip_list:
            if ruta == prefijo or ruta.startswith(prefijo.rstrip("/") + "/"):
                return True
        return False

    async def dispatch(self, request: Request, call_next):
        if self._ruta_excluida(request.url.path):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        ventana = settings.rate_limit_window_seconds
        limite = settings.rate_limit_max

        with self._lock:
            marcas = [t for t in self._contadores.get(ip, []) if now - t < ventana]
            if len(marcas) >= limite:
                espera = max(1, int(ventana - (now - marcas[0])))
                self._contadores[ip] = marcas
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Demasiadas peticiones. Espera a que se renueve la ventana.",
                    },
                    headers={"Retry-After": str(espera)},
                )
            marcas.append(now)
            self._contadores[ip] = marcas

        return await call_next(request)