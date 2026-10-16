"""Schemas de NOTIFICACIONES: campanita e historial.

``NotificacionOut`` es lo que ve el usuario; ``NotificacionCreate`` lo usa
el backend interno para crear notificaciones manuales. Las suscripciones
push se manejan con ``PushSuscripcionIn`` y ``PushSuscripcionOut``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.v2.schemas.comun import Salida


# =====================================================================
# NOTIFICACIONES
# =====================================================================


class NotificacionOut(Salida):
    """Notificación tal como la ve el cliente."""

    not_cod: int
    not_titulo: str
    not_detalle: str | None = None
    not_sev: str
    not_tipo: str | None = None
    not_ref_cod: int | None = None
    not_url: str | None = None
    not_leida: bool
    not_usu_dest: int | None = None
    fec_creacion: datetime
    fec_leida: datetime | None = None


class NotificacionCreate(BaseModel):
    """Payload interno para crear una notificación (no expuesto al cliente)."""

    not_titulo: str = Field(min_length=1, max_length=200)
    not_detalle: str | None = Field(default=None, max_length=500)
    not_sev: str = Field(pattern="^[CAMB]$")
    not_tipo: str | None = Field(default=None, max_length=50)
    not_ref_cod: int | None = None
    not_url: str | None = Field(default=None, max_length=200)
    not_usu_dest: int | None = None


class ContadorNotificaciones(BaseModel):
    """Solo el número de no leídas, para el badge de la campanita."""

    no_leidas: int


# =====================================================================
# PUSH SUSCRIPCIONES
# =====================================================================


class PushSuscripcionIn(BaseModel):
    """Lo que envía el navegador al suscribirse.

    Es exactamente el JSON que devuelve ``PushSubscription.toJSON()``:
    ``{ endpoint, keys: { p256dh, auth } }``.
    """

    endpoint: str = Field(min_length=10, max_length=500)
    keys: dict[str, str] = Field(description="Debe contener 'p256dh' y 'auth'")


class PushSuscripcionOut(Salida):
    """Respuesta al listar suscripciones (uso interno)."""

    psu_cod: int
    usu_cod: int
    psu_endpoint: str
    psu_activa: bool
    fec_creacion: datetime
    fec_ultimo_uso: datetime | None = None