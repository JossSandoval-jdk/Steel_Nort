"""Rutas de metricas del sistema (CPU y memoria RAM).

Expone el estado en tiempo real de la maquina donde corre el backend:
  - GET /metrics/sistema     -> estado puntual (tarjetas "en vivo").
  - GET /metrics/historial   -> serie temporal en memoria (graficos).

Las rutas estan protegidas: requieren un JWT valido (header Bearer).
Al consultar cada endpoint se registra una nueva muestra en el historial
en memoria, de modo que el grafico se alimenta de forma natural.

No se persiste nada en la BD (regla SteelNort: sin telemetria cruda).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.routers.auth import get_current_user
from app.services.sistema import get_snapshot, historial

router = APIRouter(prefix="/metrics", tags=["metrics"])

# Dependencia de autenticacion tipada para inyectar el usuario actual.
UsuarioActual = Annotated[object, Depends(get_current_user)]


@router.get("/sistema")
def metricas_sistema(_current: UsuarioActual) -> dict:
    """Estado puntual de CPU y RAM de la maquina.

    Lee metricas reales con psutil, registra la muestra en el historial
    (para alimentar el grafico) y devuelve los valores actuales.
    """
    muestra = get_snapshot()
    historial.agregar(muestra)
    return {
        "ts": muestra["ts"],
        "cpu": {
            "total": muestra["cpu"]["total"],
            "nucleos": muestra["cpu"]["nucleos"],
            "conteo": len(muestra["cpu"]["nucleos"]),
        },
        "mem": muestra["mem"],
    }


@router.get("/historial")
def metricas_historial(
    _current: UsuarioActual,
    n: Annotated[int | None, Query(ge=1, le=1000)] = None,
) -> dict:
    """Serie temporal de CPU y RAM (ultimas ``n`` muestras).

    ``n`` por defecto devuelve todas las muestras acumuladas. El historial
    vive en memoria y se reinicia al reiniciar la API.
    """
    muestras = historial.serie(n)
    return {
        "count": len(muestras),
        "serie": muestras,
    }