"""Endpoints para gestionar roles y permisos del sistema.

  GET    /roles                  -> listar roles
  POST   /roles                  -> crear rol (Admin)
  PATCH  /roles/{rol_id}         -> editar rol (Admin)
  DELETE /roles/{rol_id}         -> eliminar rol (Admin)

  GET    /roles/permisos         -> listar catálogo de permisos
  POST   /roles/permisos         -> crear permiso (Admin)

  GET    /roles/{rol_id}/permisos -> permisos de un rol
  POST   /roles/{rol_id}/permisos -> asignar permisos (Admin)
  DELETE /roles/{rol_id}/permisos/{prm_id} -> quitar permiso (Admin)

Solo el rol Administrador puede gestionar roles y permisos.
"""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.model_rol_permiso import Permisos, RolPermiso, Roles
from app.models.model_usuario import Usuarios
from app.routers.auth import require_csrf
from app.schemas import (
    PermisoCreate,
    PermisoOut,
    RolCreate,
    RolOut,
    RolPermisosUpdate,
    RolUpdate,
)
from app.services.permisos import require_permission

router = APIRouter(prefix="/roles", tags=["roles"])
Db = Annotated[Session, Depends(get_db)]


# =====================================================================
# CATÁLOGO DE PERMISOS (rutas estáticas ANTES de las parametrizadas)
# =====================================================================

@router.get("/permisos", response_model=list[PermisoOut])
def listar_permisos(
    db: Db,
    _current: Annotated[Usuarios, Depends(require_permission("roles:leer"))],
) -> list[Permisos]:
    """Lista el catálogo completo de permisos disponibles."""
    return (
        db.query(Permisos)
        .filter(Permisos.prm_act == True, Permisos.fec_eli.is_(None))
        .order_by(Permisos.prm_mod, Permisos.prm_clave)
        .all()
    )


@router.post("/permisos", response_model=PermisoOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def crear_permiso(
    payload: PermisoCreate,
    db: Db,
    current: Annotated[Usuarios, Depends(require_permission("roles:crear"))],
) -> Permisos:
    """Crea un nuevo permiso en el catálogo."""
    existe = (
        db.query(Permisos)
        .filter(Permisos.prm_clave == payload.prm_clave, Permisos.fec_eli.is_(None))
        .first()
    )
    if existe:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un permiso con la clave '{payload.prm_clave}'.",
        )

    permiso = Permisos(
        prm_clave=payload.prm_clave,
        prm_nom=payload.prm_nom,
        prm_mod=payload.prm_mod,
        prm_act=True,
        reg_usu=current.usu_ema,
    )
    db.add(permiso)
    db.commit()
    db.refresh(permiso)
    return permiso


# =====================================================================
# ROLES
# =====================================================================

@router.get("", response_model=list[RolOut])
def listar_roles(
    db: Db,
    _current: Annotated[Usuarios, Depends(require_permission("roles:leer"))],
) -> list[Roles]:
    """Lista todos los roles activos."""
    return (
        db.query(Roles)
        .filter(Roles.rol_act == True, Roles.fec_eli.is_(None))
        .order_by(Roles.rol_nom)
        .all()
    )


@router.post("", response_model=RolOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def crear_rol(
    payload: RolCreate,
    db: Db,
    current: Annotated[Usuarios, Depends(require_permission("roles:crear"))],
) -> Roles:
    """Crea un nuevo rol."""
    existe = (
        db.query(Roles)
        .filter(Roles.rol_nom == payload.rol_nom, Roles.fec_eli.is_(None))
        .first()
    )
    if existe:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un rol con el nombre '{payload.rol_nom}'.",
        )

    rol = Roles(
        rol_nom=payload.rol_nom,
        rol_desc=payload.rol_desc,
        rol_act=True,
        reg_usu=current.usu_ema,
    )
    db.add(rol)
    db.commit()
    db.refresh(rol)
    return rol


