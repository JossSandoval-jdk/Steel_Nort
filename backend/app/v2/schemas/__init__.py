"""Schemas de v2.

Un archivo por familia de tablas (las mismas seis de ``models/``) mas
``comun.py`` con lo transversal. Cada schema es una clase Pydantic normal.
"""

from app.v2.schemas.acceso import (
    PermisoCreate,
    PermisoOut,
    RolCreate,
    RolOut,
    RolPermisoCreate,
    RolPermisoOut,
    SesionOut,
    TokenRespuesta,
    UsuarioCreate,
    UsuarioOut,
    UsuarioUpdate,
)
from app.v2.schemas.comun import Mensaje, Pagina, Paginado, Salida, Salud, paginado
from app.v2.schemas.datos import EstadisticaCargaOut, EventoOut, LogSQLOut, MetricaOut
from app.v2.schemas.deteccion import (
    AlertaCreate,
    AlertaOut,
    AlertaUpdate,
    AlertaVariableOut,
    CausaRaizCreate,
    CausaRaizOut,
    HeatmapAnomaliaOut,
)
from app.v2.schemas.modelo import (
    DerivaMonitorOut,
    ModeloMLCreate,
    ModeloMLOut,
    ModeloMLUpdate,
    PrediccionMLOut,
    ReentrenamientoOut,
    ReentrenamientoPasoOut,
)
from app.v2.schemas.nodos import (
    InstanciaCreate,
    InstanciaOut,
    InstanciaUpdate,
    SesionSQLOut,
)
from app.v2.schemas.sistema import ConfiguracionCreate, ConfiguracionOut

__all__ = [
    "AlertaCreate",
    "AlertaOut",
    "AlertaUpdate",
    "AlertaVariableOut",
    "CausaRaizCreate",
    "CausaRaizOut",
    "ConfiguracionCreate",
    "ConfiguracionOut",
    "DerivaMonitorOut",
    "EstadisticaCargaOut",
    "EventoOut",
    "HeatmapAnomaliaOut",
    "InstanciaCreate",
    "InstanciaOut",
    "InstanciaUpdate",
    "LogSQLOut",
    "Mensaje",
    "MetricaOut",
    "ModeloMLCreate",
    "ModeloMLOut",
    "ModeloMLUpdate",
    "Pagina",
    "Paginado",
    "PermisoCreate",
    "PermisoOut",
    "PrediccionMLOut",
    "ReentrenamientoOut",
    "ReentrenamientoPasoOut",
    "RolCreate",
    "RolOut",
    "RolPermisoCreate",
    "RolPermisoOut",
    "Salida",
    "Salud",
    "SesionOut",
    "SesionSQLOut",
    "TokenRespuesta",
    "UsuarioCreate",
    "UsuarioOut",
    "UsuarioUpdate",
    "paginado",
]