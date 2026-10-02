"""Autenticacion y permisos de v2.

Dos dependencias para los routers:

    usuario_actual   exige un JWT valido y devuelve la fila de ``usuario``.
    requiere_permiso exige ademas el permiso ``modulo:accion``.

El permiso sale de ``rol_permiso -> permiso`` y el rol Administrador lo tiene
todo por el nombre, sin depender de la tabla de asignaciones. Las acciones son
las cuatro del CRUD: ``leer``, ``crear``, ``editar`` y ``eliminar``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.security import decode_access_token
from app.v2.database import get_db
from app.v2.models.acceso import Rol, Usuario
from app.v2.services import crud
from app.v2.services.acceso import es_administrador, permisos_del_rol

# auto_error=False para responder nosotros con el mensaje en espanol.
bearer = HTTPBearer(auto_error=False, description="JWT del POST /auth/login")

Sesion = Annotated[Session, Depends(get_db)]
Credenciales = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def usuario_actual(db: Sesion, credenciales: Credenciales) -> Usuario:
    """Devuelve el usuario del token, o responde 401."""
    if credenciales is None or not credenciales.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de acceso",
            headers={"WWW-Authenticate": "Bearer"},
        )

    contenido = decode_access_token(credenciales.credentials)
    if contenido is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o vencido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    usuario = crud.obtener(db, Usuario, "usu_cod", int(contenido["sub"]))
    if usuario is None or usuario.usu_est != "A" or usuario.fec_eli is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El usuario del token ya no esta activo",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return usuario


def requiere_permiso(permiso: str):
    """Dependencia que exige ``permiso`` con formato ``modulo:accion``.

    Uso::

        @router.get("/", dependencies=[Depends(requiere_permiso("acceso:leer"))])
    """

    def _dependencia(db: Sesion, usuario: Annotated[Usuario, Depends(usuario_actual)]) -> Usuario:
        if not tiene_permiso(db, usuario, permiso):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tiene el permiso {permiso}",
            )
        return usuario

    return _dependencia


def tiene_permiso(db: Session, usuario: Usuario, permiso: str) -> bool:
    """True si el rol del usuario tiene ese permiso."""
    if usuario is None:
        return False
    rol = db.get(Rol, usuario.rol_cod)
    if es_administrador(rol.rol_nom if rol else None):
        return True
    return permiso in permisos_del_rol(db, usuario.rol_cod)


# Atajo para no repetir el tipo en cada firma de los routers.
UsuarioActual = Annotated[Usuario, Depends(usuario_actual)]