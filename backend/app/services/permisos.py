"""Reglas de permisos derivadas de la base de datos.

Los permisos efectivos de cada usuario provienen de las tablas
Roles, Permisos y Rol_Permiso. Si la BD aún no está sembrada o no
es accesible, se usa una matriz por defecto para no romper la API
durante el primer arranque (antes del seed).

Permisos disponibles (formato modulo:accion):
  - usuarios:leer|crear|editar|eliminar
  - roles:leer|crear|editar|eliminar
  - permisos:crear
  - ml:reentrenar
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.model_rol_permiso import Permisos, RolPermiso, Roles
from app.models.model_usuario import Usuarios

log = logging.getLogger("steelnort.permisos")

# Matriz por defecto usada SOLO como respaldo si la BD no está sembrada.
PERMISOS_POR_ROL_DEFAULT: dict[str, frozenset[str]] = {
    "Administrador": frozenset({
        "usuarios:leer",
        "usuarios:crear",
        "usuarios:editar",
        "usuarios:eliminar",
        "roles:leer",
        "roles:crear",
        "roles:editar",
        "roles:eliminar",
        "permisos:crear",
        "ml:reentrenar",
    }),
    "Supervisor": frozenset({
        "usuarios:leer",
        "roles:leer",
    }),
    "Operador": frozenset(),
}


def _permisos_desde_bd(db: Session, nombre_rol: str) -> frozenset[str]:
    """Consulta los permisos efectivos de un rol en la BD."""
    filas = (
        db.query(Permisos.prm_clave)
        .join(RolPermiso, RolPermiso.rp_prm == Permisos.prm_cod)
        .join(Roles, Roles.rol_cod == RolPermiso.rp_rol)
        .filter(
            Roles.rol_nom == nombre_rol,
            Roles.fec_eli.is_(None),
            Roles.rol_act == True,
            Permisos.fec_eli.is_(None),
            Permisos.prm_act == True,
        )
        .all()
    )
    return frozenset(clave for (clave,) in filas)


def permisos_del_usuario(usuario: Usuarios, db: Session | None = None) -> list[str]:
    """Devuelve los permisos efectivos del usuario actual.

    - Si se pasa db, consulta la tabla de permisos.
    - Si no, cae a la matriz por defecto (respaldo).
    """
    if db is not None:
        try:
            permisos = _permisos_desde_bd(db, usuario.usu_rol)
            if permisos:
                return sorted(permisos)
            # Rol sin filas en Roles (no sembrado): usar matriz por defecto.
        except Exception:
            log.warning("Error leyendo permisos de la BD; usando matriz por defecto.", exc_info=True)

    return sorted(PERMISOS_POR_ROL_DEFAULT.get(usuario.usu_rol, frozenset()))


def require_permission(permiso: str) -> Callable:
    """Crea una dependencia FastAPI que exige un permiso concreto."""
    from app.routers.auth import get_current_user

    def dependency(
        usuario: Usuarios = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Usuarios:
        if permiso not in permisos_del_usuario(usuario, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta accion.",
            )
        return usuario

    return dependency


def matriz_permisos(db: Session | None = None) -> dict[str, list[str]]:
    """Devuelve la matriz rol → permisos para el frontend.

    Consulta la BD; si no está disponible, usa la matriz por defecto.
    """
    try:
        if db is not None:
            filas = (
                db.query(Roles.rol_nom, Permisos.prm_clave)
                .join(RolPermiso, RolPermiso.rp_rol == Roles.rol_cod)
                .join(Permisos, Permisos.prm_cod == RolPermiso.rp_prm)
                .filter(
                    Roles.fec_eli.is_(None),
                    Roles.rol_act == True,
                    Permisos.fec_eli.is_(None),
                    Permisos.prm_act == True,
                )
                .all()
            )
            if filas:
                agrupado: dict[str, list[str]] = {}
                for nombre_rol, clave in filas:
                    agrupado.setdefault(nombre_rol, []).append(clave)
                if agrupado:
                    return {k: sorted(v) for k, v in agrupado.items()}
    except Exception:
        log.warning("Error leyendo matriz de permisos de la BD; usando matriz por defecto.", exc_info=True)

    return {rol: sorted(permisos) for rol, permisos in PERMISOS_POR_ROL_DEFAULT.items()}