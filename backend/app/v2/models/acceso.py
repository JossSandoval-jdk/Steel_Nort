"""Modelos de ACCESO: usuarios, roles, permisos, asignaciones y sesiones.

Las cinco tablas del bloque 2 del esquema. Se agrupan aqui porque comparten
rasgo: se editan a mano y por eso son las unicas con ``*_est`` de dos valores
(A/I) y con las cuatro columnas de auditoria.

Convenciones (las mismas del esquema):
  * el nombre de la columna es el del SQL (``rol_cod``, ``usu_log``...),
  * ``reg_usu``/``fec_reg`` = quien creo la fila y cuando,
  * ``eli_usu``/``fec_eli`` = baja logica,
  * ``fec_reg`` con ``default=utc_now`` cubre el DEFAULT del script SQL.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Identity, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.utils import utc_now
from app.v2.database import Base


class Rol(Base):
    """Catalogo de roles. Los permisos de cada uno estan en ``rol_permiso``."""

    __tablename__ = "rol"
    __table_args__ = {"schema": "dbo"}

    rol_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    rol_nom: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    rol_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="A")
    reg_usu: Mapped[int | None] = mapped_column(Integer)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    eli_usu: Mapped[int | None] = mapped_column(Integer)
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)


class Permiso(Base):
    """Permiso atomico. Se usa como ``per_mod:per_acc`` (p. ej. ``datos:leer``)."""

    __tablename__ = "permiso"
    __table_args__ = {"schema": "dbo"}

    per_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    per_acc: Mapped[str] = mapped_column(String(30), nullable=False)
    per_mod: Mapped[str] = mapped_column(String(30), nullable=False)
    per_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="A")
    reg_usu: Mapped[int | None] = mapped_column(Integer)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    eli_usu: Mapped[int | None] = mapped_column(Integer)
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)


class Usuario(Base):
    """Cuenta de acceso. El login es por ``usu_log``, no por correo.

    ``usu_cla`` guarda el hash bcrypt de la clave: el servicio de acceso lo
    cifra al escribir y ningun schema de salida lo expone.
    """

    __tablename__ = "usuario"
    __table_args__ = {"schema": "dbo"}

    usu_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    usu_nom: Mapped[str] = mapped_column(String(100), nullable=False)
    usu_log: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    usu_cla: Mapped[str] = mapped_column(String(255), nullable=False)
    usu_ema: Mapped[str | None] = mapped_column(String(100))
    usu_dni: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    usu_tel: Mapped[str | None] = mapped_column(String(20))
    usu_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="A")
    rol_cod: Mapped[int] = mapped_column(ForeignKey("dbo.rol.rol_cod"), nullable=False)
    reg_usu: Mapped[int | None] = mapped_column(Integer)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    eli_usu: Mapped[int | None] = mapped_column(Integer)
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)


class RolPermiso(Base):
    """Asigna un permiso a un rol. El par (rol, permiso) es unico."""

    __tablename__ = "rol_permiso"
    __table_args__ = {"schema": "dbo"}

    rp_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    rol_cod: Mapped[int] = mapped_column(ForeignKey("dbo.rol.rol_cod"), nullable=False)
    per_cod: Mapped[int] = mapped_column(ForeignKey("dbo.permiso.per_cod"), nullable=False)
    rp_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="A")
    reg_usu: Mapped[int | None] = mapped_column(Integer, ForeignKey("dbo.usuario.usu_cod"))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    eli_usu: Mapped[int | None] = mapped_column(Integer, ForeignKey("dbo.usuario.usu_cod"))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)


class Sesion(Base):
    """Sesion de la API: la abre el login y la cierra el logout.

    No lleva ``fec_eli``: ``ses_est`` ya dice en que punto del ciclo esta
    (``A`` abierta, ``C`` cerrada, ``E`` expirada).
    """

    __tablename__ = "sesiones"
    __table_args__ = {"schema": "dbo"}

    ses_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    ses_usu: Mapped[int] = mapped_column(ForeignKey("dbo.usuario.usu_cod"), nullable=False)
    ses_fec_ini: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    ses_fec_fin: Mapped[datetime | None] = mapped_column(DateTime)
    ses_ip: Mapped[str | None] = mapped_column(String(45))
    ses_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="A")
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)