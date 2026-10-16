"""Servicio de DETECCION: alertas, variables que las explican y causa raiz.

Reglas propias de esta familia:

  * una alerta se resuelve (``alt_est = 'S'``) o se descarta como falso
    positivo (``alt_est = 'F'``). El trigger ``TR_alertas_hma_rollup`` saca las
    ``F`` del mapa de calor, asi que marcar asi es la forma de "borrar" una
    alerta sin perderla;
  * resolver exige ``alt_usu`` y ``alt_fec_resu`` (lo comprueba un CHECK de la
    base), asi que el servicio los escribe si no vienen;
  * variables y causas cuelgan de la alerta: si la alerta se da de baja, ellas
    tambien.
  * cuando se crea una alerta C o A, el trigger ``TR_alertas_notifica`` inserta
    una fila en ``notificaciones``. Aqui avisamos a Node para que envie el
    Web Push (best-effort: si falla, no tumba la alerta).
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.utils import utc_now
from app.v2.models.deteccion import Alerta, AlertaVariable, CausaRaiz, HeatmapAnomalia
from app.v2.models.notificaciones import Notificacion
from app.v2.schemas.deteccion import AlertaCreate, AlertaUpdate, CausaRaizCreate
from app.v2.services import crud
from app.v2.services.notificador import notificar_push

log = logging.getLogger("steelnort.v2.deteccion")


# =====================================================================
# ALERTAS
# =====================================================================


def listar_alertas(
    db: Session,
    pagina: int,
    tamano: int,
    orden: str,
    instancia: int | None,
    estado: str | None,
    severidad: str | None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
):
    filtros = {}
    if instancia:
        filtros["alt_ins"] = instancia
    if estado:
        filtros["alt_est"] = estado
    if severidad:
        filtros["alt_sev"] = severidad
    return crud.listar(
        db,
        Alerta,
        orden or "-alt_fec",
        filtros or None,
        pagina=pagina,
        tamano=tamano,
        columna_fecha="alt_fec",
        desde=desde,
        hasta=hasta,
    )


def obtener_alerta(db: Session, cod: int) -> Alerta:
    return crud.obtener_o_404(db, Alerta, "alt_cod", cod)


def crear_alerta(db: Session, datos: AlertaCreate, actor: int | None) -> Alerta:
    campos = datos.model_dump(exclude_none=True)
    campos.setdefault("alt_fec", utc_now())
    alerta = crud.nuevo(db, Alerta, campos, actor)

    # El trigger TR_alertas_notifica ya inserto la notificacion en BD si la
    # severidad es C o A. Aqui avisamos a Node para que emita por WebSocket
    # y envie el Web Push a todos los suscriptores.
    if alerta.alt_sev in ("C", "A"):
        _avisar_push(db, alerta)

    return alerta


def _avisar_push(db: Session, alerta: Alerta) -> None:
    """Notifica a Node para que envie el Web Push. Nunca lanza excepcion."""
    try:
        notificacion = db.scalars(
            select(Notificacion)
            .where(Notificacion.not_ref_cod == alerta.alt_cod)
            .order_by(Notificacion.not_cod.desc())
            .limit(1)
        ).first()

        if notificacion is None:
            log.debug(
                "No se encontro notificacion para la alerta %s (severidad=%s).",
                alerta.alt_cod,
                alerta.alt_sev,
            )
            return

        notificar_push(
            titulo=notificacion.not_titulo,
            detalle=notificacion.not_detalle,
            severidad=notificacion.not_sev,
            url=notificacion.not_url,
            not_cod=notificacion.not_cod,
        )
    except Exception as exc:
        # El push es un extra: NUNCA debe tumbar la creacion de la alerta.
        log.warning(
            "No se pudo avisar a Node del push para la alerta %s: %s",
            alerta.alt_cod,
            exc,
        )


def actualizar_alerta(db: Session, cod: int, datos: AlertaUpdate, actor: int | None) -> Alerta:
    """Resolver o descartar completa los campos que la base exige."""
    campos = datos.model_dump(exclude_unset=True)
    if campos.get("alt_est") in {"S", "F"}:
        campos.setdefault("alt_fec_resu", utc_now())
        campos.setdefault("alt_usu", actor)
    return crud.cambiar(db, Alerta, "alt_cod", cod, campos)


def eliminar_alerta(db: Session, cod: int, actor: int | None) -> Alerta:
    return crud.borrar(db, Alerta, "alt_cod", cod, columna_estado="alt_est", actor=actor)


# =====================================================================
# VARIABLES EXPLICATIVAS
# =====================================================================


def listar_alerta_variables(db: Session, pagina: int, tamano: int, orden: str, alerta: int | None):
    return crud.listar(
        db,
        AlertaVariable,
        orden or "alv_alt,alv_rank",
        filtros={"alv_alt": alerta} if alerta else None,
        pagina=pagina,
        tamano=tamano,
    )


def registrar_variables(db: Session, filas: list[dict]) -> list[AlertaVariable]:
    """El detector manda las variables de varias alertas en un solo envio."""
    if not filas:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lista de variables vacia")
    return crud.nuevo_lote(db, AlertaVariable, filas)


# =====================================================================
# CAUSA RAIZ
# =====================================================================


def listar_causas(db: Session, pagina: int, tamano: int, orden: str, alerta: int | None, nivel: str | None):
    filtros = {}
    if alerta:
        filtros["cra_alt"] = alerta
    if nivel:
        filtros["cra_nivel"] = nivel
    return crud.listar(db, CausaRaiz, orden or "cra_alt,cra_cod", filtros or None, pagina=pagina, tamano=tamano)


def crear_causa(db: Session, datos: CausaRaizCreate) -> CausaRaiz:
    return crud.nuevo(db, CausaRaiz, datos.model_dump())


def eliminar_causa(db: Session, cod: int) -> CausaRaiz:
    return crud.borrar(db, CausaRaiz, "cra_cod", cod)


# =====================================================================
# MAPA DE CALOR
# =====================================================================


def listar_heatmap(
    db: Session,
    pagina: int,
    tamano: int,
    orden: str,
    dia: date | None,
    severidad: str | None,
):
    """Mapa de calor por dia, hora y severidad."""
    filtros = {}
    if dia:
        filtros["hma_fec"] = dia
    if severidad:
        filtros["hma_sev"] = severidad
    return crud.listar(
        db,
        HeatmapAnomalia,
        orden or "-hma_fec,hma_hora",
        filtros or None,
        pagina=pagina,
        tamano=tamano,
    )