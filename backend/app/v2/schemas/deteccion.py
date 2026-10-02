"""Schemas de DETECCION: alertas, sus variables, causas raiz y mapa de calor."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.v2.schemas.comun import Salida


class AlertaOut(Salida):
    alt_cod: int
    alt_prd: int | None = None
    alt_ins: int | None = None
    alt_usu: int | None = None
    alt_tipo: str
    alt_sev: str
    alt_titulo: str
    alt_diag: str | None = None
    alt_est: str = "A"
    alt_fec: datetime
    alt_fec_resu: datetime | None = None


class AlertaCreate(BaseModel):
    alt_tipo: str = Field(min_length=1, max_length=50)
    alt_sev: str = Field(pattern="^[CAMB]$")
    alt_titulo: str = Field(min_length=1, max_length=200)
    alt_diag: str | None = Field(default=None, max_length=500)
    alt_fec: datetime | None = None
    alt_prd: int | None = None
    alt_ins: int | None = None


class AlertaUpdate(BaseModel):
    alt_est: str | None = Field(default=None, pattern="^[ARSF]$")
    alt_usu: int | None = None
    alt_fec_resu: datetime | None = None
    alt_diag: str | None = Field(default=None, max_length=500)


class AlertaVariableOut(Salida):
    alv_cod: int
    alv_alt: int
    alv_var: str
    alv_valor: float | None = None
    alv_z: float | None = None
    alv_contrib: float | None = None
    alv_rank: int | None = None


class CausaRaizOut(Salida):
    cra_cod: int
    cra_alt: int
    cra_padre: int | None = None
    cra_nivel: str
    cra_etiq: str


class CausaRaizCreate(BaseModel):
    cra_alt: int
    cra_nivel: str = Field(pattern="^[RWL]$")
    cra_etiq: str = Field(min_length=1, max_length=200)
    cra_padre: int | None = None


class HeatmapAnomaliaOut(Salida):
    hma_cod: int
    hma_fec: date
    hma_hora: int
    hma_sev: str
    hma_cant: int = 0