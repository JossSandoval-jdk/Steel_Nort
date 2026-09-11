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
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.model_alerta import Alertas, HeatmapAnomalias
from app.models.model_ml import ModelosML, PrediccionesML

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
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
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
        mdl_fec_entr=datetime.utcnow(),
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


def _obtener_nodo(db: Session, nombre: str, ip: str) -> int | None:
    from app.models.model_scada import NodosSCADA

    nodo = (
        db.query(NodosSCADA)
        .filter(NodosSCADA.ndo_nom == nombre, NodosSCADA.fec_eli.is_(None))
        .first()
    )
    if nodo is not None:
        return nodo.ndo_cod
    # Auto-registro del nodo que publica telemetria.
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


def persistir_anomalia(
    nodo_nombre: str,
    nodo_ip: str,
    prediccion: dict,
) -> dict | None:
    """Guarda la anomalia detectada y devuelve la alerta creada (o None).

    Solo se llama cuando ``prediccion["es_anomalia"]`` es True.
    """
    if not prediccion.get("es_anomalia"):
        return None

    db = SessionLocal()
    try:
        modelo = obtener_modelo_activo(db)
        if modelo is None:
            log.warning("No hay Modelos_ML activo; no se persiste anomalia")
            return None
        ndo_cod = _obtener_nodo(db, nodo_nombre, nodo_ip)
        if ndo_cod is None:
            return None

        pred = PrediccionesML(
            prd_mdl=modelo.mdl_cod,
            prd_ndo=ndo_cod,
            prd_fec=datetime.utcnow(),
            prd_es_anom=True,
            prd_score=Decimal(str(prediccion["score"])),
            prd_umbral=Decimal(str(prediccion["umbral"])),
            prd_feats=str(prediccion.get("features", {})),
            prd_expl="Ventana de 10 muestras por debajo del umbral q del baseline normal.",
            reg_usu="telemetria",
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
                alt_diag="Score por debajo del umbral de detection (ventana 10).",
                reg_usu="telemetria",
            )
            db.add(alerta)
            db.flush()
        else:
            alerta = alerta_abierta

        # Heatmap por dia/hora (cambio de minuto -> dia/hora actuales).
        now_utc = datetime.now(timezone.utc)
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
                reg_usu="telemetria",
            )
            db.add(heat)
        else:
            heat.hma_cant += 1

        db.commit()
        log.info(
            "Anomalia persistida: nodo=%s score=%s umbral=%s",
            nodo_nombre, prediccion["score"], prediccion["umbral"],
        )
        return {
            "nodo": nodo_nombre,
            "prediccion": pred.prd_cod,
            "alerta": alerta.alt_cod if alerta is not None else None,
        }
    except Exception:
        db.rollback()
        log.exception("Error al persistir anomalia")
        return None
    finally:
        db.close()