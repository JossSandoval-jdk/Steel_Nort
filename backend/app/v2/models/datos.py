"""Modelos de DATOS CRUDOS: metricas, eventos, logs SQL y carga agregada.

Las cuatro tablas del bloque 6 del esquema. Comparten la misma forma: un
codigo autogenerado, la fecha como parte de la clave, la instancia que produjo
la fila, la prediccion a la que se atribuye y el dato util.

En el esquema estan particionadas por mes, y por eso NO declaran FK hacia
``predicciones_ml`` (SQL Server no lo permite desde una tabla particionada).
Aqui tampoco: la integridad la garantiza el trigger, no la FK.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, NVARCHAR, DateTime, ForeignKey, Identity, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.utils import utc_now
from app.v2.database import Base


class Metrica(Base):
    """Muestra de metricas del motor por ventana (JSON de variables)."""

    __tablename__ = "metricas"
    __table_args__ = {"schema": "dbo"}

    met_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    met_ins: Mapped[int] = mapped_column(Integer, nullable=False)
    met_prd: Mapped[int | None] = mapped_column(Integer)
    met_fec: Mapped[datetime] = mapped_column(DateTime, nullable=False, primary_key=True)
    met_json: Mapped[str] = mapped_column(NVARCHAR, nullable=False)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class Evento(Base):
    """Evento de SQL Server que explica una anomalia.

    No se guarda uno por lote (``sql_batch_completed``): solo los que duran
    sobre el umbral, leen sobre el percentil o fallaron.
    """

    __tablename__ = "eventos"
    __table_args__ = {"schema": "dbo"}

    eve_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    eve_ins: Mapped[int] = mapped_column(Integer, nullable=False)
    eve_prd: Mapped[int | None] = mapped_column(Integer)
    eve_sid: Mapped[int | None] = mapped_column(Integer)
    eve_fec: Mapped[datetime] = mapped_column(DateTime, nullable=False, primary_key=True)
    eve_dur: Mapped[int | None] = mapped_column(Integer)
    eve_cpu: Mapped[int | None] = mapped_column(Integer)
    eve_lreads: Mapped[int | None] = mapped_column(Integer)
    eve_wait: Mapped[str | None] = mapped_column(String(60))
    eve_sql: Mapped[str | None] = mapped_column(String(500))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class LogSQL(Base):
    """Linea del log de errores de SQL que captura el collector."""

    __tablename__ = "logs_sql"
    __table_args__ = {"schema": "dbo"}

    lgs_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    lgs_ins: Mapped[int] = mapped_column(ForeignKey("dbo.instancias.ins_cod"), nullable=False)
    lgs_prd: Mapped[int | None] = mapped_column(Integer)
    lgs_fec: Mapped[datetime] = mapped_column(DateTime, nullable=False, primary_key=True)
    lgs_niv: Mapped[str | None] = mapped_column(CHAR(1))
    lgs_msg: Mapped[str | None] = mapped_column(NVARCHAR)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class EstadisticaCarga(Base):
    """Foto agregada de la carga por intervalo (JSON).

    Es un agregado por intervalo, no una ventana evaluada, asi que no lleva
    columna de prediccion.
    """

    __tablename__ = "estadisticas_carga"
    __table_args__ = {"schema": "dbo"}

    wks_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    wks_ins: Mapped[int] = mapped_column(ForeignKey("dbo.instancias.ins_cod"), nullable=False)
    wks_fec: Mapped[datetime] = mapped_column(DateTime, nullable=False, primary_key=True)
    wks_json: Mapped[str] = mapped_column(NVARCHAR, nullable=False)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)