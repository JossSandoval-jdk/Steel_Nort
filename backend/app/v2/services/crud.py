"""Operaciones de base de datos que comparten todos los servicios.

Ocho funciones cortas y explicitas que reciben el modelo y el nombre de sus
columnas. No hay clases de configuracion ni tablas intermedias: cada servicio
pasa sus propias columnas y estas funciones hacen siempre lo mismo.

    listar   listado paginado con filtro, rango de fechas y orden
    obtener  una fila por clave
    nuevo    inserta una fila y escribe la auditoria
    nuevo_lote  inserta varias filas de una vez (lo usa el collector)
    cambiar  actualizacion parcial
    borrar   baja logica si la tabla tiene fec_eli, borrado fisico si no
    guardar  commit con el error de integridad traducido a 409
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy import asc, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.utils import utc_now

log = logging.getLogger("steelnort.v2.crud")

# Columnas que escribe el backend. El cliente nunca las manda.
AUDITORIA = ("reg_usu", "fec_reg", "eli_usu", "fec_eli")


# =====================================================================
# LISTAR
# =====================================================================


def listar(
    db: Session,
    modelo,
    orden: str,
    filtros: dict | None = None,
    pagina: int = 1,
    tamano: int = 50,
    con_bajas: bool = False,
    columna_fecha: str | None = None,
    desde=None,
    hasta=None,
) -> dict:
    """Listado paginado.

    ``filtros``    igualdades exactas: ``{"alt_est": "A"}``.
    ``orden``      columnas separadas por coma, ``-`` delante = descendente.
    ``columna_fecha`` con ``desde``/``hasta`` arma el rango de fechas; uno de
    los dos extremos puede quedar en ``None`` para dejarlo abierto.

    Devuelve ``{"total", "pagina", "tamano", "items"}``. El ``total`` cuenta
    las filas que cumplen el filtro, sin paginar.
    """
    consulta = select(modelo)

    # Las tablas con fec_eli (baja logica) ocultan las filas dadas de baja.
    if hasattr(modelo, "fec_eli") and not con_bajas:
        consulta = consulta.where(modelo.fec_eli.is_(None))

    for columna, valor in (filtros or {}).items():
        consulta = consulta.where(getattr(modelo, columna) == valor)

    if columna_fecha is not None:
        if desde is not None:
            consulta = consulta.where(getattr(modelo, columna_fecha) >= desde)
        if hasta is not None:
            consulta = consulta.where(getattr(modelo, columna_fecha) <= hasta)

    total = int(db.scalar(select(func.count()).select_from(consulta.subquery())) or 0)

    for parte in [p.strip() for p in orden.split(",") if p.strip()]:
        columna = getattr(modelo, parte.lstrip("-"))
        consulta = consulta.order_by(desc(columna) if parte.startswith("-") else asc(columna))

    if pagina > 1:
        consulta = consulta.offset((pagina - 1) * tamano)

    return {
        "total": total,
        "pagina": pagina,
        "tamano": tamano,
        "items": list(db.scalars(consulta.limit(tamano)).all()),
    }


# =====================================================================
# OBTENER
# =====================================================================


def obtener(db: Session, modelo, columna: str, valor):
    """Una fila por clave, o ``None``. ``columna`` es el nombre de la clave."""
    return db.scalars(select(modelo).where(getattr(modelo, columna) == valor)).first()


def obtener_o_404(db: Session, modelo, columna: str, valor):
    """Igual que ``obtener``, pero responde 404 si no esta."""
    fila = obtener(db, modelo, columna, valor)
    if fila is None or (hasattr(modelo, "fec_eli") and fila.fec_eli is not None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{modelo.__tablename__} {valor} no encontrado",
        )
    return fila


# =====================================================================
# ESCRIBIR
# =====================================================================


def nuevo(db: Session, modelo, datos: dict, actor: int | None = None):
    """Inserta una fila. Ignora la auditoria y las columnas autogeneradas."""
    campos = _campos_validos(modelo, datos)
    campos["fec_reg"] = utc_now()
    if hasattr(modelo, "reg_usu"):
        campos["reg_usu"] = actor

    fila = modelo(**campos)
    db.add(fila)
    guardar(db, modelo)
    db.refresh(fila)
    return fila


def nuevo_lote(db: Session, modelo, filas: list[dict], actor: int | None = None) -> list:
    """Inserta varias filas con una sola transaccion (collector)."""
    ahora = utc_now()
    entidades = []
    for datos in filas:
        campos = _campos_validos(modelo, datos)
        campos["fec_reg"] = ahora
        if hasattr(modelo, "reg_usu"):
            campos["reg_usu"] = actor
        entidades.append(modelo(**campos))

    db.add_all(entidades)
    guardar(db, modelo)
    return entidades


def cambiar(db: Session, modelo, columna: str, valor, datos: dict):
    """Actualizacion parcial: solo toca los campos que vienen en ``datos``."""
    fila = obtener_o_404(db, modelo, columna, valor)
    for nombre, nuevo in _campos_validos(modelo, datos).items():
        setattr(fila, nombre, nuevo)
    guardar(db, modelo)
    db.refresh(fila)
    return fila


def borrar(db: Session, modelo, columna: str, valor, columna_estado: str | None = None, actor: int | None = None):
    """Da de baja la fila.

    Si la tabla tiene ``fec_eli`` la baja es logica: se marca ``fec_eli``,
    ``eli_usu`` y, si se indica, ``columna_estado`` pasa a ``'I'``. Si no la
    tiene, se borra fisicamente.
    """
    fila = obtener_o_404(db, modelo, columna, valor)

    if not hasattr(modelo, "fec_eli"):
        db.delete(fila)
        db.commit()
        return fila

    if columna_estado:
        setattr(fila, columna_estado, "I")
    fila.eli_usu = actor
    fila.fec_eli = utc_now()
    db.commit()
    return fila


def guardar(db: Session, modelo) -> None:
    """Guarda los cambios. Si la base rechaza la fila se responde 409."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        args = getattr(getattr(exc, "orig", None), "args", None) or []
        motivo = str(args[1] if len(args) > 1 else exc.orig)[:300]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La base rechazo la fila en {modelo.__tablename__}: {motivo}",
        ) from exc


def _campos_validos(modelo, datos: dict) -> dict:
    """Deja solo las columnas reales del modelo y quita la auditoria."""
    existentes = {c.name for c in modelo.__table__.columns}
    return {nombre: valor for nombre, valor in datos.items() if nombre in existentes and nombre not in AUDITORIA}