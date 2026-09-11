"""Modelos ORM para el sistema de roles y permisos.

Define las tablas:
  - Roles: catálogo de roles del sistema.
  - Permisos: catálogo de permisos disponibles.
  - RolPermiso: relación N:N entre Roles y Permisos.

Cada usuario ( Usuarios ) tiene un `usu_rol` que referencia a Roles.rol_cod.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.model_usuario import Usuarios


class Roles(Base):
    """Catálogo de roles del sistema (Administrador, Supervisor, Operador, etc.)."""

    __tablename__ = "Roles"

    rol_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rol_nom: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    rol_desc: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rol_act: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reg_usu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relación N:N con Permisos.
    permisos: Mapped[list["Permisos"]] = relationship(
        secondary="Rol_Permiso",
        back_populates="roles",
    )
    # Relación inversa con Usuarios (usando join por nombre).
    usuarios: Mapped[list["Usuarios"]] = relationship(
        "Usuarios",
        primaryjoin="Roles.rol_nom == Usuarios.usu_rol",
        foreign_keys="Usuarios.usu_rol",
        viewonly=True,
    )


class Permisos(Base):
    """Catálogo de permisos disponibles (ej: usuarios:leer, ml:reentrenar)."""

    __tablename__ = "Permisos"

    prm_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prm_clave: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    prm_nom: Mapped[str] = mapped_column(String(100), nullable=False)
    prm_mod: Mapped[str] = mapped_column(String(50), nullable=False)
    prm_act: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reg_usu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relación N:N con Roles.
    roles: Mapped[list["Roles"]] = relationship(
        secondary="Rol_Permiso",
        back_populates="permisos",
    )


class RolPermiso(Base):
    """Tabla puente entre Roles y Permisos (relación N:N)."""

    __tablename__ = "Rol_Permiso"

    rp_rol: Mapped[int] = mapped_column(
        Integer, ForeignKey("Roles.rol_cod"), primary_key=True
    )
    rp_prm: Mapped[int] = mapped_column(
        Integer, ForeignKey("Permisos.prm_cod"), primary_key=True
    )
    reg_usu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
