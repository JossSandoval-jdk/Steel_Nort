"""Schemas de NODOS: instancias vigiladas y conexiones observadas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.v2.schemas.comun import Salida


class InstanciaOut(Salida):
    ins_cod: int
    ins_nom: str
    ins_host: str
    ins_puerto: int
    ins_fec_alta: datetime | None = None
    ins_est: str = "A"
    fec_reg: datetime


class InstanciaCreate(BaseModel):
    ins_nom: str = Field(min_length=1, max_length=100)
    ins_host: str = Field(min_length=1, max_length=150)
    ins_puerto: int = Field(default=1433, ge=1, le=65535)
    ins_fec_alta: datetime | None = None


class InstanciaUpdate(BaseModel):
    ins_nom: str | None = Field(default=None, min_length=1, max_length=100)
    ins_fec_alta: datetime | None = None
    ins_est: str | None = Field(default=None, pattern="^[AI]$")


class SesionSQLOut(Salida):
    ssq_cod: int
    ssq_ins: int
    ssq_sid: int
    ssq_usr: str | None = None
    ssq_host: str | None = None
    ssq_prog: str | None = None
    ssq_fec_ini: datetime
    ssq_fec_fin: datetime | None = None
    ssq_est: str = "A"