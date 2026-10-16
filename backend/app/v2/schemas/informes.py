"""Schemas de INFORMES: resumen del periodo, anomalias y archivos exportados.

Los tres alimentan la pantalla Reportes v2. Salen de las tablas reales de la
v2; si no hay filas en el rango, las listas van vacias (no hay datos de ejemplo).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AnomaliaOut(BaseModel):
    """Una variable fuera de rango que explico una alerta."""

    alv_cod: int
    alerta: int
    fecha: datetime
    variable: str
    valor: float | None = None
    z: float | None = None
    severidad: str
    estado: str
    instancia: str | None = None
    titulo: str


class AlertaInformeOut(BaseModel):
    """Cabecera de alerta con el nombre de su nodo, para el historial."""

    alt_cod: int
    alt_fec: datetime
    alt_titulo: str
    alt_sev: str
    alt_est: str
    alt_diag: str | None = None
    instancia: str | None = None
    alt_fec_resu: datetime | None = None


class PorInstancia(BaseModel):
    """Fila del resumen por nodo: que tan cargado y que tan anomalo estuvo."""

    instancia: str | None = None
    ventanas: int = 0
    anomalias: int = 0
    alertas: int = 0


class PorEvento(BaseModel):
    """Fila del resumen por tipo de evento SQL (duraciones en ms)."""

    tipo: str
    ejecuciones: int = 0
    dur_prom_ms: float = 0.0
    con_espera: int = 0


class ResumenInforme(BaseModel):
    """Todo lo agregado del periodo, en una sola respuesta."""

    desde: datetime | None = None
    hasta: datetime | None = None
    ventanas: int = 0
    anomalias: int = 0
    alertas: int = 0
    por_severidad: dict[str, int] = {}
    eventos: int = 0
    logs: int = 0
    por_instancia: list[PorInstancia] = []
    por_evento: list[PorEvento] = []


class GenerarInforme(BaseModel):
    """Peticion de exportacion: que dataset y en que formato."""

    tipo: str = "resumen"    # resumen | alertas | anomalias
    formato: str = "csv"     # csv | json
    desde: datetime | None = None
    hasta: datetime | None = None


class ArchivoExportado(BaseModel):
    """Metadatos de un archivo ya generado, listo para descargar."""

    nombre: str
    bytes: int
    modificado: datetime


class ArchivoGenerado(ArchivoExportado):
    """Respuesta de la exportacion, con cuantas filas se escribieron."""

    tipo: str
    formato: str
    filas: int
