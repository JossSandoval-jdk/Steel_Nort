"""DTOs de telemetria (muestras en vivo e importacion de cargas)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MuestraPayload(BaseModel):
    """Estructura de una muestra enviada por el daemon."""

    nodo: str = Field(..., description="Nombre del nodo que publica")
    ip: str = "0.0.0.0"
    muestra: dict[str, Any] = Field(..., description="Variables de la muestra")


class CargaImportPayload(BaseModel):
    """Carga de trabajo externa para un nodo.

    ``carga`` es una lista de muestras del estilo
    ``{"fec": "2026-09-10 12:00:00" (opcional), "variables": {...}}``.
    La separacion normal/anomalia la hace el mismo detector en lote,
    conservando los timestamps inyectados.
    """

    nodo: str = Field(..., description="Nombre del nodo SCADA destino")
    ip: str = "0.0.0.0"
    carga: list[dict[str, Any]] = Field(
        ..., description="Muestras: [{'fec'?: iso, 'variables': {...}}, ...]"
    )