"""Modelos de DETECCION: que se avisa y por que.

Las cuatro tablas del bloque 5 del esquema. ``alertas`` es la cabecera;
``alerta_variable`` y ``causas_raiz`` son sus detalles y
``heatmap_anomalias`` es el agregado por hora y severidad.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CHAR,
    DECIMAL,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.utils import utc_now
from app.v2.database import Base


class Alerta(Base):
    """Aviso emitido por el detector o por el monitor.

    ``alt_est``: ``A`` abierta, ``R`` en revision, ``S`` resuelta, ``F`` falso
    positivo (el trigger ``TR_alertas_hma_rollup`` saca las ``F`` del mapa de
    calor). Resolver exige ``alt_usu`` y ``alt_fec_resu``: lo comprueba un
    CHECK de la base.
    """

    __tablename__ = "alertas"
    # implicit_returning=False porque TR_alt_instancia_coherente y
    # TR_alertas_hma_rollup estan sobre esta tabla, y SQL Server prohibe el
    # "OUTPUT inserted.prd_cod" cuando hay triggers (error 334). Ver la nota
    # larga en PrediccionML.
    __table_args__ = {"schema": "dbo", "implicit_returning": False}

    alt_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    alt_prd: Mapped[int | None] = mapped_column(ForeignKey("dbo.predicciones_ml.prd_cod"))
    alt_ins: Mapped[int | None] = mapped_column(ForeignKey("dbo.instancias.ins_cod"))
    alt_usu: Mapped[int | None] = mapped_column(ForeignKey("dbo.usuario.usu_cod"))
    alt_tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    alt_sev: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    alt_titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    alt_diag: Mapped[str | None] = mapped_column(String(500))
    alt_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="A")
    alt_fec: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    alt_fec_resu: Mapped[datetime | None] = mapped_column(DateTime)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class AlertaVariable(Base):
    """Variables que explican una alerta, ordenadas por ``alv_rank``.

    Solo hay fila si hay alerta, asi que aqui si conviene normalizar en lugar
    de guardar la lista dentro de la alerta.
    """

    __tablename__ = "alerta_variable"
    __table_args__ = {"schema": "dbo"}

    alv_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    alv_alt: Mapped[int] = mapped_column(ForeignKey("dbo.alertas.alt_cod"), nullable=False)
    alv_var: Mapped[str] = mapped_column(String(100), nullable=False)
    alv_valor: Mapped[float | None] = mapped_column(DECIMAL(18, 4))
    alv_z: Mapped[float | None] = mapped_column(DECIMAL(10, 4))
    alv_contrib: Mapped[float | None] = mapped_column(DECIMAL(10, 6))
    alv_rank: Mapped[int | None] = mapped_column(Integer)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class CausaRaiz(Base):
    """Arbol de causa raiz de una alerta. ``cra_nivel``: ``R``, ``W`` o ``L``."""

    __tablename__ = "causas_raiz"
    # implicit_returning=False por TR_cra_sin_ciclo (error 334). Ver PrediccionML.
    __table_args__ = {"schema": "dbo", "implicit_returning": False}

    cra_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    cra_alt: Mapped[int] = mapped_column(ForeignKey("dbo.alertas.alt_cod"), nullable=False)
    cra_padre: Mapped[int | None] = mapped_column(ForeignKey("dbo.causas_raiz.cra_cod"))
    cra_nivel: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    cra_etiq: Mapped[str] = mapped_column(String(200), nullable=False)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class HeatmapAnomalia(Base):
    """Celda del mapa de calor: dia x hora x severidad agregada (3 niveles).

    No se particiona a proposito para poder mantener la clave unica
    ``(hma_fec, hma_hora, hma_sev)``, que es la que usa el MERGE del trigger.
    La mantiene ese trigger, no la API.
    """

    __tablename__ = "heatmap_anomalias"
    __table_args__ = {"schema": "dbo"}

    hma_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    hma_fec: Mapped[date] = mapped_column(Date, nullable=False)
    hma_hora: Mapped[int] = mapped_column(Integer, nullable=False)
    hma_sev: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    hma_cant: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)