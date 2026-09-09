"""Modelos de metadatos y predicciones de machine learning."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.model_alerta import Alertas
    from app.models.model_scada import NodosSCADA


class ModelosML(Base):
    __tablename__ = "Modelos_ML"

    mdl_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mdl_nom: Mapped[str] = mapped_column(String(100), nullable=False)
    mdl_tipo: Mapped[str] = mapped_column(String(50), nullable=False, default="isolation_forest")
    mdl_umbral_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=85.00)
    mdl_vars: Mapped[str | None] = mapped_column(Text)
    mdl_hparms: Mapped[str | None] = mapped_column(Text)
    mdl_ruta_art: Mapped[str | None] = mapped_column(String(500))
    mdl_act: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mdl_fec_entr: Mapped[datetime | None] = mapped_column(DateTime)
    reg_usu: Mapped[str | None] = mapped_column(String(60))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)

    predicciones: Mapped[list["PrediccionesML"]] = relationship(back_populates="modelo")

    __table_args__ = (
        CheckConstraint(
            "mdl_tipo IN ('isolation_forest','autoencoder','lstm','random_forest','xgboost','otro')",
            name="CK_mdl_tipo",
        ),
    )


class PrediccionesML(Base):
    __tablename__ = "Predicciones_ML"

    prd_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prd_mdl: Mapped[int] = mapped_column(ForeignKey("Modelos_ML.mdl_cod"), nullable=False)
    prd_ndo: Mapped[int] = mapped_column(ForeignKey("Nodos_SCADA.ndo_cod"), nullable=False)
    prd_fec: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    prd_es_anom: Mapped[bool] = mapped_column(Boolean, nullable=False)
    prd_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    prd_umbral: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    prd_feats: Mapped[str | None] = mapped_column(Text)
    prd_expl: Mapped[str | None] = mapped_column(Text)
    reg_usu: Mapped[str | None] = mapped_column(String(60))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)

    modelo: Mapped["ModelosML"] = relationship(back_populates="predicciones")
    nodo: Mapped["NodosSCADA"] = relationship(back_populates="predicciones")
    alertas: Mapped[list["Alertas"]] = relationship(back_populates="prediccion")