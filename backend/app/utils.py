"""Utilidades transversales del backend SteelNort."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Timestamp UTC naive actual (equivale a ``datetime.utcnow()``).

    La API ``datetime.utcnow()`` esta deprecada en Python 3.12+. Las
    columnas de la BD son ``DateTime`` naive, por eso se elimina el
    ``tzinfo`` despues de tomar la hora UTC real.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)