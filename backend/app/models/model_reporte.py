"""Modelo de reportes generados para el negocio."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.model_usuario import Usuarios


class Reportes(Base):
    __tablename__ = "Reportes"

    rpt_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rpt_usu: Mapped[int] = mapped_column(ForeignKey("Usuarios.usu_cod"), nullable=False)
    rpt_tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    rpt_titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    rpt_params: Mapped[str | None] = mapped_column(Text)
    rpt_ruta_arch: Mapped[str | None] = mapped_column(String(500))
    rpt_est: Mapped[str] = mapped_column(String(20), nullable=False, default="generando")
    rpt_fec_gen: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    reg_usu: Mapped[str | None] = mapped_column(String(60))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)

    usuario: Mapped["Usuarios"] = relationship(back_populates="reportes")

    __table_args__ = (
        CheckConstraint(
            "rpt_tipo IN ('alertas','metricas','disponibilidad','anomalias','sesiones','general')",
            name="CK_rpt_tipo",
        ),
        CheckConstraint("rpt_est IN ('generando','completado','error')", name="CK_rpt_est"),
    )