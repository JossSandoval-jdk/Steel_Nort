"""Rutas de SISTEMA: parametros de configuracion y cifras del tablero."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query

from app.v2.models.acceso import Usuario
from app.v2.schemas.comun import Mensaje, Pagina
from app.v2.schemas.sistema import ConfiguracionOut
from app.v2.seguridad import Sesion, requiere_permiso
from app.v2.services import sistema as servicio

router = APIRouter(prefix="/sistema", tags=["sistema"])


# =====================================================================
# PARAMETROS
# =====================================================================


@router.get("/configuracion", response_model=Pagina[ConfiguracionOut], summary="Listar parametros")
def listar_configuracion(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("sistema:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(100, ge=1, le=500),
    orden: str = Query("cfg_clave"),
):
    return servicio.listar_configuracion(db, pagina, tamano, orden)


@router.get("/configuracion/{clave}", response_model=ConfiguracionOut, summary="Ver un parametro")
def obtener_configuracion(clave: str, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("sistema:leer"))]):
    return servicio.obtener_configuracion(db, clave)


@router.put("/configuracion/{clave}", response_model=ConfiguracionOut, summary="Crear o actualizar un parametro")
def guardar_configuracion(
    clave: str,
    db: Sesion,
    actor: Annotated[Usuario, Depends(requiere_permiso("sistema:editar"))],
    valor: str = Body(..., embed=True, description="Nuevo valor del parametro"),
):
    return servicio.guardar_configuracion(db, clave, valor, actor.usu_cod)


@router.delete("/configuracion/{clave}", response_model=Mensaje, summary="Dar de baja un parametro")
def eliminar_configuracion(
    clave: str, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("sistema:eliminar"))]
):
    servicio.eliminar_configuracion(db, clave, actor.usu_cod)
    return {"detalle": f"Parametro {clave} dado de baja"}


# =====================================================================
# TABLERO (pantalla de Inicio)
# =====================================================================
# Estas dos rutas piden ``tablero:leer`` y no ``sistema:leer`` a proposito:
# el resumen es la portada y la ven todos los roles, mientras que la
# configuracion de mas arriba es solo de quien la administra.


@router.get("/resumen", summary="Cifras de la pantalla de inicio")
def resumen(db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("tablero:leer"))]):
    return servicio.resumen(db)


@router.get("/resumen/heatmap", summary="Celdas del mapa de calor de un dia")
def resumen_heatmap(dia: date, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("tablero:leer"))]):
    return servicio.resumen_heatmap(db, dia)


@router.get("/resumen/disponibilidad", summary="Disponibilidad de los ultimos dias")
def resumen_disponibilidad(dias: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("tablero:leer"))]):
    return servicio.resumen_disponibilidad(db, dias)


@router.get("/resumen/transacciones", summary="Promedio diario de transacciones")
def resumen_transacciones(dias: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("tablero:leer"))]):
    return servicio.resumen_transacciones(db, dias)


# =====================================================================
# CONEXIONES
# =====================================================================


@router.get("/conexiones", summary="Estado de conexiones")
def estado_conexiones(db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("sistema:leer"))]):
    """Comprueba la base de la v2 y el SQL Server del sistema monitoreado."""
    return servicio.estado_conexiones(db)