"""Modelos de SISTEMA: los parametros del backend y el registro de auditoria.

``configuracion_sistema`` es la tabla de clave/valor del bloque 8 del esquema
(no lleva ``cfg_cod`` porque ``cfg_clave`` ya es la clave natural). ``auditoria``
guarda quien hizo que accion sobre que recurso, para poder responder
"¿quien cambio este umbral y cuando?".
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Identity, Integer, String
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


class Auditoria(Base):
    """Registro de acciones: quien hizo que, sobre que recurso, con que resultado.

    La escribe el middleware ``app/v2/auditoria.py`` en cada peticion que cambia
    datos (POST/PUT/PATCH/DELETE) sobre ``/api/v2``. No tiene baja logica: es un
    historial que no se borra. ``aud_usu`` queda en NULL cuando la peticion no
    traia un token valido (por ejemplo, un login fallido).
    """

    __tablename__ = "auditoria"
    __table_args__ = {"schema": "dbo"}

    aud_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    aud_usu: Mapped[int | None] = mapped_column(Integer)
    aud_accion: Mapped[str] = mapped_column(String(10), nullable=False)
    aud_recurso: Mapped[str] = mapped_column(String(200), nullable=False)
    aud_resultado: Mapped[int | None] = mapped_column(Integer)
    aud_ip: Mapped[str | None] = mapped_column(String(45))
    aud_fec: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)