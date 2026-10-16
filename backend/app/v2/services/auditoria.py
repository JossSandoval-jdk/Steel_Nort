"""Servicio de AUDITORIA: consultar el registro que escribe el middleware.

Solo lectura: las filas las crea ``app/v2/auditoria.py`` a medida que llegan
las peticiones. Aqui unicamente se listan, con filtros por usuario, accion y
recurso, para la pantalla de Configuracion.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.v2.models.sistema import Auditoria
from app.v2.services import crud


def registrar(
    db: Session,
    usuario: int | None,
    accion: str,
    recurso: str,
    resultado: int,
    ip: str | None = None,
) -> None:
    """Inserta una fila de auditoria con accion semantica (LOGIN, LOGIN_FAIL...).

    La usa el login: necesita registrar el usuario ya validado, y el middleware
    generico no lo puede saber porque el token no viaja en esa peticion.
    """
    db.add(
        Auditoria(
            aud_usu=usuario,
            aud_accion=accion,
            aud_recurso=recurso,
            aud_resultado=resultado,
            aud_ip=ip,
        )
    )
    db.commit()


def listar(
    db: Session,
    pagina: int,
    tamano: int,
    orden: str,
    usuario: int | None = None,
    accion: str | None = None,
    recurso: str | None = None,
):
    """Listado paginado del registro; por defecto, lo mas reciente primero."""
    filtros = {}
    if usuario is not None:
        filtros["aud_usu"] = usuario
    if accion:
        filtros["aud_accion"] = accion.upper()
    if recurso:
        filtros["aud_recurso"] = recurso

    return crud.listar(
        db,
        Auditoria,
        orden or "-aud_fec",
        filtros or None,
        pagina=pagina,
        tamano=tamano,
    )
