"""Rutas de NOTIFICACIONES: campanita, historial y push.

El usuario ve:
  - las globales (``not_usu_dest IS NULL``)
  - las dirigidas a su ``usu_cod``

Marcar como leída cambia el estado global. Las notificaciones se crean
solas por trigger cuando se abre una alerta C/A.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from app.v2.models.acceso import Usuario
from app.v2.schemas.comun import Mensaje, Pagina
from app.v2.schemas.notificaciones import (
    ContadorNotificaciones,
    NotificacionOut,
    PushSuscripcionIn,
    PushSuscripcionOut,
)
from app.v2.seguridad import Sesion, usuario_actual
from app.v2.services import notificaciones as servicio

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


# =====================================================================
# LISTAR Y CONTAR
# =====================================================================


@router.get("", response_model=Pagina[NotificacionOut], summary="Listar mis notificaciones")
def listar(
    db: Sesion,
    actor: Annotated[Usuario, Depends(usuario_actual)],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=200),
    solo_no_leidas: bool = Query(False, description="Solo las no leídas"),
    severidad: str | None = Query(None, pattern="^[CAMB]$"),
):
    return servicio.listar(
        db,
        actor.usu_cod,
        pagina=pagina,
        tamano=tamano,
        solo_no_leidas=solo_no_leidas,
        severidad=severidad,
    )


@router.get("/contador", response_model=ContadorNotificaciones, summary="Contador de no leídas")
def contador(
    db: Sesion,
    actor: Annotated[Usuario, Depends(usuario_actual)],
):
    return {"no_leidas": servicio.contador_no_leidas(db, actor.usu_cod)}


# =====================================================================
# MARCAR LEÍDAS
# =====================================================================


@router.patch("/{cod}/leer", response_model=NotificacionOut, summary="Marcar una como leída")
def marcar_leida(
    cod: int,
    db: Sesion,
    actor: Annotated[Usuario, Depends(usuario_actual)],
):
    return servicio.marcar_leida(db, cod, actor.usu_cod)


@router.patch("/leer-todas", response_model=Mensaje, summary="Marcar todas como leídas")
def marcar_todas(
    db: Sesion,
    actor: Annotated[Usuario, Depends(usuario_actual)],
):
    cantidad = servicio.marcar_todas_leidas(db, actor.usu_cod)
    return {"detalle": f"{cantidad} notificaciones marcadas como leídas"}


# =====================================================================
# PUSH SUSCRIPCIONES
# =====================================================================


@router.post(
    "/push/suscribir",
    response_model=PushSuscripcionOut,
    status_code=201,
    summary="Registrar suscripción push del navegador",
)
def suscribir_push(
    datos: PushSuscripcionIn,
    db: Sesion,
    actor: Annotated[Usuario, Depends(usuario_actual)],
    user_agent: Annotated[str | None, Header(alias="User-Agent")] = None,
):
    return servicio.suscribir(
        db,
        usu_cod=actor.usu_cod,
        endpoint=datos.endpoint,
        keys=datos.keys,
        user_agent=user_agent,
    )


@router.delete(
    "/push/desuscribir",
    response_model=Mensaje,
    summary="Eliminar suscripción push del navegador",
)
def desuscribir_push(
    endpoint: str,
    db: Sesion,
    actor: Annotated[Usuario, Depends(usuario_actual)],
):
    servicio.desuscribir(db, actor.usu_cod, endpoint)
    return {"detalle": "Suscripción desactivada"}