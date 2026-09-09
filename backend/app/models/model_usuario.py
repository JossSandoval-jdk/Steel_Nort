"""Modelos del dominio de autenticacion y usuarios.

Agrupa las entidades relacionadas con el usuario y su sesion:
  - Usuarios: identidad y credenciales.
  - Sesiones: historial de inicios/cierres de sesion.

Convencion: las columnas llevan el prefijo de 3 letras de su tabla
(usu_*, ses_*) y las 4 ultimas son la auditoria comun
(reg_usu, fec_reg, eli_usu, fec_eli) definida en el diccionario de datos.

Cada dominio futuro agrega su propio archivo en ``app/models`` (p. ej.
``model_alerta.py``) y lo importa en ``app/models/__init__.py`` para que
``init_db`` lo registre en la metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.model_alerta import Alertas
    from app.models.model_reporte import Reportes


class Usuarios(Base):
    """Usuarios del sistema y sus roles."""

    __tablename__ = "Usuarios"

    usu_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usu_nom: Mapped[str] = mapped_column(String(100), nullable=False)
    usu_ema: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    usu_pwd: Mapped[str] = mapped_column(String(256), nullable=False)
    usu_rol: Mapped[str] = mapped_column(String(30), nullable=False)
    usu_ini: Mapped[str] = mapped_column(String(4), nullable=False)
    usu_act: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reg_usu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relacion con las sesiones del usuario.
    sesiones: Mapped[list["Sesiones"]] = relationship(
        back_populates="usuario",
        cascade="all, delete-orphan",
    )
    alertas: Mapped[list["Alertas"]] = relationship(back_populates="usuario")
    reportes: Mapped[list["Reportes"]] = relationship(back_populates="usuario")


class Sesiones(Base):
    """Historial de inicios/cierres de sesion de los usuarios."""

    __tablename__ = "Sesiones"

    ses_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ses_usu: Mapped[int] = mapped_column(ForeignKey("Usuarios.usu_cod"), nullable=False)
    ses_fec_ini: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ses_fec_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ses_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    ses_usr_agt: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ses_est: Mapped[str] = mapped_column(String(15), nullable=False, default="activa")
    reg_usu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relacion inversa con el usuario.
    usuario: Mapped["Usuarios"] = relationship(back_populates="sesiones")
    eventos: Mapped[list["EventosSesion"]] = relationship(
        back_populates="sesion",
        cascade="all, delete-orphan",
    )


class EventosSesion(Base):
    """Eventos relevantes registrados durante una sesion."""

    __tablename__ = "Eventos_Sesion"

    evt_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evt_ses: Mapped[int] = mapped_column(ForeignKey("Sesiones.ses_cod"), nullable=False)
    evt_min: Mapped[int] = mapped_column(Integer, nullable=False)
    evt_tip: Mapped[str] = mapped_column(String(30), nullable=False)
    evt_desc: Mapped[str] = mapped_column(String(200), nullable=False)
    evt_color: Mapped[str] = mapped_column(String(7), nullable=False)
    reg_usu: Mapped[str | None] = mapped_column(String(60))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)

    sesion: Mapped["Sesiones"] = relationship(back_populates="eventos")

    __table_args__ = (
        CheckConstraint(
            "evt_tip IN ('login','lectura','api','advertencia','error','cierre')",
            name="CK_evt_tip",
        ),
    )