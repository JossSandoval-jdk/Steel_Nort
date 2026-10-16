"""Modelos de NOTIFICACIONES: historial persistente y suscripciones push.

``notificaciones`` guarda todo lo que se le muestra al usuario en la
campanita. ``push_suscripciones`` guarda los endpoints del navegador que
autorizaron recibir Web Push, uno por dispositivo.

``not_usu_dest = NULL`` significa "para todos": una fila notifica al equipo
completo sin duplicar registros.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.utils import utc_now
from app.v2.database import Base


class Notificacion(Base):
    """Notificación persistente para la campanita del usuario.

    ``not_sev``: ``C`` crítica, ``A`` alta, ``M`` media, ``B`` baja.
    ``not_leida`` y ``fec_leida`` los mantiene un CHECK en la base: si está
    leída, la fecha es obligatoria.

    El trigger ``TR_alertas_notifica`` inserta filas aquí automáticamente
    cuando se abre una alerta con severidad C o A. Eso significa que
    ``implicit_returning`` debe ser ``False`` porque hay un trigger sobre
    ``alertas`` que referencia esta tabla, y SQL Server prohíbe el
    ``OUTPUT inserted.not_cod`` cuando el INSERT dispara otros INSERTs (error 334).
    """

    __tablename__ = "notificaciones"
    __table_args__ = {"schema": "dbo", "implicit_returning": False}

    not_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    not_titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    not_detalle: Mapped[str | None] = mapped_column(String(500))
    not_sev: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    not_tipo: Mapped[str | None] = mapped_column(String(50))
    not_ref_cod: Mapped[int | None] = mapped_column(ForeignKey("dbo.alertas.alt_cod"))
    not_url: Mapped[str | None] = mapped_column(String(200))
    not_leida: Mapped[bool] = mapped_column(nullable=False, default=False)
    not_usu_dest: Mapped[int | None] = mapped_column(ForeignKey("dbo.usuario.usu_cod"))
    fec_creacion: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )
    fec_leida: Mapped[datetime | None] = mapped_column(DateTime)


class PushSuscripcion(Base):
    """Suscripción Web Push de un navegador concreto.

    Un mismo usuario puede tener varias (PC, móvil, tablet). El ``endpoint``
    es único y lo genera el navegador; si el usuario reinstala, cambia y se
    crea una fila nueva. Las caducadas se marcan ``psu_activa = 0``.
    """

    __tablename__ = "push_suscripciones"
    __table_args__ = {"schema": "dbo"}

    psu_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    usu_cod: Mapped[int] = mapped_column(
        ForeignKey("dbo.usuario.usu_cod"), nullable=False
    )
    psu_endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    psu_p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    psu_auth: Mapped[str] = mapped_column(String(255), nullable=False)
    psu_user_agent: Mapped[str | None] = mapped_column(String(300))
    psu_activa: Mapped[bool] = mapped_column(nullable=False, default=True)
    fec_creacion: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )
    fec_ultimo_uso: Mapped[datetime | None] = mapped_column(DateTime)