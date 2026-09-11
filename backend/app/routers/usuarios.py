"""Endpoints basicos para gestionar usuarios y sus permisos por rol."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.model_usuario import Usuarios
from app.routers.auth import get_current_user, require_csrf
from app.schemas import PermisosOut, UsuarioCreate, UsuarioOut, UsuarioUpdate
from app.services.permisos import matriz_permisos, permisos_del_usuario, require_permission
from app.services.usuarios import actualizar_usuario, crear_usuario, eliminar_usuario, listar_usuarios

router = APIRouter(prefix="/usuarios", tags=["usuarios"])
Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[UsuarioOut])
def obtener_usuarios(
    db: Db,
    _current: Annotated[Usuarios, Depends(require_permission("usuarios:leer"))],
) -> list[Usuarios]:
    return listar_usuarios(db)


@router.get("/roles/permisos", response_model=PermisosOut)
def obtener_permisos(
    db: Db,
    _current: Annotated[Usuarios, Depends(require_permission("roles:leer"))],
) -> PermisosOut:
    return PermisosOut(roles=matriz_permisos(db))


@router.get("/me/permisos", response_model=list[str])
def mis_permisos(current: Annotated[Usuarios, Depends(get_current_user)], db: Db) -> list[str]:
    return permisos_del_usuario(current, db)


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def crear(
    payload: UsuarioCreate,
    db: Db,
    current: Annotated[Usuarios, Depends(require_permission("usuarios:crear"))],
) -> Usuarios:
    return crear_usuario(db, payload, current)


@router.patch("/{usuario_id}", response_model=UsuarioOut, dependencies=[Depends(require_csrf)])
def actualizar(
    usuario_id: int,
    payload: UsuarioUpdate,
    db: Db,
    current: Annotated[Usuarios, Depends(require_permission("usuarios:editar"))],
) -> Usuarios:
    return actualizar_usuario(db, usuario_id, payload, current)


@router.delete(
    "/{usuario_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def eliminar(
    usuario_id: int,
    db: Db,
    current: Annotated[Usuarios, Depends(require_permission("usuarios:eliminar"))],
) -> None:
    eliminar_usuario(db, usuario_id, current)