"""Servicios de seguridad: hash de claves, JWT y tokens CSRF.

Centraliza toda la logica de criptografia y validacion de tokens para
que los routers solo consuman funciones limpias. Estas funciones son
reutilizables por cualquier modulo futuro (reset de clave, refresh
token, etc.).

Estrategia de doble token (ver plan):
  - ``access_token`` (JWT): identifica al usuario autenticado. Se usa
    en el header ``Authorization: Bearer <token>``. En el frontend se
    mantiene en memoria.
  - ``csrf_token`` (opaco): se emite en el login, se envia como cookie
    ``csrf_token`` y tambien en la respuesta. El frontend lo guarda en
    localStorage y debe enviarlo de vuelta en el header ``X-CSRF-Token``
    para cada request protegido. El backend verifica que el valor del
    header sea IGUAL al de la cookie (mecanismo de doble coincidencia
    que evita requests forjados / tokens corruptos).
"""

from __future__ import annotations

import secrets
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


# ---------------------------------------------------------------------
# CSRF TOKEN (doble coincidencia)
# ---------------------------------------------------------------------


def generate_csrf_token() -> str:
    """Genera un token CSRF opaco (secreto) nuevo."""
    return secrets.token_urlsafe(32)


def csrf_is_valid(cookie_token: str | None, header_token: str | None) -> bool:
    """Valida que el token del header coincida con el de la cookie.

    Ambos deben estar presentes y ser exactamente iguales. De lo
    contrario se considera no valido (evita requests forjados y tokens
    modificados en el almacenamiento).
    """
    if not cookie_token or not header_token:
        return False
    # Comparacion en tiempo constante para evitar ataques de timing.
    return secrets.compare_digest(cookie_token, header_token)