"""Servicio que avisa al servidor Node para que envíe Web Push.

FastAPI crea la notificación en la base (el trigger TR_alertas_notifica la
inserta al abrir una alerta C/A) y luego llama aquí. Este módulo hace una
petición HTTP al endpoint interno de Node (/internal/notificar), que se
encarga de:

  1. Emitir por WebSocket a los usuarios conectados en vivo.
  2. Enviar Web Push a todos los navegadores suscritos.

La llamada es best-effort: si Node no responde, se loguea el error y se
sigue. El push es un extra, no debe tumbar la creación de la alerta.
"""

from __future__ import annotations

import logging

import httpx

from app.v2.config import settings

log = logging.getLogger("steelnort.v2.notificador")

# Timeout corto: si Node no responde en 3s, es que algo va mal.
TIMEOUT_SEGUNDOS = 3.0


def notificar_push(
    titulo: str,
    detalle: str | None,
    severidad: str,
    url: str | None = None,
    not_cod: int | None = None,
) -> bool:
    """Envía el webhook a Node. Devuelve True si llegó, False si falló.

    Es SÍNCRONA a propósito: se llama después de un commit, y el webhook
    responde en ~50 ms. No merece la pena complicarlo con async.
    """
    if not settings.internal_token:
        log.warning("[push] INTERNAL_TOKEN no configurado: no se avisa a Node.")
        return False

    payload: dict = {
        "titulo": titulo,
        "detalle": detalle or "",
        "severidad": severidad,
        "url": url or "/notificaciones",
    }
    if not_cod is not None:
        payload["not_cod"] = not_cod

    endpoint = f"{settings.node_internal_url.rstrip('/')}/internal/notificar"

    try:
        with httpx.Client(timeout=TIMEOUT_SEGUNDOS) as cliente:
            respuesta = cliente.post(
                endpoint,
                json=payload,
                headers={"X-Internal-Token": settings.internal_token},
            )
        if respuesta.status_code >= 400:
            log.warning(
                "[push] Node rechazó el webhook: %s %s",
                respuesta.status_code,
                respuesta.text[:200],
            )
            return False
        log.info(
            "[push] Notificado a Node: '%s' [%s] (not_cod=%s)",
            titulo,
            severidad,
            not_cod,
        )
        return True
    except httpx.RequestError as exc:
        log.warning("[push] No se pudo contactar con Node en %s: %s", endpoint, exc)
        return False
    except Exception as exc:
        log.warning("[push] Error inesperado llamando a Node: %s", exc)
        return False