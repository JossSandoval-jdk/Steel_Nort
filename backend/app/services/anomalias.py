"""Persistencia de anomalias detectadas por el modelo.

Regla SteelNort: la telemetria cruda NO se guarda. Solo cuando el
detector marca una ventana como anomalia se persiste:
  - Predicciones_ML (la prediccion puntual),
  - Alertas (una alerta nueva por nodo mientras no se resuelva),
  - Heatmap_Anomalias (conteo por dia/hora para el mapa).

Ademas se registra en ``logs/telemetria_api.log`` (logging) la anomalia
para trazabilidad sin tocar la BD.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.model_alerta import Alertas, HeatmapAnomalias
from app.models.model_ml import ModelosML, PrediccionesML
from app.services.nodos import obtener_o_crear_nodo
from app.utils import utc_now

log = logging.getLogger("steelnort.anomalias")


def _registrar_modelo_desplegado(db: Session) -> ModelosML:
    """Registra en Modelos_ML el detector que esta cargado/desplegado.

    Bootstrap para la primera ejecucion: el detector arranca desde los
    artefactos (joblib) aunque la BD no tenga todavia un mirror registrado.
    Así, Predicciones_ML siempre tiene un ``prd_mdl`` valido.
    """
    import json

    from app.ml.detector import get_detector

    det = get_detector()
    ts = utc_now().strftime("%Y%m%d_%H%M%S")
    modelo = ModelosML(
        mdl_nom=f"isolation_forest_{ts}",
        mdl_tipo="isolation_forest",
        mdl_umbral_pct=Decimal("85.00"),
        mdl_vars=",".join(det._features21),
        mdl_hparms=json.dumps({
            "contamination": "auto",
            "random_state": 42,
            "fuente": "autoregistro_arranque",
            "umbrales": det.umbrales,
        }),
        mdl_ruta_art=str(det._ruta_modelo),
        mdl_act=True,
        mdl_fec_entr=utc_now(),
        reg_usu="sistema",
    )
    db.add(modelo)
    db.flush()
    log.info("Modelo activo auto-registrado: %s", modelo.mdl_nom)
    return modelo


def obtener_modelo_activo(db: Session) -> ModelosML | None:
    """Devuelve el modelo activo o lo auto-registra si la BD esta vacia."""
    modelo = (
        db.query(ModelosML)
        .filter(ModelosML.mdl_act == True, ModelosML.fec_eli.is_(None))
        .order_by(ModelosML.mdl_cod.desc())
        .first()
    )
    if modelo is None:
        modelo = _registrar_modelo_desplegado(db)
    return modelo


def persistir_prediccion(
    db: Session,
    nodo_nombre: str,
    nodo_ip: str,
    fec: datetime,
    prediccion: dict,
    origen: str = "telemetria",
) -> dict | None:
    """Persiste una prediccion ANOMALA en la sesion ya abierta ``db``.

    Crea (o reusa) el nodo, registra Predicciones_ML, mantiene UNA alerta
    abierta por nodo y actualiza el HeatmapAnomalias para el dia/hora de
    ``fec``. Devuelve el resumen de lo persistido o ``None`` si no aplica.

    Usado por la telemetria en vivo y por la importacion de cargas.
    """
    if not prediccion.get("es_anomalia"):
        return None

    modelo = obtener_modelo_activo(db)
    if modelo is None:
        log.warning("No hay Modelos_ML activo; no se persiste anomalia")
        return None
    ndo_cod = obtener_o_crear_nodo(db, nodo_nombre, nodo_ip, origen=origen)
    if ndo_cod is None:
        return None

    pred = PrediccionesML(
        prd_mdl=modelo.mdl_cod,
        prd_ndo=ndo_cod,
        prd_fec=fec,
        prd_es_anom=True,
        prd_score=Decimal(str(prediccion["score"])),
        prd_umbral=Decimal(str(prediccion["umbral"])),
        prd_feats=str(prediccion.get("features", {})),
        prd_expl="Ventana de muestras por debajo del umbral q del baseline normal.",
        reg_usu=origen,
    )
    db.add(pred)
    db.flush()  # para tener prd_cod

    # Alerta abierta por nodo mientras no se resuelva.
    alerta_abierta = (
        db.query(Alertas)
        .filter(
            Alertas.alt_ndo == ndo_cod,
            Alertas.alt_resu == False,
            Alertas.fec_eli.is_(None),
        )
        .first()
    )
    if alerta_abierta is None:
        alerta = Alertas(
            alt_ndo=ndo_cod,
            alt_prd=pred.prd_cod,
            alt_tipo="anomalia_ml",
            alt_sev="alta",
            alt_titulo=f"Anomalia detectada en {nodo_nombre}",
            alt_diag="Score por debajo del umbral de detection (ventana del detector).",
            reg_usu=origen,
        )
        db.add(alerta)
        db.flush()
    else:
        alerta = alerta_abierta

    # Heatmap por dia/hora del timestamp de la prediccion.
    now_utc = fec if fec.tzinfo else fec.replace(tzinfo=timezone.utc)
    heat = (
        db.query(HeatmapAnomalias)
        .filter(
            HeatmapAnomalias.hma_fec == now_utc.date(),
            HeatmapAnomalias.hma_hora == now_utc.hour,
            HeatmapAnomalias.hma_sev == "alerta_alta",
        )
        .first()
    )
    if heat is None:
        heat = HeatmapAnomalias(
            hma_fec=now_utc.date(),
            hma_hora=now_utc.hour,
            hma_sev="alerta_alta",
            hma_cant=1,
            reg_usu=origen,
        )
        db.add(heat)
    else:
        heat.hma_cant += 1

    log.info(
        "Anomalia persistida: nodo=%s score=%s umbral=%s",
        nodo_nombre, prediccion["score"], prediccion["umbral"],
    )
    return {
        "nodo": nodo_nombre,
        "prediccion": pred.prd_cod,
        "alerta": alerta.alt_cod if alerta is not None else None,
    }


def persistir_anomalia(
    nodo_nombre: str,
    nodo_ip: str,
    prediccion: dict,
) -> dict | None:
    """Guarda la anomalia detectada y devuelve la alerta creada (o None).

    Solo se llama cuando ``prediccion["es_anomalia"]`` es True. Abre su
    propia sesion (telemetria en vivo).
    """
    if not prediccion.get("es_anomalia"):
        return None

    db = SessionLocal()
    try:
        resultado = persistir_prediccion(
            db, nodo_nombre, nodo_ip, utc_now(), prediccion, origen="telemetria"
        )
        db.commit()
        return resultado
    except Exception:
        db.rollback()
        log.exception("Error al persistir anomalia")
        return None
    finally:
        db.close()