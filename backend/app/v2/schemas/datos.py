"""Schemas de DATOS CRUDOS: metricas, eventos, logs y carga agregada.

Solo hay schemas de salida: estas tablas las escribe el collector y las borra
``proc_retencion_datos``, no se editan a mano. Para insertar se usa POST con el
cuerpo tal cual, porque las columnas son las de la tabla (ver ``routers/datos``).
"""

from __future__ import annotations

from datetime import datetime

from app.v2.schemas.comun import Salida


class MetricaOut(Salida):
    met_cod: int
    met_ins: int
    met_prd: int | None = None
    met_fec: datetime
    met_json: str


class EventoOut(Salida):
    eve_cod: int
    eve_ins: int
    eve_prd: int | None = None
    eve_sid: int | None = None
    eve_fec: datetime
    eve_dur: int | None = None
    eve_cpu: int | None = None
    eve_lreads: int | None = None
    eve_wait: str | None = None
    eve_sql: str | None = None


class LogSQLOut(Salida):
    lgs_cod: int
    lgs_ins: int
    lgs_prd: int | None = None
    lgs_fec: datetime
    lgs_niv: str | None = None
    lgs_msg: str | None = None


class EstadisticaCargaOut(Salida):
    wks_cod: int
    wks_ins: int
    wks_fec: datetime
    wks_json: str