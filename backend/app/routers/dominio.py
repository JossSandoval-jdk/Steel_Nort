"""Rutas basicas de consulta para las tablas de negocio."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.model_alerta import Alertas, CausasRaiz, HeatmapAnomalias
from app.models.model_configuracion import ConfiguracionSistema
from app.models.model_ml import ModelosML, PrediccionesML
from app.models.model_muestra_normal import MuestrasNormales
from app.models.model_reporte import Reportes
from app.models.model_scada import NodosSCADA, Servicios
from app.models.model_usuario import EventosSesion, Sesiones, Usuarios
from app.routers.auth import get_current_user, require_csrf
from app.schemas.dominio import (
    AlertaCreate, AlertaOut, AlertaResolverPayload, CausaRaizOut,
    ConfiguracionCreate, ConfiguracionOut, EventoSesionOut, HeatmapOut,
    ModeloMLOut, NodoCreate, NodoOut, PrediccionMLOut, ReporteOut,
    ServicioCreate, ServicioOut, SesionDetalleOut,
)
from app.services.dominio import crear, listar, obtener
from app.utils import utc_now

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


@router.patch("/alertas/{alerta_id}/resolver", response_model=AlertaOut,
              dependencies=[Depends(require_csrf)])
def resolver_alerta(alerta_id: int, payload: AlertaResolverPayload,
                    db: Db, current: Auth) -> Alertas:
    """Cierra una alerta y la clasifica (falsa_alarma/incidente_real/esperado).

    Esa clasificacion es la verdad de campo que alimenta el FPR/TPR de la
    vigilancia en vivo.
    """
    alerta = db.get(Alertas, alerta_id)
    if alerta is None or alerta.fec_eli is not None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    if alerta.alt_resu:
        return alerta

    nota = f" - {payload.nota}" if payload.nota else ""
    alerta.alt_resu = True
    alerta.alt_fec_resu = utc_now()
    alerta.alt_usu = current.usu_cod
    prev = alerta.alt_diag or ""
    alerta.alt_diag = (
        f"{prev} | resuelta por {current.usu_cod} "
        f"etiqueta={payload.etiqueta}{nota}"
    )[:500]
    db.commit()
    db.refresh(alerta)
    return alerta


@router.get("/alertas/vigilancia")
def vigilancia(db: Db, _current: Auth) -> dict:
    """FPR/TPR observado en vivo por nodo.

    - ``ratio_alarma``: ventanas anomalas / total evaluadas (proxy del FPR
      mientras el entorno este sano).
    - ``alertas.por_etiqueta``: resueltas manualmente como falsa_alarma /
      incidente_real / esperado (verdad de campo).
    """
    nodos = {n[0]: n[1] for n in
             db.execute(select(NodosSCADA.ndo_cod, NodosSCADA.ndo_nom))}
    normales = db.execute(
        select(MuestrasNormales.mno_ndo, func.count())
        .group_by(MuestrasNormales.mno_ndo)
    ).all()
    anomalias = db.execute(
        select(PrediccionesML.prd_ndo, func.count())
        .group_by(PrediccionesML.prd_ndo)
    ).all()
    desde_24h = utc_now() - timedelta(hours=24)
    norm_24h = db.execute(
        select(func.count()).select_from(MuestrasNormales)
        .where(MuestrasNormales.mno_fec >= desde_24h)).scalar() or 0
    anom_24h = db.execute(
        select(func.count()).select_from(PrediccionesML)
        .where(PrediccionesML.prd_fec >= desde_24h)).scalar() or 0

    def ratio(a: int, n: int) -> float:
        tot = a + n
        return round(a / tot, 4) if tot else 0.0

    por_nodo = []
    g_anom = g_norm = 0
    for ndo_cod, nombre in sorted(nodos.items(), key=lambda kv: kv[1]):
        a = dict(anomalias).get(ndo_cod, 0)
        n = dict(normales).get(ndo_cod, 0)
        g_anom += a
        g_norm += n
        por_nodo.append({
            "nodo": nombre, "ndo_cod": ndo_cod,
            "anomalias": a, "normales": n, "ventanas": a + n,
            "ratio_alarma": ratio(a, n),
        })

    alertas = db.execute(
        select(Alertas.alt_diag, Alertas.alt_resu)
        .where(Alertas.alt_tipo == "anomalia_ml")
    ).all()
    abiertas = sum(1 for _, r in alertas if not r)
    etiquetas = {"falsa_alarma": 0, "incidente_real": 0, "esperado": 0}
    for diag, resu in alertas:
        m = re.search(r"etiqueta=(\w+)", diag or "")
        if resu and m and m.group(1) in etiquetas:
            etiquetas[m.group(1)] += 1

    return {
        "generado": utc_now().isoformat(),
        "por_nodo": por_nodo,
        "global": {
            "anomalias": g_anom, "normales": g_norm,
            "ventanas": g_anom + g_norm, "ratio_alarma": ratio(g_anom, g_norm),
        },
        "ultimas_24h": {
            "anomalias": anom_24h, "normales": norm_24h,
            "ratio_alarma": ratio(anom_24h, norm_24h),
        },
        "alertas": {"abiertas": abiertas, "por_etiqueta": etiquetas},
    }


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