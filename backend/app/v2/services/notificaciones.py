"""Servicio de NOTIFICACIONES: listar, marcar leídas, suscribir push.

Las notificaciones se crean solas por trigger en la base cuando se abre
una alerta C/A. Este servicio las consulta, las marca como leídas y
mantiene la tabla de suscripciones push.

La consulta "para mí" incluye:
  - las globales (``not_usu_dest IS NULL``)
  - las dirigidas a mi ``usu_cod``

OJO SQL Server: para comparar booleanos se usa ``col == True/False``, NO
``col.is_(True/False)``, porque ``.is_()`` genera ``IS 1`` / ``IS 0`` que
es sintaxis PostgreSQL, no T-SQL. Para NULL sí se usa ``.is_(None)``.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.utils import utc_now
from app.v2.models.notificaciones import Notificacion, PushSuscripcion
from app.v2.services import crud


# =====================================================================
# LISTAR
# =====================================================================


def listar(
    db: Session,
    usu_cod: int,
    *,
    pagina: int = 1,
    tamano: int = 50,
    solo_no_leidas: bool = False,
    severidad: str | None = None,
) -> dict:
    """Listado paginado de notificaciones visibles para un usuario."""
    consulta = select(Notificacion).where(_visible_para(usu_cod))

    if solo_no_leidas:
        consulta = consulta.where(Notificacion.not_leida == False)  # noqa: E712
    if severidad:
        consulta = consulta.where(Notificacion.not_sev == severidad)

    total = int(db.scalar(select(func.count()).select_from(consulta.subquery())) or 0)

    consulta = consulta.order_by(Notificacion.fec_creacion.desc())
    if pagina > 1:
        consulta = consulta.offset((pagina - 1) * tamano)

    return {
        "total": total,
        "pagina": pagina,
        "tamano": tamano,
        "items": list(db.scalars(consulta.limit(tamano)).all()),
    }


def contador_no_leidas(db: Session, usu_cod: int) -> int:
    """Número de notificaciones no leídas visibles para el usuario."""
    return int(
        db.scalar(
            select(func.count(Notificacion.not_cod)).where(
                and_(Notificacion.not_leida == False, _visible_para(usu_cod))  # noqa: E712
            )
        )
        or 0
    )


# =====================================================================
# MARCAR LEÍDAS
# =====================================================================


def marcar_leida(db: Session, not_cod: int, usu_cod: int) -> Notificacion:
    """Marca una notificación como leída.

    Solo el destinatario o alguien con acceso a las globales puede hacerlo.
    Si es global, cualquier usuario autenticado la puede marcar (es
    compartida: la marca es global).
    """
    notif = crud.obtener_o_404(db, Notificacion, "not_cod", not_cod)

    if notif.not_usu_dest is not None and notif.not_usu_dest != usu_cod:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puede marcar como leída una notificación de otro usuario.",
        )

    # Si ya está leída, no hacemos nada.
    if notif.not_leida:
        return notif

    notif.not_leida = True
    notif.fec_leida = utc_now()
    crud.guardar(db, Notificacion)
    db.refresh(notif)
    return notif


def marcar_todas_leidas(db: Session, usu_cod: int) -> int:
    """Marca como leídas todas las no leídas visibles para el usuario.

    Devuelve cuántas se actualizaron. Las globales se marcan también (es
    el precio de compartirlas: si uno las marca, las marca para todos).
    """
    ahora = utc_now()
    resultado = db.execute(
        update(Notificacion)
        .where(and_(Notificacion.not_leida == False, _visible_para(usu_cod)))  # noqa: E712
        .values(not_leida=True, fec_leida=ahora)
    )
    db.commit()
    return int(resultado.rowcount or 0)


# =====================================================================
# PUSH SUSCRIPCIONES
# =====================================================================


def suscribir(
    db: Session, usu_cod: int, endpoint: str, keys: dict, user_agent: str | None
) -> PushSuscripcion:
    """Guarda o actualiza una suscripción push del navegador.

    Si el endpoint ya existe se reactiva y se actualizan las claves (el
    navegador puede regenerarlas). Si no existe, se inserta.
    """
    p256dh = (keys or {}).get("p256dh")
    auth = (keys or {}).get("auth")
    if not p256dh or not auth:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El payload de la suscripción debe traer keys.p256dh y keys.auth.",
        )

    existente = db.scalars(
        select(PushSuscripcion).where(PushSuscripcion.psu_endpoint == endpoint)
    ).first()

    if existente is None:
        suscripcion = PushSuscripcion(
            usu_cod=usu_cod,
            psu_endpoint=endpoint,
            psu_p256dh=p256dh,
            psu_auth=auth,
            psu_user_agent=(user_agent or None),
            psu_activa=True,
            fec_creacion=utc_now(),
        )
        db.add(suscripcion)
        crud.guardar(db, PushSuscripcion)
        db.refresh(suscripcion)
        return suscripcion

    # Ya existía: la reactivamos y actualizamos claves/propietario.
    existente.usu_cod = usu_cod
    existente.psu_p256dh = p256dh
    existente.psu_auth = auth
    existente.psu_user_agent = user_agent or existente.psu_user_agent
    existente.psu_activa = True
    crud.guardar(db, PushSuscripcion)
    db.refresh(existente)
    return existente


def desuscribir(db: Session, usu_cod: int, endpoint: str) -> None:
    """Desactiva (no borra) una suscripción del usuario actual."""
    suscripcion = db.scalars(
        select(PushSuscripcion).where(
            and_(
                PushSuscripcion.psu_endpoint == endpoint,
                PushSuscripcion.usu_cod == usu_cod,
            )
        )
    ).first()
    if suscripcion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suscripción no encontrada para este usuario.",
        )
    suscripcion.psu_activa = False
    crud.guardar(db, PushSuscripcion)


def suscripciones_activas(db: Session) -> list[PushSuscripcion]:
    """Todas las suscripciones activas (para el envío masivo desde Node)."""
    return list(
        db.scalars(
            select(PushSuscripcion).where(PushSuscripcion.psu_activa == True)  # noqa: E712
        ).all()
    )


def marcar_uso(db: Session, psu_cod: int) -> None:
    """Actualiza ``fec_ultimo_uso`` tras un envío exitoso."""
    suscripcion = crud.obtener(db, PushSuscripcion, "psu_cod", psu_cod)
    if suscripcion is None:
        return
    suscripcion.fec_ultimo_uso = utc_now()
    db.commit()


# =====================================================================
# HELPERS INTERNOS
# =====================================================================


def _visible_para(usu_cod: int):
    """Predicado SQL: notificaciones globales + las dirigidas al usuario."""
    return or_(
        Notificacion.not_usu_dest.is_(None),  # IS NULL → válido en SQL Server
        Notificacion.not_usu_dest == usu_cod,
    )