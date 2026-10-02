"""Modelo de SISTEMA: los parametros de comportamiento del backend.

Una sola tabla de clave/valor del bloque 8 del esquema. No lleva ``cfg_cod``
porque ``cfg_clave`` ya es la clave natural.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.utils import utc_now
from app.v2.database import Base


class Configuracion(Base):
    """Parametro del sistema: ``cfg_clave -> cfg_valor``.

    Ejemplos: ``detector.cuantil``, ``retencion.metricas_dias``,
    ``alertas.ventana_n_de_m``. Deshabilitar un parametro es una baja logica
    real, asi que la tabla conserva la auditoria completa.
    """

    __tablename__ = "configuracion_sistema"
    __table_args__ = {"schema": "dbo"}

    cfg_clave: Mapped[str] = mapped_column(String(100), primary_key=True)
    cfg_valor: Mapped[str] = mapped_column(String(500), nullable=False)
    reg_usu: Mapped[int | None] = mapped_column(Integer)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    eli_usu: Mapped[int | None] = mapped_column(Integer)
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)