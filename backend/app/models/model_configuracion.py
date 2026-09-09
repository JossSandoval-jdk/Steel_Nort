"""Modelo de parametros de configuracion del sistema."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConfiguracionSistema(Base):
    __tablename__ = "Configuracion_Sistema"

    cfg_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cfg_clave: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    cfg_valor: Mapped[str] = mapped_column(String(500), nullable=False)
    cfg_desc: Mapped[str | None] = mapped_column(String(200))
    reg_usu: Mapped[str | None] = mapped_column(String(60))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)