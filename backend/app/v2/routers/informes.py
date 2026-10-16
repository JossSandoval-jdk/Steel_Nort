"""Rutas de INFORMES: resumen del periodo, anomalias, alertas y exportaciones.

Alimentan la pantalla Reportes v2 (que reemplaza a la v1). Todo se lee de las
tablas reales de la v2 y exige ``datos:leer``, que es el permiso de esa pantalla.
Los archivos exportables se escriben en ``logs/informes_exportados``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.v2.models.acceso import Usuario
from app.v2.schemas.comun import Mensaje, Pagina
from app.v2.schemas.informes import (
    AlertaInformeOut,
    AnomaliaOut,
    ArchivoExportado,
    ArchivoGenerado,
    GenerarInforme,
    ResumenInforme,
)
from app.v2.seguridad import Sesion, requiere_permiso
from app.v2.services import informes as servicio

router = APIRouter(prefix="/informes", tags=["informes"])


@router.get("/resumen", response_model=ResumenInforme, summary="Resumen del periodo")
def resumen(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))],
    desde: datetime | None = Query(None, description="Desde (inclusive)"),
    hasta: datetime | None = Query(None, description="Hasta (inclusive)"),
):
    return servicio.resumen(db, desde, hasta)


@router.get("/anomalias", response_model=Pagina[AnomaliaOut], summary="Anomalias detalladas")
def anomalias(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    desde: datetime | None = Query(None),
    hasta: datetime | None = Query(None),
    severidad: str | None = Query(None, pattern="^[CAMB]$"),
    instancia: int | None = Query(None, description="alt_ins"),
):
    return servicio.listar_anomalias(db, pagina, tamano, desde, hasta, severidad, instancia)


@router.get("/alertas", response_model=Pagina[AlertaInformeOut], summary="Historial de alertas")
def alertas(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    desde: datetime | None = Query(None),
    hasta: datetime | None = Query(None),
    severidad: str | None = Query(None, pattern="^[CAMB]$"),
    estado: str | None = Query(None, pattern="^[ARSF]$"),
    instancia: int | None = Query(None, description="alt_ins"),
):
    return servicio.listar_alertas(db, pagina, tamano, desde, hasta, severidad, estado, instancia)


@router.post("/generar", response_model=ArchivoGenerado, status_code=201, summary="Generar informe")
def generar(
    datos: GenerarInforme,
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))],
):
    return servicio.generar(db, datos.tipo, datos.formato, datos.desde, datos.hasta)


@router.get("/exportados", response_model=list[ArchivoExportado], summary="Listar exportaciones")
def exportados(_: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))]):
    return servicio.listar_exportados()


@router.get("/exportados/{nombre}", summary="Descargar una exportacion")
def descargar(
    nombre: str,
    _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))],
):
    ruta = servicio.ruta_exportado(nombre)
    if not ruta.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe {nombre}")
    return FileResponse(ruta, filename=nombre)


@router.delete("/exportados/{nombre}", response_model=Mensaje, summary="Eliminar una exportacion")
def eliminar(
    nombre: str,
    _: Annotated[Usuario, Depends(requiere_permiso("datos:leer"))],
):
    servicio.eliminar_exportado(nombre)
    return {"detalle": f"Archivo {nombre} eliminado"}
