"""Middleware de la API SteelNort.

Agrupacion de middlewares transversales listos para registrar en
``app.main``:

  1. ``RequestLoggingMiddleware``  -> logger de cada request (metodo, path,
                                     status, duracion, IP).
  2. ``ProxyHeadersMiddleware``    -> respeta X-Forwarded-For/Proto cuando
                                     el backend va detras de un proxy.
  3. ``SecurityHeadersMiddleware`` -> headers de seguridad + limpiar
                                     cabecera ``server``.
  4. ``RateLimitMiddleware``       -> limite de requests por IP (429).
  5. ``ModelProtectionMiddleware`` -> exige JWT valido en rutas del modelo
                                     (reentrenamiento/despliegue).
"""

from app.middleware.model_protection import ModelProtectionMiddleware
from app.middleware.proxy_headers import ProxyHeadersMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

__all__ = [
    "ModelProtectionMiddleware",
    "ProxyHeadersMiddleware",
    "RateLimitMiddleware",
    "RequestLoggingMiddleware",
    "SecurityHeadersMiddleware",
]