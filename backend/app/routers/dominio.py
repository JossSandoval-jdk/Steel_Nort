"""Rutas basicas de consulta para las tablas de negocio."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.model_alerta import Alertas, CausasRaiz, HeatmapAnomalias
from app.models.model_configuracion import ConfiguracionSistema
from app.models.model_ml import ModelosML, PrediccionesML
from app.models.model_reporte import Reportes
from app.models.model_scada import NodosSCADA, Servicios
from app.models.model_usuario import EventosSesion, Sesiones, Usuarios
from app.routers.auth import get_current_user, require_csrf
from app.schemas.dominio import (
    AlertaCreate, AlertaOut, CausaRaizOut, ConfiguracionCreate, ConfiguracionOut,
    EventoSesionOut, HeatmapOut, ModeloMLOut, NodoCreate, NodoOut, PrediccionMLOut,
    ReporteOut, ServicioCreate, ServicioOut, SesionDetalleOut,
)
from app.services.dominio import crear, listar, obtener

router = APIRouter(tags=["dominio"])
Db = Annotated[Session, Depends(get_db)]
Auth = Annotated[Usuarios, Depends(get_current_user)]


@router.get("/sesiones", response_model=list[SesionDetalleOut])
def sesiones(db: Db, _current: Auth) -> list[Sesiones]:
    return listar(db, Sesiones)


@router.get("/sesiones/{sesion_id}/eventos", response_model=list[EventoSesionOut])
def eventos(sesion_id: int, db: Db, _current: Auth) -> list[EventosSesion]:
    return list(db.query(EventosSesion).filter(EventosSesion.evt_ses == sesion_id).all())


@router.get("/scada/nodos", response_model=list[NodoOut])
def nodos(db: Db, _current: Auth) -> list[NodosSCADA]:
    return listar(db, NodosSCADA)


@router.post("/scada/nodos", response_model=NodoOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def crear_nodo(payload: NodoCreate, db: Db, current: Auth) -> NodosSCADA:
    return crear(db, NodosSCADA, payload.model_dump(), current.usu_cod)


@router.get("/scada/servicios", response_model=list[ServicioOut])
def servicios(db: Db, _current: Auth) -> list[Servicios]:
    return listar(db, Servicios)


@router.post("/scada/servicios", response_model=ServicioOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def crear_servicio(payload: ServicioCreate, db: Db, current: Auth) -> Servicios:
    return crear(db, Servicios, payload.model_dump(), current.usu_cod)


@router.get("/alertas", response_model=list[AlertaOut])
def alertas(db: Db, _current: Auth) -> list[Alertas]:
    return listar(db, Alertas)


@router.post("/alertas", response_model=AlertaOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def crear_alerta(payload: AlertaCreate, db: Db, current: Auth) -> Alertas:
    datos = payload.model_dump() | {"alt_usu": current.usu_cod}
    return crear(db, Alertas, datos, current.usu_cod)


@router.get("/alertas/{alerta_id}/causas", response_model=list[CausaRaizOut])
def causas(alerta_id: int, db: Db, _current: Auth) -> list[CausasRaiz]:
    consulta = select(CausasRaiz).where(CausasRaiz.cra_alt == alerta_id)
    return list(db.scalars(consulta))


@router.get("/heatmap", response_model=list[HeatmapOut])
def heatmap(db: Db, _current: Auth) -> list[HeatmapAnomalias]:
    return listar(db, HeatmapAnomalias)


@router.get("/configuracion", response_model=list[ConfiguracionOut])
def configuracion(db: Db, _current: Auth) -> list[ConfiguracionSistema]:
    return listar(db, ConfiguracionSistema)


@router.post("/configuracion", response_model=ConfiguracionOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def crear_configuracion(payload: ConfiguracionCreate, db: Db, current: Auth) -> ConfiguracionSistema:
    return crear(db, ConfiguracionSistema, payload.model_dump(), current.usu_cod)


@router.get("/ml/modelos", response_model=list[ModeloMLOut])
def modelos_ml(db: Db, _current: Auth) -> list[ModelosML]:
    return listar(db, ModelosML)


@router.get("/ml/predicciones", response_model=list[PrediccionMLOut])
def predicciones_ml(db: Db, _current: Auth) -> list[PrediccionesML]:
    return listar(db, PrediccionesML)


@router.get("/reportes", response_model=list[ReporteOut])
def reportes(db: Db, _current: Auth) -> list[Reportes]:
    return listar(db, Reportes)