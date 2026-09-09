"""Reglas basicas de permisos derivadas del rol almacenado en Usuarios."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.models.model_usuario import Usuarios

PERMISOS_POR_ROL: dict[str, frozenset[str]] = {
    "Administrador": frozenset({
        "usuarios:leer",
        "usuarios:crear",
        "usuarios:editar",
        "usuarios:eliminar",
        "permisos:leer",
    }),
    "Supervisor": frozenset({"usuarios:leer", "permisos:leer"}),
    "Operador": frozenset(),
}


def permisos_del_usuario(usuario: Usuarios) -> list[str]:
    """Devuelve los permisos efectivos del usuario actual."""
    return sorted(PERMISOS_POR_ROL.get(usuario.usu_rol, frozenset()))


def require_permission(permiso: str) -> Callable:
    """Crea una dependencia FastAPI que exige un permiso concreto."""
    from app.routers.auth import get_current_user

    def dependency(usuario: Usuarios = Depends(get_current_user)) -> Usuarios:
        if permiso not in PERMISOS_POR_ROL.get(usuario.usu_rol, frozenset()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta accion.",
            )
        return usuario

    return dependency