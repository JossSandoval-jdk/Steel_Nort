"""Schemas (DTOs) para la API de autenticacion.

Define los objetos de entrada/salida usando Pydantic v2. La separacion
en paquetes permite escalar: cada dominio nuevo (alertas, reportes, ML)
distribuye sus propios schemas aqui.
"""

from __future__ import annotations

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Cuerpo del POST /auth/login.

    ``usu_ema`` (email) es el campo que identifica al usuario en la
    tabla Usuarios. Se valida formato de email y longitud minima de la
    clave.
    """

    email: EmailStr = Field(..., description="Correo del usuario (usu_ema)")
    password: str = Field(..., min_length=8, description="Contrasena (usu_pwd)")


class UsuarioOut(BaseModel):
    """Representacion publica (de salida) de un usuario.

    Excluye datos sensibles como ``usu_pwd`` para no exponerlos en la
    API. Se usa en respuestas de login y de autenticacion.
    """

    usu_cod: int
    usu_nom: str
    usu_ema: EmailStr
    usu_rol: str
    usu_ini: str
    usu_act: bool

    model_config = {"from_attributes": True}


class UsuarioCreate(BaseModel):
    """Datos necesarios para crear un usuario."""

    usu_nom: str = Field(..., min_length=1, max_length=100)
    usu_ema: EmailStr
    password: str = Field(..., min_length=8, max_length=256)
    usu_rol: Literal["Administrador", "Supervisor", "Operador"]
    usu_ini: str = Field(..., min_length=1, max_length=4)


class UsuarioUpdate(BaseModel):
    """Campos editables de un usuario."""

    usu_nom: str | None = Field(default=None, min_length=1, max_length=100)
    usu_ema: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)
    usu_rol: Literal["Administrador", "Supervisor", "Operador"] | None = None
    usu_ini: str | None = Field(default=None, min_length=1, max_length=4)
    usu_act: bool | None = None


class PermisosOut(BaseModel):
    """Permisos efectivos agrupados por rol."""

    roles: dict[str, list[str]]


class TokenResponse(BaseModel):
    """Respuesta del login exitoso.

    ``access_token``: JWT firmado que identifica la sesion (se guarda
    en memoria en el frontend).
    ``csrf_token``: token de validacion por request (se guarda en
    localStorage en el frontend) y debe coincidir con la cookie para
    cada peticion protegida.
    """

    access_token: str
    csrf_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    usuario: UsuarioOut


class SesionOut(BaseModel):
    """Representacion de una sesion registrada en la BD."""

    ses_cod: int
    ses_usu: int
    ses_fec_ini: datetime
    ses_fec_fin: datetime | None
    ses_ip: str | None
    ses_est: str

    model_config = {"from_attributes": True}