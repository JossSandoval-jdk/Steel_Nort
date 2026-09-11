"""Middleware de PROXY (truste de headers).

Cuando ``settings.trusted_proxy = True`` (el backend esta detras de
nginx/podman-gateway), confia en ``X-Forwarded-For`` y
``X-Forwarded-Proto`` para reescribir la IP y el esquema reales del
cliente. Si esta en False (arranque local/media), los headers de
forwarding se IGNORAN para no permitir suplantacion de IP.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings


class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    """Reescribe client/scheme del scope usando los headers de proxy."""

    async def dispatch(self, request: Request, call_next):
        if settings.trusted_proxy:
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                ip = forwarded_for.split(",")[0].strip()
                request.scope["client"] = (ip, request.client.port if request.client else 0)

            forwarded_proto = request.headers.get("X-Forwarded-Proto")
            if forwarded_proto:
                request.scope["scheme"] = forwarded_proto.strip().lower()

        return await call_next(request)