"""Endpoints del monitor de deriva (Etapa 2 Anti-Drift).

  GET  /drift/estado   -> estado del ultimo analisis de deriva.
  POST /drift/revisar  -> fuerza una revision inmediata.

El monitor NO reentrena: solo marca la recomendacion para el equipo.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.routers.auth import get_current_user
from app.services.drift import estado_drift, fuerza_revision

log = logging.getLogger("steelnort.drift_api")

router = APIRouter(prefix="/drift", tags=["drift"])

UsuarioActual = Annotated[object, Depends(get_current_user)]


@router.get("/estado")
def obtener_estado_drift(_current: UsuarioActual) -> dict:
    """Estado del ultimo analisis de deriva vs baseline de entrenamiento."""
    return estado_drift()


@router.post("/revisar")
def revisar_ahora(_current: UsuarioActual) -> dict:
    """Ejecuta una revision de deriva inmediata."""
    return fuerza_revision()