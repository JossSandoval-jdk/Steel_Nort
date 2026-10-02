"""Rutas de DATOS CRUDOS: metricas, eventos, logs SQL y carga agregada.

Las cuatro tablas son de solo lectura para el usuario. La escritura existe para
el collector: acepta una fila o una lista de filas con las columnas de la tabla
y las inserta en bloque (maximo 1000 por peticion).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.v2.models.acceso import Usuario
from app.v2.schemas.comun import Pagina
from app.v2.schemas.datos import EstadisticaCargaOut, EventoOut, LogSQLOut, MetricaOut
from app.v2.seguridad import Sesion, requiere_permiso
from app.v2.services import datos as servicio

router = APIRouter(prefix="/datos", tags=["datos"])


# =====================================================================
# METRICAS
# =====================================================================


@router.get("/metricas", response_model=Pagina[MetricaOut], summary="Listar metricas")
def listar_metricas(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("-met_fec"),
    instancia: int | None = Query(None, description="met_ins"),
    prediccion: int | None = Query(None, description="met_prd"),
    desde: datetime | None = Query(None, description="met_fec minima"),
    hasta: datetime | None = Query(None, description="met_fec maxima"),
):
    return servicio.listar_metricas(db, pagina, tamano, orden, instancia, prediccion, desde, hasta)


@router.get("/metricas/{cod}", response_model=MetricaOut, summary="Ver una metrica")
def obtener_metrica(cod: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))]):
    return servicio.obtener_metrica(db, cod)


@router.post("/metricas", status_code=201, summary="Registrar metricas (collector)")
def registrar_metricas(
    filas: dict | list[dict], db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("datos:crear"))]
):
    return servicio.registrar_metricas(db, filas)


# =====================================================================
# EVENTOS
# =====================================================================


@router.get("/eventos", response_model=Pagina[EventoOut], summary="Listar eventos")
def listar_eventos(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("-eve_fec"),
    instancia: int | None = Query(None, description="eve_ins"),
    prediccion: int | None = Query(None, description="eve_prd"),
    tipo: str | None = Query(None, description="eve_wait"),
    desde: datetime | None = Query(None, description="eve_fec minima"),
    hasta: datetime | None = Query(None, description="eve_fec maxima"),
):
    return servicio.listar_eventos(db, pagina, tamano, orden, instancia, prediccion, desde, hasta, tipo)


@router.get("/eventos/{cod}", response_model=EventoOut, summary="Ver un evento")
def obtener_evento(cod: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))]):
    return servicio.obtener_evento(db, cod)


@router.post("/eventos", status_code=201, summary="Registrar eventos (collector)")
def registrar_eventos(
    filas: dict | list[dict], db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("datos:crear"))]
):
    return servicio.registrar_eventos(db, filas)


# =====================================================================
# LOGS SQL
# =====================================================================


@router.get("/logs", response_model=Pagina[LogSQLOut], summary="Listar logs SQL")
def listar_logs(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("-lgs_fec"),
    instancia: int | None = Query(None, description="lgs_ins"),
    nivel: str | None = Query(None, description="lgs_niv"),
    desde: datetime | None = Query(None, description="lgs_fec minima"),
    hasta: datetime | None = Query(None, description="lgs_fec maxima"),
):
    return servicio.listar_logs(db, pagina, tamano, orden, instancia, nivel, desde, hasta)


@router.post("/logs", status_code=201, summary="Registrar logs SQL (collector)")
def registrar_logs(
    filas: dict | list[dict], db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("datos:crear"))]
):
    return servicio.registrar_logs(db, filas)


# =====================================================================
# CARGA AGREGADA
# =====================================================================


@router.get("/cargas", response_model=Pagina[EstadisticaCargaOut], summary="Listar estadisticas de carga")
def listar_cargas(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("-wks_fec"),
    instancia: int | None = Query(None, description="wks_ins"),
    desde: datetime | None = Query(None, description="wks_fec minima"),
    hasta: datetime | None = Query(None, description="wks_fec maxima"),
):
    return servicio.listar_cargas(db, pagina, tamano, orden, instancia, desde, hasta)


@router.post("/cargas", status_code=201, summary="Registrar estadisticas de carga (collector)")
def registrar_cargas(
    filas: dict | list[dict], db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("datos:crear"))]
):
    return servicio.registrar_cargas(db, filas)