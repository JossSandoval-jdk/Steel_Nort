"""Schemas de ACCESO: usuarios, roles, permisos, asignaciones y sesiones.

Todos heredan de ``Salida`` para poder devolverse directo desde el modelo ORM.
``usu_cla`` (el hash de la clave) nunca aparece en un schema de salida.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.v2.schemas.comun import Salida

# =====================================================================
# USUARIOS
# =====================================================================


class UsuarioOut(Salida):
    """Usuario tal como lo ve el cliente (sin el hash de la clave)."""

    usu_cod: int
    usu_nom: str
    usu_log: str
    usu_ema: str | None = None
    usu_dni: str | None = None
    usu_tel: str | None = None
    usu_est: str = "A"
    rol_cod: int
    reg_usu: int | None = None
    fec_reg: datetime
    fec_eli: datetime | None = None


class UsuarioCreate(BaseModel):
    """Alta de usuario. La clave viaja como ``password`` y se guarda cifrada.

    ``usu_dni`` es obligatorio porque en la tabla es NOT NULL y unico.
    """

    usu_nom: str = Field(min_length=1, max_length=100)
    usu_log: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=72)
    usu_dni: str = Field(min_length=1, max_length=12)
    rol_cod: int
    usu_ema: EmailStr | None = None
    usu_tel: str | None = Field(default=None, max_length=20)


class UsuarioUpdate(BaseModel):
    """Edicion parcial. Sin ``password`` la clave no cambia."""

    usu_nom: str | None = Field(default=None, min_length=1, max_length=100)
    usu_ema: EmailStr | None = None
    usu_dni: str | None = Field(default=None, max_length=12)
    usu_tel: str | None = Field(default=None, max_length=20)
    rol_cod: int | None = None
    usu_est: str | None = Field(default=None, pattern="^[AI]$")
    password: str | None = Field(default=None, min_length=8, max_length=72)


# =====================================================================
# ROLES, PERMISOS Y ASIGNACIONES
# =====================================================================


class RolOut(Salida):
    rol_cod: int
    rol_nom: str
    rol_est: str = "A"
    fec_reg: datetime


class RolCreate(BaseModel):
    rol_nom: str = Field(min_length=1, max_length=50)


class PermisoOut(Salida):
    per_cod: int
    per_acc: str
    per_mod: str
    per_est: str = "A"


class PermisoCreate(BaseModel):
    per_mod: str = Field(min_length=1, max_length=30)
    per_acc: str = Field(min_length=1, max_length=30)


class RolPermisoOut(Salida):
    rp_cod: int
    rol_cod: int
    per_cod: int
    rp_est: str = "A"


class RolPermisoCreate(BaseModel):
    rol_cod: int
    per_cod: int


# =====================================================================
# SESIONES
# =====================================================================


class SesionOut(Salida):
    ses_cod: int
    ses_usu: int
    ses_fec_ini: datetime
    ses_fec_fin: datetime | None = None
    ses_ip: str | None = None
    ses_est: str = "A"


class TokenRespuesta(BaseModel):
    """Lo que devuelve POST /auth/login."""

    access_token: str
    token_type: str = "bearer"
    expira_en_minutos: int
    usuario: UsuarioOut
    rol: str
    permisos: list[str] = []