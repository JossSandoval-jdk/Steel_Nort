"""Servicio de NODOS: instancias vigiladas y conexiones observadas."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.v2.models.nodos import Instancia, SesionSQL
from app.v2.schemas.nodos import InstanciaCreate, InstanciaUpdate
from app.v2.services import crud


def listar_instancias(db: Session, pagina: int, tamano: int, orden: str, con_bajas: bool, estado: str | None):
    return crud.listar(
        db,
        Instancia,
        orden or "ins_nom",
        filtros={"ins_est": estado} if estado else None,
        pagina=pagina,
        tamano=tamano,
        con_bajas=con_bajas,
    )


def obtener_instancia(db: Session, cod: int) -> Instancia:
    return crud.obtener_o_404(db, Instancia, "ins_cod", cod)


def crear_instancia(db: Session, datos: InstanciaCreate, actor: int | None) -> Instancia:
    return crud.nuevo(db, Instancia, datos.model_dump(), actor)


def actualizar_instancia(db: Session, cod: int, datos: InstanciaUpdate, actor: int | None) -> Instancia:
    """Solo se cambian nombre, fecha de alta y estado.

    Host y puerto no se tocan: son la clave natural del nodo y cambiarlos
    haria que las filas historicas apuntaran a otra maquina.
    """
    return crud.cambiar(db, Instancia, "ins_cod", cod, datos.model_dump(exclude_unset=True))


def eliminar_instancia(db: Session, cod: int, actor: int | None) -> Instancia:
    return crud.borrar(db, Instancia, "ins_cod", cod, columna_estado="ins_est", actor=actor)


def listar_sesiones_sql(
    db: Session,
    pagina: int,
    tamano: int,
    orden: str,
    instancia: int | None,
    estado: str | None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
):
    filtros = {}
    if instancia:
        filtros["ssq_ins"] = instancia
    if estado:
        filtros["ssq_est"] = estado
    return crud.listar(
        db,
        SesionSQL,
        orden or "-ssq_fec_ini",
        filtros or None,
        pagina=pagina,
        tamano=tamano,
        columna_fecha="ssq_fec_ini",
        desde=desde,
        hasta=hasta,
    )