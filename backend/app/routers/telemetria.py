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
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.model_muestra_normal import MuestrasNormales
from app.routers.auth import get_current_user
from app.services.anomalias import persistir_anomalia
from app.services.importacion import importar_csv, importar_muestras
from app.services.telemetria import buffer_telemetria
from app.ml.detector import get_detector

router = APIRouter(prefix="/telemetria", tags=["telemetria"])

# Dependencia de autenticacion tipada.
UsuarioActual = Annotated[object, Depends(get_current_user)]

log = logging.getLogger("steelnort.telemetria")

# Margen de espera del SSE entre envios (para no saturar hilos).
SSE_LOOP_SECONDS = 0.5

# Nodos que ya fueron "vistos" en este arranque (para no repetir el
# log de conexion en cada muestra).
_nodos_vistos: set[str] = set()


class MuestraPayload(BaseModel):
    """Estructura de una muestra enviada por el daemon."""

    nodo: str = Field(..., description="Nombre del nodo que publica")
    ip: str = "0.0.0.0"
    muestra: dict[str, Any] = Field(..., description="Variables de la muestra")


class CargaImportPayload(BaseModel):
    """Carga de trabajo externa para un nodo.

    ``carga`` es una lista de muestras del estilo
    ``{"fec": "2026-09-10 12:00:00" (opcional), "variables": {...}}``.
    La separacion normal/anomalia la hace el mismo detector en lote,
    conservando los timestamps inyectados.
    """

    nodo: str = Field(..., description="Nombre del nodo SCADA destino")
    ip: str = "0.0.0.0"
    carga: list[dict[str, Any]] = Field(
        ..., description="Muestras: [{'fec'?: iso, 'variables': {...}}, ...]"
    )


def _obtener_o_crear_nodo(db: Session, nombre: str, ip: str) -> int | None:
    """Busca o auto-registra un nodo SCADA y retorna su cod."""
    from app.models.model_scada import NodosSCADA

    nodo = (
        db.query(NodosSCADA)
        .filter(NodosSCADA.ndo_nom == nombre, NodosSCADA.fec_eli.is_(None))
        .first()
    )
    if nodo is not None:
        return nodo.ndo_cod
    nodo = NodosSCADA(
        ndo_nom=nombre[:100],
        ndo_ip=ip[:45],
        ndo_tipo="servidor",
        ndo_est="operativo",
        reg_usu="telemetria",
    )
    db.add(nodo)
    db.flush()
    return nodo.ndo_cod


def _guardar_muestra_normal(
    db: Session,
    nodo_nombre: str,
    nodo_ip: str,
    prediccion: dict,
    ventana: dict,
) -> None:
    """Persiste la muestra NORMAL en la tabla Muestras_Normales.

    Solo se llama cuando prediccion['es_anomalia'] es False.
    Guarda las features como JSON para poder reconstruir el
    dataset de entrenamiento posteriormente.
    """
    ndo_cod = _obtener_o_crear_nodo(db, nodo_nombre, nodo_ip)
    if ndo_cod is None:
        return

    feats_json = json.dumps(
        prediccion.get("features", {}),
        default=str,
    )

    mno = MuestrasNormales(
        mno_ndo=ndo_cod,
        mno_fec=datetime.utcnow(),
        mno_score=Decimal(str(prediccion.get("score", 0))),
        mno_umbral=Decimal(str(prediccion.get("umbral", 0))),
        mno_feats=feats_json,
        mno_ventana=ventana.get("ventana", 10),
        reg_usu="telemetria",
    )
    db.add(mno)


def _nodo_registrado(db: Session, nombre: str) -> bool:
    """True si el nodo ya existe en la BD (baja logica excluida)."""
    from app.models.model_scada import NodosSCADA

    return (
        db.query(NodosSCADA)
        .filter(NodosSCADA.ndo_nom == nombre, NodosSCADA.fec_eli.is_(None))
        .first()
        is not None
    )


def _log_reconocimiento(nodo: str, ip: str, recien_alta: bool) -> None:
    """Deja en el terminal/log la validacion de conexion del servidor.

    - Primera vez en TODA la vida (nodo recien registrado): "RECONOCIDO".
    - Primera vez en este arranque (nodo ya registrado, acaba de
      conectarse): "conectado".
    El resto de muestras ya no generan este log (evita ruido).
    """
    global _nodos_vistos
    if recien_alta:
        _nodos_vistos.add(nodo)
        log.info(
            "[TELEMETRIA] Servidor/Nodo RECONOCIDO por el sistema: %s (%s) ->"
            " registrado en Nodos_SCADA",
            nodo, ip,
        )
        return
    if nodo not in _nodos_vistos:
        _nodos_vistos.add(nodo)
        log.info(
            "[TELEMETRIA] Servidor/Nodo %s (%s) conectado - enviando telemetria",
            nodo, ip,
        )


def _log_prediccion(nodo: str, prediccion: dict, ventana: int) -> None:
    """Clasificacion visible en el terminal para validar el modelo."""
    marca = "ANOMALIA" if prediccion["es_anomalia"] else "NORMAL"
    log.info(
        "[TELEMETRIA] NODO=%s | %s | es_anomalia=%s | score=%.4f | umbral=%.4f | ventana=%d",
        nodo, marca, prediccion["es_anomalia"],
        prediccion["score"], prediccion["umbral"], ventana,
    )


@router.post("/muestras")
def publicar_muestra(
    _current: UsuarioActual,
    payload: MuestraPayload,
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

    buffer_telemetria.agregar(str(nodo), muestra)

    prediccion = None
    db = SessionLocal()
    primera_vez = True
    try:
        detector = get_detector()
        prediccion = detector.evaluar(str(nodo), muestra)

        # Validacion visible de la conexion servidor <-> sistema.
        primera_vez = not _nodo_registrado(db, str(nodo))
        _log_reconocimiento(str(nodo), payload.ip, primera_vez)

        if prediccion is not None:
            _log_prediccion(str(nodo), prediccion, detector._ventana)
            try:
                if prediccion["es_anomalia"]:
                    # --- ANOMALIA: persistir en Predicciones_ML + Alertas + Heatmap ---
                    persistir_anomalia(str(nodo), payload.ip, prediccion)
                else:
                    # --- NORMAL: persistir en Muestras_Normales (para reentrenar) ---
                    _guardar_muestra_normal(
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

    return {"ok": True, "recibida": len(buffer_telemetria.serie(str(nodo))),
            "prediccion": prediccion}


@router.post("/import")
def importar_carga(
    _current: UsuarioActual,
    payload: CargaImportPayload,
) -> dict:
    """Importa una carga de trabajo externa (JSON) y la separa.

    Reproduce la carga por el detector con ventanas aisladas y persiste:
      normal   -> Muestras_Normales (para reentrenar)
      anomalia -> Predicciones_ML + Alertas + Heatmap

    La primera ventana menor a 10 muestras no se evalua (se descarta del
    reporte como ``descartadas_primera_ventana``).
    """
    reporte = importar_muestras(
        nodo=payload.nodo or "desconocido",
        ip=payload.ip,
        muestras=payload.carga,
    )
    return reporte


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
        "nodos": buffer_telemetria.estados(),
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
                mutaciones = buffer_telemetria.desde_seq(seq)
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