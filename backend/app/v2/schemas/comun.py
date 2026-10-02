"""Piezas comunes a todos los endpoints: paginado y envoltorio de respuesta."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Salida(BaseModel):
    """Base de los schemas de respuesta: leen los atributos del modelo ORM."""

    model_config = ConfigDict(from_attributes=True)


class Paginado(BaseModel):
    """Parametros de paginacion y orden de un listado."""

    pagina: int = 1
    tamano: int = 50
    orden: str | None = None


def paginado(
    pagina: Annotated[int, Query(ge=1, description="Pagina (1 = la primera)")] = 1,
    tamano: Annotated[int, Query(ge=1, le=500, description="Filas por pagina")] = 50,
    orden: Annotated[
        str | None,
        Query(description='Columnas separadas por coma; "-" delante = descendente. Ej. "-ses_fec_ini"'),
    ] = None,
) -> Paginado:
    """Dependencia de FastAPI para los tres parametros de listado."""
    return Paginado(pagina=pagina, tamano=tamano, orden=orden)


class Pagina(BaseModel, Generic[T]):
    """Respuesta de un listado paginado."""

    total: int = Field(description="Filas que cumplen el filtro, sin paginar")
    pagina: int
    tamano: int
    items: list[T] = []


class Mensaje(BaseModel):
    """Respuesta de las operaciones que no devuelven la entidad."""

    detalle: str
    id: int | str | None = None


class Salud(Salida):
    """Estado de la API y de la base de datos."""

    app: str
    version: str
    base: str | None = None
    servidor: str | None = None
    tablas_ok: int = 0
    tablas_faltantes: list[str] = []
    utc: datetime | None = None