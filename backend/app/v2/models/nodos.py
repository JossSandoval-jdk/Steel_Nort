"""Modelos de NODOS: que se monitorea y de donde viene la carga.

``instancias`` es el maestro (host + puerto, unico en el esquema) y
``sesiones_sql`` cuelga de el. Ambas son de auditoria simple: las escribe el
collector, no las edita nadie a mano.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Identity, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.utils import utc_now
from app.v2.database import Base


class Instancia(Base):
    """Nodo de SQL Server vigilado.

    ``ins_fec_alta`` es la referencia del trigger ``TR_prd_instancia_valida``:
    una prediccion no puede empezar antes de que el nodo entrara en
    vigilancia, asi que la escribe el collector y no se cambia despues.
    """

    __tablename__ = "instancias"
    __table_args__ = {"schema": "dbo"}

    ins_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    ins_nom: Mapped[str] = mapped_column(String(100), nullable=False)
    ins_host: Mapped[str] = mapped_column(String(150), nullable=False)
    ins_puerto: Mapped[int] = mapped_column(Integer, nullable=False, default=1433)
    ins_fec_alta: Mapped[datetime | None] = mapped_column(DateTime)
    ins_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="A")
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class SesionSQL(Base):
    """Conexion activa contra una instancia, con su ventana de vida.

    Solo se guarda lo que distingue conexiones: ``ssq_usr`` casi siempre
    coincide con el resto porque todas usan el mismo login.
    """

    __tablename__ = "sesiones_sql"
    __table_args__ = {"schema": "dbo"}

    ssq_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    ssq_ins: Mapped[int] = mapped_column(ForeignKey("dbo.instancias.ins_cod"), nullable=False)
    ssq_sid: Mapped[int] = mapped_column(Integer, nullable=False)
    ssq_usr: Mapped[str | None] = mapped_column(String(128))
    ssq_host: Mapped[str | None] = mapped_column(String(150))
    ssq_prog: Mapped[str | None] = mapped_column(String(100))
    ssq_fec_ini: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ssq_fec_fin: Mapped[datetime | None] = mapped_column(DateTime)
    ssq_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="A")
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)