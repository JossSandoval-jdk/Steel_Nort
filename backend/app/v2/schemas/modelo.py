"""Schemas de MODELO: despliegue, predicciones, deriva y reentrenamiento."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.v2.schemas.comun import Salida


class ModeloMLOut(Salida):
    mdl_cod: int
    mdl_nom: str
    mdl_tipo: str
    mdl_cuantil: float
    mdl_umbral: float | None = None
    mdl_vars: str | None = None
    mdl_hparms: str | None = None
    mdl_ruta_art: str | None = None
    mdl_est: str = "C"
    mdl_fec_entr: datetime | None = None
    reg_usu: int | None = None
    fec_reg: datetime
    fec_eli: datetime | None = None


class ModeloMLCreate(BaseModel):
    mdl_nom: str = Field(min_length=1, max_length=100)
    mdl_tipo: str = Field(
        default="ensemble_z",
        pattern="^(isolation_forest|copod|ensemble_z|lof|ocsvm|elliptic)$",
    )
    mdl_cuantil: float = Field(default=0.010, gt=0, lt=1)
    mdl_umbral: float | None = None
    mdl_vars: str | None = None
    mdl_hparms: str | None = None
    mdl_ruta_art: str | None = None


class ModeloMLUpdate(BaseModel):
    mdl_nom: str | None = Field(default=None, min_length=1, max_length=100)
    mdl_umbral: float | None = None
    mdl_vars: str | None = None
    mdl_hparms: str | None = None
    mdl_ruta_art: str | None = None
    mdl_est: str | None = Field(default=None, pattern="^[ACI]$")
    mdl_fec_entr: datetime | None = None


class PrediccionMLOut(Salida):
    prd_cod: int
    prd_mdl: int
    prd_ins: int
    prd_ini: datetime
    prd_fin: datetime
    prd_sco_iso: float | None = None
    prd_sco_cop: float | None = None
    prd_sco_ens: float
    prd_umbral: float
    prd_zona: str = "N"
    prd_es_anom: bool = False
    prd_feats: str | None = None
    fec_reg: datetime


class DerivaMonitorOut(Salida):
    drv_cod: int
    drv_mdl: int
    drv_fec: datetime
    drv_var: str
    drv_metrica: str = "P"
    drv_valor: float
    drv_est: str = "E"


class ReentrenamientoOut(Salida):
    ren_cod: int
    ren_mdl_origen: int
    ren_mdl_nuevo: int | None = None
    ren_disparo: str
    ren_motivo: str | None = None
    ren_fec_sol: datetime
    ren_dat_ini: datetime | None = None
    ren_dat_fin: datetime | None = None
    ren_criterio: str | None = None
    ren_n_train: int | None = None
    ren_f1_antes: float | None = None
    ren_f1_desp: float | None = None
    ren_fpr_antes: float | None = None
    ren_fpr_desp: float | None = None
    ren_est: str = "P"
    ren_fec_apr: datetime | None = None
    ren_obs: str | None = None
    fec_reg: datetime


class ReentrenamientoPasoOut(Salida):
    rep_ren: int
    rep_orden: int
    rep_paso: str
    rep_est: str = "P"
    rep_fec_ini: datetime | None = None
    rep_fec_fin: datetime | None = None
    rep_detalle: str | None = None