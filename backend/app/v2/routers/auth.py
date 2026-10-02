"""Rutas de autenticacion: login, perfil y logout.

El login es por ``usu_log`` (no por correo), como en el esquema. El JWT lo
emite ``app.security``; aqui solo se orquestan usuario, sesion y permisos.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.v2.models.acceso import Rol
from app.v2.models.acceso import Sesion as SesionDB
from app.v2.schemas.acceso import TokenRespuesta, UsuarioOut
from app.v2.seguridad import Sesion, UsuarioActual
from app.v2.services import acceso

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    usuario: str = Field(min_length=1, max_length=50, examples=["admin"])
    clave: str = Field(min_length=1, max_length=72, examples=["Admin123!"])


@router.post("/login", response_model=TokenRespuesta, summary="Iniciar sesion")
def login(datos: LoginBody, request: Request, db: Sesion) -> TokenRespuesta:
    """Comprueba usuario y clave, abre la sesion y devuelve el JWT.

    En ``permisos`` van ya en formato ``modulo:accion``, que es lo que el
    backend comprueba en cada ruta. El Administrador lleva ``*:*`` porque
    puede hacerlo todo.
    """
    ip = request.client.host if request.client else None
    usuario, rol, token, minutos = acceso.autenticar(db, datos.usuario.strip(), datos.clave, ip)
    acceso.registrar_sesion(db, usuario.usu_cod, ip)

    return TokenRespuesta(
        access_token=token,
        expira_en_minutos=minutos,
        usuario=UsuarioOut.model_validate(usuario),
        rol=rol,
        permisos=mis_permisos_de(usuario.rol_cod, db),
    )


@router.get("/me", response_model=UsuarioOut, summary="Usuario del token")
def mi_usuario(usuario: UsuarioActual) -> UsuarioOut:
    """Cuenta autenticada; sirve para refrescar el perfil en el frontend."""
    return UsuarioOut.model_validate(usuario)


@router.get("/permisos", summary="Permisos efectivos del usuario actual")
def mis_permisos(usuario: UsuarioActual, db: Sesion) -> dict:
    rol = db.get(Rol, usuario.rol_cod)
    permisos = mis_permisos_de(usuario.rol_cod, db)
    return {
        "rol": rol.rol_nom if rol else "",
        "permisos": permisos,
        "administrador": "*:*" in permisos,
    }


@router.post("/logout", summary="Cerrar la sesion actual")
def logout(usuario: UsuarioActual, db: Sesion) -> dict:
    """Marca como cerrada la ultima sesion abierta del usuario."""
    abierta = db.scalars(
        select(SesionDB)
        .where(SesionDB.ses_usu == usuario.usu_cod, SesionDB.ses_est == "A")
        .order_by(SesionDB.ses_fec_ini.desc())
    ).first()
    if abierta is not None:
        acceso.cerrar_sesion(db, abierta.ses_cod)
    return {"detalle": "Sesion cerrada"}


def mis_permisos_de(rol_cod: int, db: Sesion) -> list[str]:
    """Permisos de un rol en formato ``modulo:accion`` (admin = ``*:*``)."""
    rol = db.get(Rol, rol_cod)
    if acceso.es_administrador(rol.rol_nom if rol else None):
        return ["*:*"]
    return acceso.permisos_del_rol(db, rol_cod)