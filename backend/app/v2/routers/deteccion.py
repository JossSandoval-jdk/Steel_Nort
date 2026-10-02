"""Rutas de DETECCION: alertas, variables explicativas, causa raiz y heatmap.

Borrar una alerta no la elimina de la base: la marca como descartada
(``alt_est = 'F'``), asi que el historial se conserva.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.v2.models.acceso import Usuario
from app.v2.schemas.comun import Mensaje, Pagina
from app.v2.schemas.deteccion import (
    AlertaCreate,
    AlertaOut,
    AlertaUpdate,
    AlertaVariableOut,
    CausaRaizCreate,
    CausaRaizOut,
    HeatmapAnomaliaOut,
)
from app.v2.seguridad import Sesion, requiere_permiso
from app.v2.services import anomalia_v2, deteccion as servicio

router = APIRouter(prefix="/deteccion", tags=["deteccion"])


# =====================================================================
# ALERTAS
# =====================================================================


@router.get("/alertas", response_model=Pagina[AlertaOut], summary="Listar alertas")
def listar_alertas(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("deteccion:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("-alt_fec"),
    instancia: int | None = Query(None, description="alt_ins"),
    estado: str | None = Query(
        None, pattern="^[ARSF]$", description="A abierta, R en revision, S resuelta, F descartada"
    ),
    severidad: str | None = Query(None, pattern="^[CAMB]$"),
    desde: datetime | None = Query(None, description="alt_fec minima"),
    hasta: datetime | None = Query(None, description="alt_fec maxima"),
):
    return servicio.listar_alertas(db, pagina, tamano, orden, instancia, estado, severidad, desde, hasta)


@router.get("/alertas/{cod}", response_model=AlertaOut, summary="Ver una alerta")
def obtener_alerta(cod: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("deteccion:leer"))]):
    return servicio.obtener_alerta(db, cod)


@router.get("/alertas/{cod}/informe", summary="Ver informe completo de una anomalia")
def obtener_informe_alerta(
    cod: int,
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("deteccion:leer"))],
):
    return anomalia_v2.obtener_informe(db, cod)


@router.post("/alertas", response_model=AlertaOut, status_code=201, summary="Abrir alerta")
def crear_alerta(
    datos: AlertaCreate,
    db: Sesion,
    actor: Annotated[Usuario, Depends(requiere_permiso("deteccion:crear"))],
):
    return servicio.crear_alerta(db, datos, actor.usu_cod)


@router.patch("/alertas/{cod}", response_model=AlertaOut, summary="Editar o resolver alerta")
def actualizar_alerta(
    cod: int, datos: AlertaUpdate, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("deteccion:editar"))]
):
    return servicio.actualizar_alerta(db, cod, datos, actor.usu_cod)


@router.delete("/alertas/{cod}", response_model=Mensaje, summary="Descartar una alerta")
def eliminar_alerta(
    cod: int, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("deteccion:eliminar"))]
):
    servicio.eliminar_alerta(db, cod, actor.usu_cod)
    return {"detalle": f"Alerta {cod} descartada"}


# =====================================================================
# VARIABLES EXPLICATIVAS
# =====================================================================


@router.get("/alertas-variables", response_model=Pagina[AlertaVariableOut], summary="Listar variables por alerta")
def listar_variables(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("deteccion:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(100, ge=1, le=500),
    orden: str = Query("alv_alt,alv_rank"),
    alerta: int | None = Query(None, description="alv_alt"),
):
    return servicio.listar_alerta_variables(db, pagina, tamano, orden, alerta)


@router.post("/alertas-variables", status_code=201, summary="Registrar variables de una o varias alertas")
def registrar_variables(
    filas: dict | list[dict], db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("deteccion:crear"))]
):
    return servicio.registrar_variables(db, filas)


# =====================================================================
# CAUSA RAIZ
# =====================================================================


@router.get("/causas", response_model=Pagina[CausaRaizOut], summary="Listar causa raiz")
def listar_causas(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("deteccion:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(100, ge=1, le=500),
    orden: str = Query("cra_alt,cra_cod"),
    alerta: int | None = Query(None, description="cra_alt"),
    nivel: str | None = Query(None, pattern="^[RWL]$", description="R raiz, WWarning, Lleaf"),
):
    return servicio.listar_causas(db, pagina, tamano, orden, alerta, nivel)


@router.post("/causas", response_model=CausaRaizOut, status_code=201, summary="Registrar causa raiz")
def crear_causa(
    datos: CausaRaizCreate, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("deteccion:crear"))]
):
    return servicio.crear_causa(db, datos)


@router.delete("/causas/{cod}", response_model=Mensaje, summary="Eliminar causa raiz")
def eliminar_causa(cod: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("deteccion:eliminar"))]):
    servicio.eliminar_causa(db, cod)
    return {"detalle": f"Causa {cod} eliminada"}


# =====================================================================
# MAPA DE CALOR
# =====================================================================


@router.get("/heatmap", response_model=Pagina[HeatmapAnomaliaOut], summary="Mapa de calor de anomalias")
def listar_heatmap(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("deteccion:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(200, ge=1, le=1000),
    orden: str = Query("-hma_fec,hma_hora"),
    dia: date | None = Query(None, description="Dia exacto (hma_fec)"),
    severidad: str | None = Query(None, pattern="^[CAMB]$"),
):
    return servicio.listar_heatmap(db, pagina, tamano, orden, dia, severidad)