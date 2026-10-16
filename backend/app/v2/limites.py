"""Middleware de LIMITE de peticiones: responde 429 cuando un cliente se pasa.

Limite en memoria (ventana deslizante) por IP, sin dependencias nuevas. Se
apoya en la configuracion ``rate_limit_max`` / ``rate_limit_window_seconds``.
Es una red de seguridad global contra rafagas; el proxy Node mantiene ademas
su propio limite para el Web Push.

Para demostrar el 429 basta bajar ``V2_RATE_LIMIT_MAX`` en el ``.env`` (por
ejemplo a 5) y hacer una rafaga: la sexta peticion del mismo minuto responde
429 con la cabecera ``Retry-After``.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.responses import JSONResponse

from app.v2.config import settings

# IP -> marcas de tiempo (segundos monotonos) de sus ultimas peticiones.
_visitas: dict[str, deque] = defaultdict(deque)


def reiniciar() -> None:
    """Vacia el contador por IP (util para las pruebas)."""
    _visitas.clear()


async def limitar_peticion(request, call_next):
    """Corta la peticion con 429 si la IP supero el maximo en la ventana."""
    maximo = settings.rate_limit_max
    ventana = settings.rate_limit_window_seconds
    ip = request.client.host if request.client else "?"

    ahora = time.monotonic()
    marcas = _visitas[ip]
    while marcas and ahora - marcas[0] > ventana:
        marcas.popleft()

    if len(marcas) >= maximo:
        return JSONResponse(
            status_code=429,
            content={"detail": f"Demasiadas peticiones. Intente en {ventana} segundos."},
            headers={"Retry-After": str(ventana)},
        )

    marcas.append(ahora)
    return await call_next(request)
