"""Rutas de NODOS: instancias vigiladas y conexiones observadas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.v2.models.acceso import Usuario
from app.v2.schemas.comun import Mensaje, Pagina
from app.v2.schemas.nodos import (
    InstanciaCreate,
    InstanciaOut,
    InstanciaUpdate,
    SesionSQLOut,
)
from app.v2.seguridad import Sesion, requiere_permiso
from app.v2.services import nodos

router = APIRouter(prefix="/nodos", tags=["nodos"])


# =====================================================================
# INSTANCIAS
# =====================================================================


@router.get("/instancias", response_model=Pagina[InstanciaOut], summary="Listar instancias")
def listar_instancias(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("nodos:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("ins_nom"),
    con_bajas: bool = Query(False),
    estado: str | None = Query(None, pattern="^[AI]$"),
):
    return nodos.listar_instancias(db, pagina, tamano, orden, con_bajas, estado)


@router.get("/instancias/{cod}", response_model=InstanciaOut, summary="Ver una instancia")
def obtener_instancia(cod: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("nodos:leer"))]):
    return nodos.obtener_instancia(db, cod)


@router.post("/instancias", response_model=InstanciaOut, status_code=201, summary="Registrar instancia")
def crear_instancia(
    datos: InstanciaCreate, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("nodos:crear"))]
):
    return nodos.crear_instancia(db, datos, actor.usu_cod)


@router.patch("/instancias/{cod}", response_model=InstanciaOut, summary="Editar instancia")
def actualizar_instancia(
    cod: int, datos: InstanciaUpdate, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("nodos:editar"))]
):
    return nodos.actualizar_instancia(db, cod, datos, actor.usu_cod)


@router.delete("/instancias/{cod}", response_model=Mensaje, summary="Dar de baja una instancia")
def eliminar_instancia(
    cod: int, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("nodos:eliminar"))]
):
    nodos.eliminar_instancia(db, cod, actor.usu_cod)
    return {"detalle": f"Instancia {cod} dada de baja"}


# =====================================================================
# CONEXIONES SQL
# =====================================================================


@router.get("/sesiones-sql", response_model=Pagina[SesionSQLOut], summary="Listar conexiones observadas")
def listar_sesiones_sql(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("nodos:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("-ssq_fec_ini"),
    instancia: int | None = Query(None, description="ins_cod"),
    estado: str | None = Query(None, pattern="^[AC]$"),
    desde: datetime | None = Query(None, description="ssq_fec_ini minima"),
    hasta: datetime | None = Query(None, description="ssq_fec_ini maxima"),
):
    return nodos.listar_sesiones_sql(db, pagina, tamano, orden, instancia, estado, desde, hasta)