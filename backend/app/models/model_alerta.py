"""Modelos de alertas y causas raiz."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.model_ml import PrediccionesML
    from app.models.model_scada import NodosSCADA, Servicios
    from app.models.model_usuario import Usuarios


class Alertas(Base):
    __tablename__ = "Alertas"

    alt_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alt_ndo: Mapped[int | None] = mapped_column(ForeignKey("Nodos_SCADA.ndo_cod"))
    alt_svc: Mapped[int | None] = mapped_column(ForeignKey("Servicios.svc_cod"))
    alt_usu: Mapped[int | None] = mapped_column(ForeignKey("Usuarios.usu_cod"))
    alt_prd: Mapped[int | None] = mapped_column(ForeignKey("Predicciones_ML.prd_cod"))
    alt_tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    alt_sev: Mapped[str] = mapped_column(String(15), nullable=False)
    alt_titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    alt_diag: Mapped[str | None] = mapped_column(String(500))
    alt_fec: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    alt_resu: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alt_fec_resu: Mapped[datetime | None] = mapped_column(DateTime)
    reg_usu: Mapped[str | None] = mapped_column(String(60))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)

    nodo: Mapped["NodosSCADA | None"] = relationship(back_populates="alertas")
    servicio: Mapped["Servicios | None"] = relationship(back_populates="alertas")
    usuario: Mapped["Usuarios | None"] = relationship(back_populates="alertas")
    prediccion: Mapped["PrediccionesML | None"] = relationship(back_populates="alertas")
    causas: Mapped[list["CausasRaiz"]] = relationship(back_populates="alerta", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("alt_sev IN ('critica','alta','media','baja')", name="CK_alt_sev"),
    )


class CausasRaiz(Base):
    __tablename__ = "Causas_Raiz"

    cra_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cra_alt: Mapped[int] = mapped_column(ForeignKey("Alertas.alt_cod"), nullable=False)
    cra_padre: Mapped[int | None] = mapped_column(ForeignKey("Causas_Raiz.cra_cod"))
    cra_nivel: Mapped[str] = mapped_column(String(10), nullable=False)
    cra_etiq: Mapped[str] = mapped_column(String(200), nullable=False)
    cra_tono: Mapped[str] = mapped_column(String(10), nullable=False)
    reg_usu: Mapped[str | None] = mapped_column(String(60))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)

    alerta: Mapped["Alertas"] = relationship(back_populates="causas")
    padre: Mapped["CausasRaiz | None"] = relationship(remote_side=[cra_cod], back_populates="hijos")
    hijos: Mapped[list["CausasRaiz"]] = relationship(back_populates="padre")

    __table_args__ = (
        CheckConstraint("cra_nivel IN ('root','warn','leaf')", name="CK_cra_nivel"),
    )


class HeatmapAnomalias(Base):
    __tablename__ = "Heatmap_Anomalias"

    hma_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hma_fec: Mapped[date] = mapped_column(Date, nullable=False)
    hma_hora: Mapped[int] = mapped_column(Integer, nullable=False)
    hma_sev: Mapped[str] = mapped_column(String(15), nullable=False)
    hma_cant: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reg_usu: Mapped[str | None] = mapped_column(String(60))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint("hma_hora BETWEEN 0 AND 23", name="CK_hma_hora"),
        CheckConstraint("hma_sev IN ('normal','alerta_baja','alerta_alta')", name="CK_hma_sev"),
    )