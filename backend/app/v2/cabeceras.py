"""Cabeceras de seguridad para todas las respuestas de la API v2.

Endurecimiento basico contra el sniffing de tipos, el enmarcado de la pagina en
otro sitio (clickjacking) y la fuga del referer. La capa Node (produccion) ya
usa Helmet; esto cubre lo que sale directo de FastAPI.
"""

from __future__ import annotations

from fastapi import Request

CABECERAS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


async def poner_cabeceras(request: Request, call_next):
    """Agrega las cabeceras de seguridad a la respuesta."""
    respuesta = await call_next(request)
    for nombre, valor in CABECERAS.items():
        respuesta.headers[nombre] = valor
    return respuesta
