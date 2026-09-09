"""Inicializacion del usuario administrador (seed).

Garantiza que exista al menos un usuario con rol Administrador para
poder iniciar sesion la primera vez. Es idempotente: si ya hay usuarios
en la tabla, no hace nada.

Los datos del admin se leen de la configuracion (``.env``) para que el
operador pueda cambiarlos sin tocar el codigo.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.model_usuario import Usuarios
from app.security import hash_password


def seed_admin_if_empty(db: Session) -> None:
    """Crea el admin inicial solo si la tabla Usuarios esta vacia."""
    count = db.scalar(select(func.count()).select_from(Usuarios))
    if count and count > 0:
        return

    admin = Usuarios(
        usu_nom=settings.seed_admin_nombre,
        usu_ema=settings.seed_admin_email,
        usu_pwd=hash_password(settings.seed_admin_password),
        usu_rol=settings.seed_admin_rol,
        usu_ini=settings.seed_admin_iniciales,
        usu_act=True,
        fec_reg=datetime.now(timezone.utc),
    )
    db.add(admin)
    db.commit()