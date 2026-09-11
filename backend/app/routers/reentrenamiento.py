"""Endpoints de reentrenamiento del modelo ML.

  POST /reentrenar              -> ejecuta reentrenamiento (solo Admin).
  GET  /reentrenamiento/estado  -> estado del modelo activo y último retrain.

FLUJO:
  1. Admin dispara POST /reentrenar con dias=N.
  2. El servicio lee Muestras_Normales (SOLO normales).
  3. Filtra outliers, re-entrena IsolationForest.
  4. Si es mejor → reemplaza artefactos y registra en Modelos_ML.
  5. Las anomalías NUNCA se usan para entrenar.

Solo el rol Administrador puede disparar reentrenamiento.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.model_usuario import Usuarios
from app.routers.auth import get_current_user
from app.services.permisos import require_permission
from app.services.reentrenamiento import estado_reentrenamiento, reentrenar

router = APIRouter(prefix="/reentrenamiento", tags=["reentrenamiento"])


@router.post("")
def ejecutar_reentrenamiento(
    current: Annotated[Usuarios, Depends(require_permission("ml:reentrenar"))],
    db: Session = Depends(get_db),
    dias: Annotated[int, Query(ge=1, le=90)] = 7,
    force: bool = False,
) -> dict:
    """Ejecuta el pipeline de reentrenamiento usando SOLO muestras normales.

    - ``dias``: número de días hacia atrás para leer muestras normales.
    - ``force``: si es True, reemplaza el modelo aunque el actual sea mejor.

    Las anomalías NUNCA se usan para entrenar. Solo las muestras
    que el detector clasificó como normales alimentan el reentrenamiento.
    """
    resultado = reentrenar(dias=dias, force=force)
    return resultado


@router.get("/estado")
def estado(
    _current: Annotated[Usuarios, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict:
    """Estado del modelo activo y del último reentrenamiento."""
    return estado_reentrenamiento(db)
