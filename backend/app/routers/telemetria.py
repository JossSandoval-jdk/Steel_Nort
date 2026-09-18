"""Rutas de telemetria en vivo.

  POST /telemetria/muestras   -> el daemon publica una muestra (~7s).
  GET  /telemetria/live       -> SSE: feed en vivo para el dashboard.
  GET  /telemetria/estado     -> heartbeat por nodo + estado del detector.

Sin CSRF a proposito: el que publica es el daemon (maquina a maquina),
autenticado por JWT en el header Authorization. La telemetria cruda vive
solo en memoria (regla SteelNort); las anomalias se persisten aparte.

FLUJO DE DATOS (normal vs anomalia):
  1. Daemon envia muestra -> se almacena en ring buffer (in-memory).
  2. Detector evalua la ventana de 10 muestras.
  3. Si es_anomalia=True  -> se persiste en Predicciones_ML + Alertas + Heatmap.
  4. Si es_anomalia=False -> se persiste en Muestras_Normales (para reentrenar).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.database import SessionLocal
from app.ml.detector import get_detector
from app.routers.auth import get_current_user
from app.schemas.telemetria import CargaImportPayload, MuestraPayload
from app.services import telemetria as svc
from app.services.anomalias import persistir_anomalia
from app.services.importacion import importar_csv, importar_muestras
from app.services.nodos import nodo_registrado

router = APIRouter(prefix="/telemetria", tags=["telemetria"])

# Dependencia de autenticacion tipada (el router no necesita el objeto).
UsuarioActual = Annotated[object, Depends(get_current_user)]

log = logging.getLogger("steelnort.telemetria")

# Margen de espera del SSE entre envios (para no saturar hilos).
SSE_LOOP_SECONDS = 0.5


@router.post("/muestras")
def publicar_muestra(
    payload: MuestraPayload,
    _current: UsuarioActual,
) -> dict:
    """El daemon agrega una muestra de telemetria por nodo.

    Flujo:
      1. Se guarda en ring buffer (in-memory, para SSE).
      2. Se evalua con el detector (ventana de 10).
      3. Si es anomalia -> se persiste en Predicciones_ML + Alertas + Heatmap.
      4. Si NO es anomalia -> se persiste en Muestras_Normales (para reentrenar).
    """
    nodo = payload.nodo or "desconocido"
    muestra = payload.muestra

    svc.buffer_telemetria.agregar(str(nodo), muestra)

    prediccion = None
    db = SessionLocal()
    try:
        detector = get_detector()
        prediccion = detector.evaluar(str(nodo), muestra)

        # Validacion visible de la conexion servidor <-> sistema.
        primera_vez = not nodo_registrado(db, str(nodo))
        svc.log_reconocimiento(str(nodo), payload.ip, primera_vez)

        if prediccion is not None:
            svc.log_prediccion(str(nodo), prediccion, detector._ventana)
            try:
                if prediccion["es_anomalia"]:
                    # --- ANOMALIA: persistir en Predicciones_ML + Alertas + Heatmap ---
                    persistir_anomalia(str(nodo), payload.ip, prediccion)
                else:
                    # --- NORMAL: persistir en Muestras_Normales (para reentrenar) ---
                    svc.guardar_muestra_normal(
                        db, str(nodo), payload.ip, prediccion,
                        {"ventana": detector._ventana},
                    )
                    db.commit()
            except Exception:
                db.rollback()
                log.exception("Error persistiendo resultado para nodo=%s", nodo)
    except Exception:
        log.exception("Fallo el detector para nodo=%s", nodo)
    finally:
        db.close()

    return {"ok": True, "recibida": len(svc.buffer_telemetria.serie(str(nodo))),
            "prediccion": prediccion}


@router.post("/import")
def importar_carga(
    payload: CargaImportPayload,
    _current: UsuarioActual,
) -> dict:
    """Importa una carga de trabajo externa (JSON) y la separa.

    Reproduce la carga por el detector con ventanas aisladas y persiste:
      normal   -> Muestras_Normales (para reentrenar)
      anomalia -> Predicciones_ML + Alertas + Heatmap

    La primera ventana menor a 10 muestras no se evalua (se descarta del
    reporte como ``descartadas_primera_ventana``).
    """
    return importar_muestras(
        nodo=payload.nodo or "desconocido",
        ip=payload.ip,
        muestras=payload.carga,
    )


@router.post("/import/csv")
def importar_carga_csv(
    _current: UsuarioActual,
    archivo: Annotated[UploadFile, File(...)],
    nodo: str = "",
    ip: str = "0.0.0.0",
) -> dict:
    """Importa una carga de trabajo externa desde un archivo CSV.

    Columnas del CSV:
      - ``fec``/``fecha``/``timestamp`` (opcional): timestamp inyectado.
      - columnas de las variables del modelo (las demas se ignoran).
      - ``nodo`` (opcional): nodo por fila; si falta usa el parametro ``nodo``.
    """
    texto = archivo.file.read().decode("utf-8-sig", errors="replace")
    return importar_csv(
        texto=texto,
        nodo_default=nodo,
        ip=ip,
    )


@router.get("/estado")
def estado_telemetria(_current: UsuarioActual) -> dict:
    """Heartbeat: ultima muestra por nodo, corte detectado y estado ML."""
    return {
        "nodos": svc.buffer_telemetria.estados(),
        "detector": get_detector().estado(),
    }


@router.get("/sincronizacion")
def estado_sincronizacion(_current: UsuarioActual) -> dict:
    """Estado en vivo de la cadena de datos: VPS SQL + daemon -> web."""
    from app.services.sincronizacion import estado

    return {"sincronizacion": estado()}


@router.get("/live")
def live_telemetria(_current: UsuarioActual, request: Request) -> StreamingResponse:
    """SSE: emite cada mutacion nueva del buffer a partir del ultimo seq."""
    seq = 0
    header = request.headers.get("Last-Event-ID")
    if header and header.isdigit():
        seq = int(header)

    async def event_stream():
        nonlocal seq
        try:
            while True:
                if await request.is_disconnected():
                    break
                mutaciones = svc.buffer_telemetria.desde_seq(seq)
                for s, nodo, muestra in mutaciones:
                    seq = s
                    data = json.dumps(
                        {"seq": s, "nodo": nodo, "muestra": muestra},
                        default=str,
                    )
                    yield f"event: muestra\ndata: {data}\n\n"
                yield "event: ping\ndata: {}\n\n"
                await asyncio.sleep(SSE_LOOP_SECONDS)
        except asyncio.CancelledError:  # pragma: no cover
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )