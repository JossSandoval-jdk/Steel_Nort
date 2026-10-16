"""Middleware de AUDITORIA: deja registro de las acciones que cambian datos.

Cada peticion de escritura (POST, PUT, PATCH, DELETE) sobre ``/api/v2`` escribe
una fila en ``dbo.auditoria`` con:

    aud_usu        el ``usu_cod`` del token, o NULL si no vino un token valido;
    aud_accion     el metodo HTTP (es lo que distingue crear de editar o borrar);
    aud_recurso    la ruta pedida (que recurso se toco);
    aud_resultado  el codigo HTTP de la respuesta (200, 403, 409...);
    aud_ip         la IP del cliente;
    aud_fec        la fecha y hora (UTC).

Asi se puede responder "¿quien cambio este umbral y cuando?" sin tocar cada
servicio: el registro es transversal. Se guarda DESPUES de responder, para no
retrasar la peticion, y en un hilo aparte (``run_in_threadpool``) porque la
sesion de SQLAlchemy es sincrona.

Se registran las escrituras (POST/PUT/PATCH/DELETE) y, ademas, los accesos
denegados (respuesta 403), para dejar constancia de quien intento algo que no
le correspondia.
"""

from __future__ import annotations

import logging

from starlette.concurrency import run_in_threadpool

from app.security import decode_access_token
from app.v2.database import SessionLocal
from app.v2.models.sistema import Auditoria

log = logging.getLogger("steelnort.v2.auditoria")

# Los metodos que cambian datos. GET/HEAD/OPTIONS no se auditan.
METODOS_ESCRITURA = {"POST", "PUT", "PATCH", "DELETE"}

# El login se registra aparte (con accion semantica y el usuario ya validado):
# el token no viaja en la propia peticion de login, asi que el middleware no
# podria saber quien entro. Lo hace el router de auth con ``auditoria.registrar``.
RUTAS_EXPLICITAS = {"/api/v2/auth/login"}


def _usuario_del_token(cabecera: str | None) -> int | None:
    """Saca el ``usu_cod`` del JWT, o ``None`` si falta o no es valido."""
    if not cabecera or not cabecera.lower().startswith("bearer "):
        return None
    contenido = decode_access_token(cabecera[7:].strip())
    if not contenido:
        return None
    try:
        return int(contenido.get("sub"))
    except (TypeError, ValueError):
        return None


def _guardar(usuario: int | None, accion: str, recurso: str, resultado: int, ip: str | None) -> None:
    """Inserta la fila de auditoria. Nunca deja caer la peticion si falla."""
    try:
        with SessionLocal() as db:
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
    except Exception as exc:  # el registro no debe romper la operacion real
        log.warning("No se pudo registrar la auditoria: %s", exc)


async def auditar_peticion(request, call_next):
    """Middleware HTTP: audita la escritura (y los accesos denegados) despues de responder."""
    respuesta = await call_next(request)

    # Se registra toda escritura y, ademas, todo acceso denegado (403), para
    # poder ver quien intento algo que no le correspondia.
    es_escritura = request.method in METODOS_ESCRITURA
    denegado = respuesta.status_code == 403

    if (
        (es_escritura or denegado)
        and request.url.path.startswith("/api/v2")
        and request.url.path not in RUTAS_EXPLICITAS
    ):
        usuario = _usuario_del_token(request.headers.get("authorization"))
        ip = request.client.host if request.client else None
        await run_in_threadpool(
            _guardar, usuario, request.method, request.url.path, respuesta.status_code, ip
        )

    return respuesta
