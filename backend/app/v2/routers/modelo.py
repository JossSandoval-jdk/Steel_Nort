"""Rutas de MODELO: despliegue, predicciones, deriva y reentrenamientos.

Las tablas de historico (predicciones y deriva) solo admiten lectura y alta por
lote: las escribe el detector y no se editan a mano.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.v2.models.acceso import Usuario
from app.v2.schemas.comun import Mensaje, Pagina
from app.v2.schemas.modelo import (
    DerivaMonitorOut,
    ModeloMLCreate,
    ModeloMLOut,
    ModeloMLUpdate,
    PrediccionMLOut,
    ReentrenamientoOut,
    ReentrenamientoPasoOut,
)
from app.v2.seguridad import Sesion, requiere_permiso
from app.v2.services import modelo as servicio

router = APIRouter(prefix="/modelo", tags=["modelo"])


# =====================================================================
# MODELOS
# =====================================================================


@router.get("/modelos", response_model=Pagina[ModeloMLOut], summary="Listar modelos")
def listar_modelos(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("modelo:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("mdl_cod"),
    con_bajas: bool = Query(False),
    estado: str | None = Query(None, pattern="^[ACI]$", description="A activo, C candidato, I inactivo"),
):
    return servicio.listar_modelos(db, pagina, tamano, orden, con_bajas, estado)


@router.get("/modelos/{cod}", response_model=ModeloMLOut, summary="Ver un modelo")
def obtener_modelo(cod: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("modelo:leer"))]):
    return servicio.obtener_modelo(db, cod)


@router.post("/modelos", response_model=ModeloMLOut, status_code=201, summary="Crear modelo")
def crear_modelo(
    datos: ModeloMLCreate, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("modelo:crear"))]
):
    return servicio.crear_modelo(db, datos, actor.usu_cod)


@router.patch("/modelos/{cod}", response_model=ModeloMLOut, summary="Editar modelo")
def actualizar_modelo(
    cod: int, datos: ModeloMLUpdate, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("modelo:editar"))]
):
    return servicio.actualizar_modelo(db, cod, datos, actor.usu_cod)


@router.post("/modelos/{cod}/activar", response_model=ModeloMLOut, summary="Activar modelo en produccion")
def activar_modelo(cod: int, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("modelo:editar"))]):
    return servicio.activar_modelo(db, cod, actor.usu_cod)


@router.delete("/modelos/{cod}", response_model=Mensaje, summary="Dar de baja un modelo")
def eliminar_modelo(cod: int, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("modelo:eliminar"))]):
    servicio.eliminar_modelo(db, cod, actor.usu_cod)
    return {"detalle": f"Modelo {cod} dado de baja"}


# =====================================================================
# PREDICCIONES
# =====================================================================


@router.get("/predicciones", response_model=Pagina[PrediccionMLOut], summary="Listar predicciones")
def listar_predicciones(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("modelo:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("-prd_ini"),
    instancia: int | None = Query(None, description="prd_ins"),
    modelo: int | None = Query(None, description="prd_mdl"),
    solo_anomalias: bool = Query(False, description="Solo las marcadas como anomalia"),
    desde: datetime | None = Query(None, description="prd_ini minima"),
    hasta: datetime | None = Query(None, description="prd_ini maxima"),
):
    return servicio.listar_predicciones(db, pagina, tamano, orden, instancia, modelo, solo_anomalias, desde, hasta)


@router.get("/predicciones/{cod}", response_model=PrediccionMLOut, summary="Ver una prediccion")
def obtener_prediccion(cod: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("modelo:leer"))]):
    return servicio.obtener_prediccion(db, cod)


@router.post(
    "/predicciones",
    status_code=201,
    summary="Registrar predicciones (una o varias)",
    description="Cuerpo: una fila o una lista de filas con las columnas de predicciones_ml.",
)
def registrar_predicciones(
    filas: dict | list[dict], db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("modelo:crear"))]
):
    return servicio.registrar_predicciones(db, filas)


# =====================================================================
# DERIVA
# =====================================================================


@router.get("/deriva", response_model=Pagina[DerivaMonitorOut], summary="Listar medidas de deriva")
def listar_deriva(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("modelo:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("-drv_fec"),
    modelo: int | None = Query(None, description="drv_mdl"),
    variable: str | None = Query(None, description="drv_var"),
    estado: str | None = Query(None, pattern="^[EAN]$"),
):
    return servicio.listar_deriva(db, pagina, tamano, orden, modelo, variable, estado)


@router.post("/deriva", status_code=201, summary="Registrar medidas de deriva")
def registrar_deriva(
    filas: dict | list[dict], db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("modelo:crear"))]
):
    return servicio.registrar_deriva(db, filas)


# =====================================================================
# REENTRENAMIENTO
# =====================================================================


@router.get("/reentrenamientos", response_model=Pagina[ReentrenamientoOut], summary="Listar reentrenamientos")
def listar_reentrenamientos(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("modelo:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(50, ge=1, le=500),
    orden: str = Query("-ren_fec_sol"),
    estado: str | None = Query(
        None, pattern="^[PEACR]$", description="P pendiente, E en curso, A aprobado, C cancelado, R rechazado"
    ),
    modelo: int | None = Query(None, description="ren_mdl_origen"),
):
    return servicio.listar_reentrenamientos(db, pagina, tamano, orden, estado, modelo)


@router.get("/reentrenamientos/{cod}", response_model=ReentrenamientoOut, summary="Ver un reentrenamiento")
def obtener_reentrenamiento(cod: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("modelo:leer"))]):
    return servicio.obtener_reentrenamiento(db, cod)


@router.post(
    "/reentrenamientos",
    response_model=ReentrenamientoOut,
    status_code=201,
    summary="Pedir un reentrenamiento",
)
def registrar_reentrenamiento(
    datos: dict, db: Sesion, actor: Annotated[Usuario, Depends(requiere_permiso("modelo:crear"))]
):
    return servicio.registrar_reentrenamiento(db, datos, actor.usu_cod)


@router.patch("/reentrenamientos/{cod}", response_model=ReentrenamientoOut, summary="Actualizar un reentrenamiento")
def actualizar_reentrenamiento(
    cod: int, datos: dict, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("modelo:editar"))]
):
    return servicio.actualizar_reentrenamiento(db, cod, datos)


@router.get(
    "/reentrenamientos/{cod}/completo",
    summary="Reentrenamiento con su bitacora de pasos",
)
def obtener_reentrenamiento_completo(
    cod: int, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("modelo:leer"))]
):
    return servicio.obtener_reentrenamiento_completo(db, cod)


# =====================================================================
# BITACORA DE PASOS
# =====================================================================


@router.get("/pasos", response_model=Pagina[ReentrenamientoPasoOut], summary="Listar pasos")
def listar_pasos(
    db: Sesion,
    _: Annotated[Usuario, Depends(requiere_permiso("modelo:leer"))],
    pagina: int = Query(1, ge=1),
    tamano: int = Query(100, ge=1, le=500),
    orden: str = Query("rep_ren,rep_orden"),
    reentrenamiento: int | None = Query(None, description="rep_ren"),
):
    return servicio.listar_pasos(db, pagina, tamano, orden, reentrenamiento)


@router.post("/pasos", response_model=ReentrenamientoPasoOut, summary="Registrar un paso")
def registrar_paso(datos: dict, db: Sesion, _: Annotated[Usuario, Depends(requiere_permiso("modelo:crear"))]):
    return servicio.registrar_paso(db, datos)