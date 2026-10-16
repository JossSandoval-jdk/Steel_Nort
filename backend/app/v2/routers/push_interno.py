"""Rutas internas para el servidor Node.js (envío de Web Push).

No se exponen al frontend. Se protegen con el header ``X-Internal-Token``
que debe coincidir con ``V2_INTERNAL_TOKEN`` del .env. En producción, además,
debería comprobarse la IP de origen.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.v2.config import settings
from app.v2.database import get_db
from app.v2.services import notificaciones as servicio

router = APIRouter(prefix="/internal", tags=["internal"])


def verificar_token(
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> None:
    """Comprueba el token compartido con Node (settings.internal_token)."""
    esperado = settings.internal_token
    if not esperado:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_TOKEN no configurado en el servidor.",
        )
    if x_internal_token != esperado:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token interno inválido.",
        )


class SuscripcionPushOut(BaseModel):
    psu_cod: int
    usu_cod: int
    psu_endpoint: str
    psu_p256dh: str
    psu_auth: str


@router.get(
    "/push/suscripciones",
    response_model=list[SuscripcionPushOut],
    dependencies=[Depends(verificar_token)],
    summary="Suscripciones push activas (para Node)",
)
def listar_suscripciones(db: Annotated[Session, Depends(get_db)]):
    return servicio.suscripciones_activas(db)


@router.post(
    "/push/{psu_cod}/uso",
    dependencies=[Depends(verificar_token)],
    summary="Marcar una suscripción como usada (para Node)",
)
def marcar_uso(psu_cod: int, db: Annotated[Session, Depends(get_db)]):
    servicio.marcar_uso(db, psu_cod)
    return {"detalle": "ok"}