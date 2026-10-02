"""Schemas de SISTEMA: parametros clave/valor y resumen de la plataforma."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.v2.schemas.comun import Salida


class ConfiguracionOut(Salida):
    cfg_clave: str
    cfg_valor: str
    reg_usu: int | None = None
    fec_reg: datetime
    fec_eli: datetime | None = None


class ConfiguracionCreate(BaseModel):
    cfg_clave: str = Field(min_length=1, max_length=100)
    cfg_valor: str = Field(max_length=500)


class Resumen(BaseModel):
    """Cifras de una linea por tabla, para el tablero."""

    total: int
    ayer: int = 0