@router.patch("/{rol_id}", response_model=RolOut, dependencies=[Depends(require_csrf)])
def actualizar_rol(
    rol_id: int,
    payload: RolUpdate,
    db: Db,
    current: Annotated[Usuarios, Depends(require_permission("roles:editar"))],
) -> Roles:
    """Edita un rol existente."""
    rol = db.query(Roles).filter(Roles.rol_cod == rol_id, Roles.fec_eli.is_(None)).first()
    if not rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")

    if payload.rol_nom is not None:
        existe = (
            db.query(Roles)
            .filter(Roles.rol_nom == payload.rol_nom, Roles.rol_cod != rol_id, Roles.fec_eli.is_(None))
            .first()
        )
        if existe:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe un rol con el nombre '{payload.rol_nom}'.",
            )
        rol.rol_nom = payload.rol_nom

    if payload.rol_desc is not None:
        rol.rol_desc = payload.rol_desc
    if payload.rol_act is not None:
        rol.rol_act = payload.rol_act

    db.commit()
    db.refresh(rol)
    return rol


@router.delete("/{rol_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[Depends(require_csrf)])
def eliminar_rol(
    rol_id: int,
    db: Db,
    current: Annotated[Usuarios, Depends(require_permission("roles:eliminar"))],
) -> None:
    """Elimina lógicamente un rol (baja lógica)."""
    rol = db.query(Roles).filter(Roles.rol_cod == rol_id, Roles.fec_eli.is_(None)).first()
    if not rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")

    usuarios_con_rol = (
        db.query(Usuarios)
        .filter(Usuarios.usu_rol == rol.rol_nom, Usuarios.fec_eli.is_(None))
        .count()
    )
    if usuarios_con_rol > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede eliminar: hay {usuarios_con_rol} usuario(s) con este rol.",
        )

    rol.eli_usu = current.usu_ema
    rol.fec_eli = datetime.datetime.utcnow()
    rol.rol_act = False
    db.commit()


# =====================================================================
# PERMISOS DE UN ROL
# =====================================================================

@router.get("/{rol_id}/permisos", response_model=list[PermisoOut])
def obtener_permisos_rol(
    rol_id: int,
    db: Db,
    _current: Annotated[Usuarios, Depends(require_permission("roles:leer"))],
) -> list[Permisos]:
    """Lista los permisos asignados a un rol."""
    rol = db.query(Roles).filter(Roles.rol_cod == rol_id, Roles.fec_eli.is_(None)).first()
    if not rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")

    return (
        db.query(Permisos)
        .join(RolPermiso, RolPermiso.rp_prm == Permisos.prm_cod)
        .filter(RolPermiso.rp_rol == rol_id, Permisos.prm_act == True, Permisos.fec_eli.is_(None))
        .order_by(Permisos.prm_clave)
        .all()
    )


@router.post("/{rol_id}/permisos", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def asignar_permisos(
    rol_id: int,
    payload: RolPermisosUpdate,
    db: Db,
    current: Annotated[Usuarios, Depends(require_permission("roles:editar"))],
) -> dict:
    """Asigna permisos a un rol (reemplaza las asignaciones existentes)."""
    rol = db.query(Roles).filter(Roles.rol_cod == rol_id, Roles.fec_eli.is_(None)).first()
    if not rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")

    permisos = (
        db.query(Permisos)
        .filter(Permisos.prm_cod.in_(payload.prm_ids), Permisos.prm_act == True, Permisos.fec_eli.is_(None))
        .all()
    )
    encontrados = {p.prm_cod for p in permisos}
    faltantes = set(payload.prm_ids) - encontrados
    if faltantes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Permisos no encontrados: {sorted(faltantes)}",
        )

    db.query(RolPermiso).filter(RolPermiso.rp_rol == rol_id).delete()

    for prm_id in payload.prm_ids:
        db.add(RolPermiso(rp_rol=rol_id, rp_prm=prm_id, reg_usu=current.usu_ema))

    db.commit()
    return {"mensaje": f"Permisos asignados al rol '{rol.rol_nom}'.", "cantidad": len(payload.prm_ids)}


@router.delete("/{rol_id}/permisos/{prm_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[Depends(require_csrf)])
def quitar_permiso(
    rol_id: int,
    prm_id: int,
    db: Db,
    current: Annotated[Usuarios, Depends(require_permission("roles:editar"))],
) -> None:
    """Quita un permiso específico de un rol."""
    rol = db.query(Roles).filter(Roles.rol_cod == rol_id, Roles.fec_eli.is_(None)).first()
    if not rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")

    asignacion = (
        db.query(RolPermiso)
        .filter(RolPermiso.rp_rol == rol_id, RolPermiso.rp_prm == prm_id)
        .first()
    )
    if not asignacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El permiso no está asignado a este rol.",
        )

    db.delete(asignacion)
    db.commit()