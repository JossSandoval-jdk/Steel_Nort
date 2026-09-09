"""DTOs basicos para los dominios operativos de SteelNort."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EventoSesionOut(ORMModel):
    evt_cod: int
    evt_ses: int
    evt_min: int
    evt_tip: str
    evt_desc: str
    evt_color: str
    fec_reg: datetime


class SesionDetalleOut(ORMModel):
    ses_cod: int
    ses_usu: int
    ses_fec_ini: datetime
    ses_fec_fin: datetime | None
    ses_ip: str | None
    ses_usr_agt: str | None
    ses_est: str
    eventos: list[EventoSesionOut] = []


class NodoOut(ORMModel):
    ndo_cod: int
    ndo_nom: str
    ndo_ubic: str | None
    ndo_ip: str
    ndo_tipo: str
    ndo_est: str
    ndo_uptime: int


class NodoCreate(BaseModel):
    ndo_nom: str = Field(..., min_length=1, max_length=100)
    ndo_ubic: str | None = Field(default=None, max_length=150)
    ndo_ip: str = Field(..., min_length=1, max_length=45)
    ndo_tipo: str = "scada"


class ServicioOut(ORMModel):
    svc_cod: int
    svc_ndo: int
    svc_nom: str
    svc_desc: str | None
    svc_est: str
    svc_uptime_pct: Decimal


class ServicioCreate(BaseModel):
    svc_ndo: int
    svc_nom: str = Field(..., min_length=1, max_length=100)
    svc_desc: str | None = Field(default=None, max_length=200)


class AlertaOut(ORMModel):
    alt_cod: int
    alt_ndo: int | None
    alt_svc: int | None
    alt_usu: int | None
    alt_prd: int | None
    alt_tipo: str
    alt_sev: str
    alt_titulo: str
    alt_diag: str | None
    alt_fec: datetime
    alt_resu: bool


class AlertaCreate(BaseModel):
    alt_ndo: int | None = None
    alt_svc: int | None = None
    alt_prd: int | None = None
    alt_tipo: str = Field(..., max_length=50)
    alt_sev: str = Field(..., max_length=15)
    alt_titulo: str = Field(..., max_length=200)
    alt_diag: str | None = Field(default=None, max_length=500)


class CausaRaizOut(ORMModel):
    cra_cod: int
    cra_alt: int
    cra_padre: int | None
    cra_nivel: str
    cra_etiq: str
    cra_tono: str


class HeatmapOut(ORMModel):
    hma_cod: int
    hma_fec: date
    hma_hora: int
    hma_sev: str
    hma_cant: int


class ConfiguracionOut(ORMModel):
    cfg_cod: int
    cfg_clave: str
    cfg_valor: str
    cfg_desc: str | None


class ConfiguracionCreate(BaseModel):
    cfg_clave: str = Field(..., min_length=1, max_length=100)
    cfg_valor: str = Field(..., max_length=500)
    cfg_desc: str | None = Field(default=None, max_length=200)


class ModeloMLOut(ORMModel):
    mdl_cod: int
    mdl_nom: str
    mdl_tipo: str
    mdl_umbral_pct: Decimal
    mdl_vars: str | None
    mdl_hparms: str | None
    mdl_ruta_art: str | None
    mdl_act: bool
    mdl_fec_entr: datetime | None


class PrediccionMLOut(ORMModel):
    prd_cod: int
    prd_mdl: int
    prd_ndo: int
    prd_fec: datetime
    prd_es_anom: bool
    prd_score: Decimal
    prd_umbral: Decimal
    prd_feats: str | None
    prd_expl: str | None


class ReporteOut(ORMModel):
    rpt_cod: int
    rpt_usu: int
    rpt_tipo: str
    rpt_titulo: str
    rpt_params: str | None
    rpt_ruta_arch: str | None
    rpt_est: str
    rpt_fec_gen: datetime