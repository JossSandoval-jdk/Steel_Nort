"""Servicio de DATOS CRUDOS: metricas, eventos, logs SQL y carga agregada.

Las cuatro tablas son de solo lectura para el usuario: las escribe el collector
por POST y las borra ``proc_retencion_datos``. Por eso aqui no hay funciones de
editar ni de borrar, solo listado, detalle y registro.

Todas aceptan el cuerpo tal cual (una fila o una lista) porque sus columnas son
exactamente las de la tabla; la base es la que valida los tipos.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.v2.models.datos import EstadisticaCarga, Evento, LogSQL, Metrica
from app.v2.services import crud

MAX_FILAS = 1000


def _registrar(db: Session, modelo, cuerpo) -> list:
    """Normaliza el cuerpo a lista y delega la insercion en bloque."""
    filas = cuerpo if isinstance(cuerpo, list) else [cuerpo]
    if not filas:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lista vacia")
    if len(filas) > MAX_FILAS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Maximo {MAX_FILAS} filas por peticion en {modelo.__tablename__}",
        )
    return crud.nuevo_lote(db, modelo, filas)


# =====================================================================
# METRICAS
# =====================================================================


def listar_metricas(
    db: Session,
    pagina: int,
    tamano: int,
    orden: str,
    instancia: int | None,
    prediccion: int | None,
    desde=None,
    hasta=None,
):
    filtros = {}
    if instancia:
        filtros["met_ins"] = instancia
    if prediccion:
        filtros["met_prd"] = prediccion
    return crud.listar(
        db, Metrica, orden or "-met_fec", filtros or None, pagina=pagina, tamano=tamano,
        columna_fecha="met_fec", desde=desde, hasta=hasta,
    )


def obtener_metrica(db: Session, cod: int) -> Metrica:
    return crud.obtener_o_404(db, Metrica, "met_cod", cod)


def registrar_metricas(db: Session, cuerpo) -> list:
    return _registrar(db, Metrica, cuerpo)


# =====================================================================
# EVENTOS
# =====================================================================


def listar_eventos(
    db: Session,
    pagina: int,
    tamano: int,
    orden: str,
    instancia: int | None,
    prediccion: int | None,
    desde=None,
    hasta=None,
    tipo: str | None = None,
):
    filtros = {}
    if instancia:
        filtros["eve_ins"] = instancia
    if prediccion:
        filtros["eve_prd"] = prediccion
    if tipo:
        filtros["eve_wait"] = tipo
    return crud.listar(
        db, Evento, orden or "-eve_fec", filtros or None, pagina=pagina, tamano=tamano,
        columna_fecha="eve_fec", desde=desde, hasta=hasta,
    )


def obtener_evento(db: Session, cod: int) -> Evento:
    return crud.obtener_o_404(db, Evento, "eve_cod", cod)


def registrar_eventos(db: Session, cuerpo) -> list:
    return _registrar(db, Evento, cuerpo)


# =====================================================================
# LOGS SQL
# =====================================================================


def listar_logs(
    db: Session,
    pagina: int,
    tamano: int,
    orden: str,
    instancia: int | None,
    nivel: str | None,
    desde=None,
    hasta=None,
):
    filtros = {}
    if instancia:
        filtros["lgs_ins"] = instancia
    if nivel:
        filtros["lgs_niv"] = nivel
    return crud.listar(
        db, LogSQL, orden or "-lgs_fec", filtros or None, pagina=pagina, tamano=tamano,
        columna_fecha="lgs_fec", desde=desde, hasta=hasta,
    )


def registrar_logs(db: Session, cuerpo) -> list:
    return _registrar(db, LogSQL, cuerpo)


# =====================================================================
# CARGA AGREGADA
# =====================================================================


def listar_cargas(
    db: Session,
    pagina: int,
    tamano: int,
    orden: str,
    instancia: int | None,
    desde=None,
    hasta=None,
):
    return crud.listar(
        db,
        EstadisticaCarga,
        orden or "-wks_fec",
        filtros={"wks_ins": instancia} if instancia else None,
        pagina=pagina,
        tamano=tamano,
        columna_fecha="wks_fec", desde=desde, hasta=hasta,
    )


def registrar_cargas(db: Session, cuerpo) -> list:
    return _registrar(db, EstadisticaCarga, cuerpo)