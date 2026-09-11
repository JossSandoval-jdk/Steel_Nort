"""Modelo de muestras normales para reentrenamiento.

Almacena SOLO las muestras que el detector clasifica como normales
(es_anomalia=False). Estas se usan para reentrenar el modelo periodicamente.

Diseño:
  - Cada fila es una captura del daemon (~7s) con las variables del modelo.
  - Se guarda el nodo, timestamp, score del detector, y las features como JSON.
  - Se usa una tabla separada de Predicciones_ML para no mezclar
    lo normal (entrenamiento) con lo anómalo (diagnóstico).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MuestrasNormales(Base):
    __tablename__ = "Muestras_Normales"

    mno_cod: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mno_ndo: Mapped[int] = mapped_column(ForeignKey("Nodos_SCADA.ndo_cod"), nullable=False)
    mno_fec: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    mno_score: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    mno_umbral: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    mno_feats: Mapped[str | None] = mapped_column(Text)
    mno_ventana: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    reg_usu: Mapped[str | None] = mapped_column(String(60))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eli_usu: Mapped[str | None] = mapped_column(String(60))
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)
