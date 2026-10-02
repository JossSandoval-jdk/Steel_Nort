"""Servicio de MODELO: modelos, predicciones, deriva y reentrenamientos.

Reglas propias de esta familia:

  * solo un modelo puede quedar activo (``mdl_est = 'A'``), asi que antes de
    activar uno nuevo se desactiva el que hubiera;
  * ``predicciones_ml.prd_feats`` no se puede modificar despues (lo protege un
    trigger de la base), asi que este servicio nunca lo toca;
  * predicciones y deriva son historico: se registran y se listan, no se
    editan a mano.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.v2.models.modelo import (
    DerivaMonitor,
    ModeloML,
    PrediccionML,
    Reentrenamiento,
    ReentrenamientoPaso,
)
from app.v2.schemas.modelo import ModeloMLCreate, ModeloMLUpdate
from app.v2.services import crud

# =====================================================================
# MODELOS
# =====================================================================


def listar_modelos(db: Session, pagina: int, tamano: int, orden: str, con_bajas: bool, estado: str | None):
    return crud.listar(
        db,
        ModeloML,
        orden or "mdl_cod",
        filtros={"mdl_est": estado} if estado else None,
        pagina=pagina,
        tamano=tamano,
        con_bajas=con_bajas,
    )


def obtener_modelo(db: Session, cod: int) -> ModeloML:
    return crud.obtener_o_404(db, ModeloML, "mdl_cod", cod)


def crear_modelo(db: Session, datos: ModeloMLCreate, actor: int | None) -> ModeloML:
    return crud.nuevo(db, ModeloML, datos.model_dump(), actor)


def actualizar_modelo(db: Session, cod: int, datos: ModeloMLUpdate, actor: int | None) -> ModeloML:
    """Si el PATCH activa el modelo, primero desactiva el que estuviera activo."""
    campos = datos.model_dump(exclude_unset=True)
    if campos.get("mdl_est") == "A":
        _desactivar_activos(db, conservar=cod)
    return crud.cambiar(db, ModeloML, "mdl_cod", cod, campos)


def activar_modelo(db: Session, cod: int, actor: int | None) -> ModeloML:
    """Deja este modelo como el unico en produccion."""
    modelo = obtener_modelo(db, cod)
    _desactivar_activos(db, conservar=cod)
    modelo.mdl_est = "A"
    crud.guardar(db, ModeloML)
    db.refresh(modelo)
    return modelo


def eliminar_modelo(db: Session, cod: int, actor: int | None) -> ModeloML:
    return crud.borrar(db, ModeloML, "mdl_cod", cod, columna_estado="mdl_est", actor=actor)


def _desactivar_activos(db: Session, conservar: int) -> None:
    """Pone en 'C' (candidato) todos los modelos activos salvo el indicado."""
    activos = db.scalars(
        select(ModeloML).where(ModeloML.mdl_est == "A", ModeloML.mdl_cod != conservar)
    ).all()
    for modelo in activos:
        modelo.mdl_est = "C"


# =====================================================================
# PREDICCIONES
# =====================================================================


def listar_predicciones(
    db: Session,
    pagina: int,
    tamano: int,
    orden: str,
    instancia: int | None,
    modelo: int | None,
    solo_anomalias: bool,
    desde: datetime | None = None,
    hasta: datetime | None = None,
):
    filtros = {}
    if instancia:
        filtros["prd_ins"] = instancia
    if modelo:
        filtros["prd_mdl"] = modelo
    if solo_anomalias:
        filtros["prd_es_anom"] = True
    return crud.listar(
        db,
        PrediccionML,
        orden or "-prd_ini",
        filtros or None,
        pagina=pagina,
        tamano=tamano,
        columna_fecha="prd_ini",
        desde=desde,
        hasta=hasta,
    )


def obtener_prediccion(db: Session, cod: int) -> PrediccionML:
    return crud.obtener_o_404(db, PrediccionML, "prd_cod", cod)


def registrar_predicciones(db: Session, filas: list[dict]) -> list[PrediccionML]:
    """El detector inserta por HTTP, normalmente en lote."""
    if not filas:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lista de predicciones vacia")
    return crud.nuevo_lote(db, PrediccionML, filas)


# =====================================================================
# DERIVA
# =====================================================================


def listar_deriva(
    db: Session,
    pagina: int,
    tamano: int,
    orden: str,
    modelo: int | None,
    variable: str | None,
    estado: str | None,
):
    filtros = {}
    if modelo:
        filtros["drv_mdl"] = modelo
    if variable:
        filtros["drv_var"] = variable
    if estado:
        filtros["drv_est"] = estado
    return crud.listar(db, DerivaMonitor, orden or "-drv_fec", filtros or None, pagina=pagina, tamano=tamano)


def registrar_deriva(db: Session, filas: list[dict]) -> list[DerivaMonitor]:
    if not filas:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lista de medidas vacia")
    return crud.nuevo_lote(db, DerivaMonitor, filas)


# =====================================================================
# REENTRENAMIENTO
# =====================================================================


def listar_reentrenamientos(
    db: Session, pagina: int, tamano: int, orden: str, estado: str | None, modelo: int | None
):
    filtros = {}
    if estado:
        filtros["ren_est"] = estado
    if modelo:
        filtros["ren_mdl_origen"] = modelo
    return crud.listar(
        db, Reentrenamiento, orden or "-ren_fec_sol", filtros or None, pagina=pagina, tamano=tamano
    )


def obtener_reentrenamiento(db: Session, cod: int) -> Reentrenamiento:
    return crud.obtener_o_404(db, Reentrenamiento, "ren_cod", cod)


def registrar_reentrenamiento(db: Session, datos: dict, actor: int | None) -> Reentrenamiento:
    """Un reentrenamiento siempre arranca pendiente (``ren_est = 'P'``)."""
    campos = dict(datos)
    campos["ren_est"] = "P"
    return crud.nuevo(db, Reentrenamiento, campos, actor)


def actualizar_reentrenamiento(db: Session, cod: int, datos: dict) -> Reentrenamiento:
    return crud.cambiar(db, Reentrenamiento, "ren_cod", cod, datos)


def obtener_reentrenamiento_completo(db: Session, cod: int) -> dict:
    """El reentrenamiento con su bitacora de pasos (lo que se pinta junto)."""
    reentrenamiento = obtener_reentrenamiento(db, cod)
    pasos = listar_pasos(db, 1, 99, "rep_orden", cod)["items"]
    return {"reentrenamiento": reentrenamiento, "pasos": pasos}


# =====================================================================
# BITACORA DE PASOS
# =====================================================================


def listar_pasos(db: Session, pagina: int, tamano: int, orden: str, reentrenamiento: int | None):
    return crud.listar(
        db,
        ReentrenamientoPaso,
        orden or "rep_ren,rep_orden",
        filtros={"rep_ren": reentrenamiento} if reentrenamiento else None,
        pagina=pagina,
        tamano=tamano,
    )


def registrar_paso(db: Session, datos: dict) -> ReentrenamientoPaso:
    """Guarda un paso. La clave es ``(rep_ren, rep_orden)``.

    Si ese paso ya existe se sobrescribe (el runner va reportando el mismo
    paso mientras avanza); si no, se inserta.
    """
    paso = crud.obtener(db, ReentrenamientoPaso, "rep_ren", datos.get("rep_ren"))
    if paso is not None and paso.rep_orden == datos.get("rep_orden"):
        for campo, valor in datos.items():
            setattr(paso, campo, valor)
        crud.guardar(db, ReentrenamientoPaso)
        return paso
    return crud.nuevo(db, ReentrenamientoPaso, datos)