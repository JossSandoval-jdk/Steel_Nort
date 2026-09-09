"""Servicios de consulta y alta basica para los modelos del dominio."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


def listar(db: Session, modelo: Any) -> list[Any]:
    """Lista registros activos cuando la tabla tiene baja logica."""
    consulta = select(modelo)
    if hasattr(modelo, "fec_eli"):
        consulta = consulta.where(modelo.fec_eli.is_(None))
    primary_key = next(iter(modelo.__table__.primary_key.columns))
    return list(db.scalars(consulta.order_by(primary_key)))


def obtener(db: Session, modelo: Any, registro_id: int) -> Any | None:
    registro = db.get(modelo, registro_id)
    if registro is not None and hasattr(registro, "fec_eli") and registro.fec_eli is not None:
        return None
    return registro


def crear(db: Session, modelo: Any, datos: dict[str, Any], usuario_id: int) -> Any:
    registro = modelo(**datos, reg_usu=str(usuario_id))
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro