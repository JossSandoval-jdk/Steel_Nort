"""Servicios de seguridad: hash de claves y JWT.

Centraliza la logica de criptografia y validacion de tokens para que los
routers solo consuman funciones limpias.

Diseno real (v2):
  - ``access_token`` (JWT): identifica al usuario autenticado. Viaja en la
    cabecera ``Authorization: Bearer <token>`` y el frontend lo mantiene
    **solo en memoria** (ni ``localStorage`` ni ``sessionStorage``).

  - CSRF: se protege con **doble-envio** (cookie ``csrf_token`` + cabecera
    ``X-CSRF-Token``), tal como se decidio en la revision de seguridad (S1-8).
    En este diseno el JWT viaja en una cabecera que una web ajena no puede
    agregar sola, asi que la superficie clasica de CSRF no existe; el
    doble-envio se agrega como **defensa en profundidad** (si algun dia las
    credenciales pasaran a cookies, el control ya esta en su sitio). El
    middleware vive en ``app/v2/csrf.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


# ---------------------------------------------------------------------
# HASH DE CONTRASENAS (bcrypt)
# ---------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Genera un hash bcrypt para una clave en texto plano."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica una clave en texto plano contra su hash bcrypt."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------
# ACCESS TOKEN (JWT)
# ---------------------------------------------------------------------


def create_access_token(subject: int, extra: dict | None = None) -> tuple[str, int]:
    """Genera un JWT firmado con expiracion.

    Devuelve ``(token, minutes)`` donde ``minutes`` es la vigencia en
    minutos (para que el frontend pueda mostrarlo si lo desea).
    """
    expire_minutes = settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
        "type": "access",
    }
    if extra:
        payload.update(extra)

    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token, expire_minutes


def decode_access_token(token: str) -> dict | None:
    """Decodifica y valida un JWT.

    Devuelve el payload si es valido y esta vigente, o ``None`` si la
    firma no coincide o el token expiro.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.PyJWTError:
        return None