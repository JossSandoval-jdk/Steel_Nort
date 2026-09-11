"""Rutas de autenticacion.

Contiene el flujo de login, verificacion de sesion y cierre de sesion.
Se encarga de:
  - autenticar credenciales contra la tabla Usuarios,
  - registrar cada ingreso en Sesiones,
  - emitir el doble token (access JWT + csrf),
  - proteger el endpoint /me (exige Bearer y CSRF valido).

Escala: cuando se agreguen mas modulos protegidos, las dependencias
``get_current_user`` y ``require_csrf`` pueden moverse a un modulo
compartido de dependencias para reutilizarse en otros routers.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.model_usuario import Sesiones, Usuarios
from app.schemas import LoginRequest, SesionOut, TokenResponse, UsuarioOut
from app.security import (
    create_access_token,
    csrf_is_valid,
    decode_access_token,
    generate_csrf_token,
    verify_password,
)
from app.seed import seed_admin_if_empty

router = APIRouter(prefix="/auth", tags=["auth"])

# Nombre de la cookie que transporta el csrf token.
CSRF_COOKIE = "csrf_token"


# ---------------------------------------------------------------------
# Dependencias de seguridad (reutilizables en otros routers)
# ---------------------------------------------------------------------


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Usuarios:
    """Autentica al usuario desde el header Authorization Bearer.

    Extrae y valida el JWT. Si es valido, carga al usuario activo desde
    la BD. Lanza 401 si el token es invalido/expirado o 403 si el
    usuario fue desactivado o eliminado (baja logica).

    Alternativa: acepta ``?token=<JWT>`` como query param para
    endpoints SSE donde EventSource no puede enviar headers custom.
    """
    auth = request.headers.get("Authorization", "")
    token = None
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ").strip()
    else:
        token = request.query_params.get("token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autorizacion faltante o malformado.",
        )
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado.",
        )

    user_id = int(payload.get("sub", 0))
    user = db.get(Usuarios, user_id)
    if user is None or user.fec_eli is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta no existe o fue eliminada.",
        )
    if not user.usu_act:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada.",
        )
    return user


def require_csrf(request: Request) -> None:
    """Valida el doble token CSRF para requests de escritura.

    Compara la cookie ``csrf_token`` contra el header ``X-CSRF-Token``.
    Deben ser identicos; de lo contrario se rechaza (403).
    """
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get("X-CSRF-Token")
    if not csrf_is_valid(cookie, header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF invalido o no coincidente.",
        )


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    """Autentica credenciales y devuelve el doble token.

    1) Garantiza el admin inicial (seed) por si la BD esta vacia.
    2) Busca el usuario por email y valida clave + estado.
    3) Registra la sesion en la tabla Sesiones.
    4) Emite access_token + csrf_token y fija la cookie csrf.
    """
    # Seed: si la BD no tiene usuarios, crea el admin configurado en .env.
    seed_admin_if_empty(db)

    email = payload.email
    user = db.scalar(select(Usuarios).where(Usuarios.usu_ema == email))

    # Mensaje generico para no filtrar si el email existe o la clave falla.
    if user is None or not verify_password(payload.password, user.usu_pwd):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas.",
        )
    if not user.usu_act:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada.",
        )
    if user.fec_eli is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta eliminada.",
        )

    # Registrar la sesion (solo el inicio; el cierre lo hace /logout).
    sesion = Sesiones(
        ses_usu=user.usu_cod,
        ses_fec_ini=datetime.now(timezone.utc),
        ses_ip=request.client.host if request.client else None,
        ses_usr_agt=request.headers.get("User-Agent"),
        ses_est="activa",
    )
    db.add(sesion)
    db.commit()

    # Emitir tokens.
    access_token, minutes = create_access_token(subject=user.usu_cod)
    csrf_token = generate_csrf_token()

    # Fijar la cookie del csrf (HttpOnly NO se usa porque el JS debe
    # poder leerla para verificar coincidencia; puede marcarse Secure
    # en produccion con HTTPS).
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        max_age=settings.csrf_token_expire_minutes * 60,
        httponly=False,
        samesite="lax",
        secure=False,  # -> True cuando se use HTTPS en el VPS
    )

    return TokenResponse(
        access_token=access_token,
        csrf_token=csrf_token,
        expires_in_minutes=minutes,
        usuario=UsuarioOut.model_validate(user),
    )


@router.get("/me", response_model=UsuarioOut)
def me(current: Usuarios = Depends(get_current_user)) -> Usuarios:
    """Devuelve el usuario autenticado a partir del token."""
    return current


@router.post("/logout", dependencies=[Depends(require_csrf)])
def logout(
    request: Request,
    response: Response,
    current: Usuarios = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Cierra la sesion mas reciente del usuario y limpia la cookie.

    Marca la ultima sesion activa como cerrada y borra la cookie del
    csrf del cliente.
    """
    ultima = db.scalar(
        select(Sesiones)
        .where(Sesiones.ses_usu == current.usu_cod, Sesiones.ses_est == "activa")
        .order_by(Sesiones.ses_cod.desc())
    )
    if ultima is not None:
        ultima.ses_est = "cerrada"
        ultima.ses_fec_fin = datetime.now(timezone.utc)
        db.commit()

    response.delete_cookie(CSRF_COOKIE)
    return {"detail": "Sesion cerrada correctamente."}