"""Modelos de infraestructura SCADA."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.model_alerta import Alertas
    from app.models.model_ml import PrediccionesML


class NodosSCADA(Base):
    __tablename__ = "Nodos_SCADA"

    ndo_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ndo_nom: Mapped[str] = mapped_column(String(100), nullable=False)
    ndo_ubic: Mapped[str | None] = mapped_column(String(150))
    ndo_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    ndo_tipo: Mapped[str] = mapped_column(String(50), nullable=False, default="scada")
    ndo_est: Mapped[str] = mapped_column(String(20), nullable=False, default="operativo")
    ndo_uptime: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reg_usu: Mapped[str | None] = mapped_column(String(60))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)

    servicios: Mapped[list["Servicios"]] = relationship(back_populates="nodo")
    alertas: Mapped[list["Alertas"]] = relationship(back_populates="nodo")
    predicciones: Mapped[list["PrediccionesML"]] = relationship(back_populates="nodo")

    __table_args__ = (
        CheckConstraint("ndo_tipo IN ('scada','servidor','edge','plc')", name="CK_ndo_tipo"),
        CheckConstraint("ndo_est IN ('operativo','degradado','offline','mantenimiento')", name="CK_ndo_est"),
    )


class Servicios(Base):
    __tablename__ = "Servicios"

    svc_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    svc_ndo: Mapped[int] = mapped_column(ForeignKey("Nodos_SCADA.ndo_cod"), nullable=False)
    svc_nom: Mapped[str] = mapped_column(String(100), nullable=False)
    svc_desc: Mapped[str | None] = mapped_column(String(200))
    svc_est: Mapped[str] = mapped_column(String(20), nullable=False, default="operativo")
    svc_uptime_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=100.00)
    reg_usu: Mapped[str | None] = mapped_column(String(60))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)

    nodo: Mapped["NodosSCADA"] = relationship(back_populates="servicios")
    alertas: Mapped[list["Alertas"]] = relationship(back_populates="servicio")

    __table_args__ = (
        CheckConstraint("svc_est IN ('operativo','degradado','detenido','programado')", name="CK_svc_est"),
    )