"""Rutas de ACCESO: usuarios, roles, permisos, asignaciones y sesiones.

Cada ruta declara su permiso: leer, crear, editar o eliminar del modulo
``acceso``. Para anadir una tabla nueva basta con copiar un bloque de aqui.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.v2.models.acceso import Usuario
from app.v2.schemas.acceso import (
    PermisoCreate,
    PermisoOut,
    RolCreate,
    RolOut,
    RolPermisoCreate,
    RolPermisoOut,
    SesionOut,
    UsuarioCreate,
    UsuarioOut,
    UsuarioUpdate,
)
from app.v2.schemas.comun import Mensaje, Pagina
from app.v2.seguridad import Sesion, requiere_permiso
from app.v2.services import acceso

router = APIRouter(prefix="/acceso", tags=["acceso"])


# =====================================================================
# USUARIOS
# =====================================================================


@router.get("/usuarios", response_model=Pagina[UsuarioOut], summary="Listar usuarios")
def listar_usuarios(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("acceso:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("usu_cod"),
    con_bajas: bool = Query(False, description="Incluye los dados de baja"),
    estado: str | None = Query(None, pattern="^[AI]$"),
):
    return acceso.listar_usuarios(db, pagina, tamano, orden, con_bajas, estado)


@router.get("/usuarios/{cod}", response_model=UsuarioOut, summary="Ver un usuario")
def obtener_usuario(cod: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("acceso:leer"))]):
    return acceso.obtener_usuario(db, cod)


@router.post("/usuarios", response_model=UsuarioOut, status_code=201, summary="Crear usuario")
def crear_usuario(
    datos: UsuarioCreate,
    db: Sesion,
    actor: Annotated[Usuario, Depends(requiere_permiso("acceso:crear"))],
):
    return acceso.crear_usuario(db, datos, actor.usu_cod)


@router.patch("/usuarios/{cod}", response_model=UsuarioOut, summary="Editar usuario")
def actualizar_usuario(
    cod: int, datos: UsuarioUpdate, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("acceso:editar"))]
):
    return acceso.actualizar_usuario(db, cod, datos, actor.usu_cod)


@router.delete("/usuarios/{cod}", response_model=Mensaje, summary="Dar de baja un usuario")
def eliminar_usuario(cod: int, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("acceso:eliminar"))]):
    acceso.eliminar_usuario(db, cod, actor.usu_cod)
    return {"detalle": f"Usuario {cod} dado de baja"}


# =====================================================================
# ROLES
# =====================================================================


@router.get("/roles", response_model=Pagina[RolOut], summary="Listar roles")
def listar_roles(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("acceso:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("rol_nom"),
    con_bajas: bool = Query(False),
    estado: str | None = Query(None, pattern="^[AI]$"),
):
    return acceso.listar_roles(db, pagina, tamano, orden, con_bajas, estado)


@router.post("/roles", response_model=RolOut, status_code=201, summary="Crear rol")
def crear_rol(datos: RolCreate, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("acceso:crear"))]):
    return acceso.crear_rol(db, datos, actor.usu_cod)


@router.delete("/roles/{cod}", response_model=Mensaje, summary="Dar de baja un rol")
def eliminar_rol(cod: int, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("acceso:eliminar"))]):
    acceso.eliminar_rol(db, cod, actor.usu_cod)
    return {"detalle": f"Rol {cod} dado de baja"}


# =====================================================================
# PERMISOS
# =====================================================================


@router.get("/permisos", response_model=Pagina[PermisoOut], summary="Listar permisos")
def listar_permisos(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("acceso:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(100, ge=1, le=500),
    orden: str = Query("per_mod,per_acc"),
    con_bajas: bool = Query(False),
    modulo: str | None = Query(None, description="Filtra por modulo"),
):
    return acceso.listar_permisos(db, pagina, tamano, orden, con_bajas, modulo)


@router.post("/permisos", response_model=PermisoOut, status_code=201, summary="Crear permiso")
def crear_permiso(
    datos: PermisoCreate, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("acceso:crear"))]
):
    return acceso.crear_permiso(db, datos, actor.usu_cod)


# =====================================================================
# ASIGNACION DE PERMISOS A ROLES
# =====================================================================


@router.get("/roles-permisos", response_model=Pagina[RolPermisoOut], summary="Listar asignaciones")
def listar_roles_permisos(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("acceso:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(100, ge=1, le=500),
    orden: str = Query("rp_cod"),
    rol_cod: int | None = Query(None),
):
    return acceso.listar_roles_permisos(db, pagina, tamano, orden, rol_cod)


@router.post("/roles-permisos", response_model=RolPermisoOut, status_code=201, summary="Asignar permiso a un rol")
def asignar_permiso(
    datos: RolPermisoCreate, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("acceso:crear"))]
):
    return acceso.asignar_permiso(db, datos.rol_cod, datos.per_cod, actor.usu_cod)


@router.delete("/roles-permisos/{cod}", response_model=Mensaje, summary="Quitar permiso de un rol")
def quitar_permiso(cod: int, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("acceso:eliminar"))]):
    acceso.quitar_permiso(db, cod, actor.usu_cod)
    return {"detalle": f"Asignacion {cod} dada de baja"}


# =====================================================================
# SESIONES
# =====================================================================


@router.get("/sesiones", response_model=Pagina[SesionOut], summary="Listar sesiones")
def listar_sesiones(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("acceso:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("-ses_fec_ini"),
    usuario: int | None = Query(None, description="Codigo de usuario (ses_usu)"),
    estado: str | None = Query(None, pattern="^[ACE]$"),
):
    return acceso.listar_sesiones(db, pagina, tamano, orden, usuario, estado)