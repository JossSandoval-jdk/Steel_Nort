"""Importacion de cargas de trabajo externas (batch).

Permite que OTRO sistema inyecte una carga de trabajo (datos normales y
anomalias mezclados) sin tocar la telemetria en vivo. La separacion la
hace el MISMO detector que corre en streaming:

  1. Las muestras se agrupan por nodo y se ordenan por timestamp.
  2. Se reproducen por el detector con ventanas LOCALES (no contamina
     el ring buffer ni las ventanas del live).
  3. CADA ventana se separa en:
       - normal   -> Muestras_Normales  (alimenta el reentrenamiento)
       - anomalia -> Predicciones_ML + Alertas + Heatmap (diagnostico)

Asi, el dato inyectado queda separado automaticamente y listo para
reentrenar con SOLO datos normales.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.ml.detector import get_detector
from app.models.model_alerta import Alertas, HeatmapAnomalias
from app.models.model_ml import ModelosML, PrediccionesML
from app.models.model_muestra_normal import MuestrasNormales
from app.models.model_scada import NodosSCADA
from app.services.anomalias import obtener_modelo_activo

log = logging.getLogger("steelnort.importacion")

NOMBRES_COLUMNA_TIEMPO = ("fec", "fecha", "timestamp", "ts", "fecha_str")


def _obtener_nodo(db: Session, nombre: str, ip: str) -> int | None:
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
        reg_usu="importacion",
    )
    db.add(nodo)
    db.flush()
    return nodo.ndo_cod


def _parsear_fecha(valor) -> datetime | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None) if valor.tzinfo else valor
    if isinstance(valor, (int, float)):
        try:
            return datetime.fromtimestamp(float(valor), tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        if texto.endswith("Z") or "+" in texto:
            return datetime.fromisoformat(texto.replace("Z", "+00:00")).replace(tzinfo=None)
        return datetime.fromisoformat(texto)
    except ValueError:
        from dateutil import parser as dt_parser
        try:
            return dt_parser.parse(texto)
        except (ValueError, TypeError):
            return None


def _extraer_fecha(muestra: dict) -> datetime | None:
    for clave in NOMBRES_COLUMNA_TIEMPO:
        if clave in muestra and muestra.get(clave) is not None:
            return _parsear_fecha(muestra.get(clave))
    return None


def _persistir_normal(db: Session, ndo_cod: int, fec: datetime, pred: dict, reg_usu: str) -> None:
    db.add(MuestrasNormales(
        mno_ndo=ndo_cod,
        mno_fec=fec,
        mno_score=Decimal(str(pred.get("score", 0))),
        mno_umbral=Decimal(str(pred.get("umbral", 0))),
        mno_feats=__import__("json").dumps(pred.get("features", {}), default=str),
        mno_ventana=10,
        reg_usu=reg_usu,
    ))


def _persistir_anomalia(db: Session, modelo: ModelosML, ndo_cod: int, fec: datetime, pred: dict, reg_usu: str) -> None:
    import json

    registro = PrediccionesML(
        prd_mdl=modelo.mdl_cod,
        prd_ndo=ndo_cod,
        prd_fec=fec,
        prd_es_anom=True,
        prd_score=Decimal(str(pred.get("score", 0))),
        prd_umbral=Decimal(str(pred.get("umbral", 0))),
        prd_feats=json.dumps(pred.get("features", {}), default=str),
        prd_expl="Ventana de 10 muestras bajo el umbral del baseline normal (importacion externa).",
        reg_usu=reg_usu,
    )
    db.add(registro)
    db.flush()

    # Una alerta abierta por nodo mientras no se resuelva.
    alerta_abierta = (
        db.query(Alertas)
        .filter(Alertas.alt_ndo == ndo_cod, Alertas.alt_resu == False, Alertas.fec_eli.is_(None))
        .first()
    )
    if alerta_abierta is None:
        db.add(Alertas(
            alt_ndo=ndo_cod,
            alt_prd=registro.prd_cod,
            alt_tipo="anomalia_ml",
            alt_sev="alta",
            alt_titulo=f"Anomalia detectada en el nodo (importacion)",
            alt_diag="Score por debajo del umbral de deteccion (ventana 10).",
            reg_usu=reg_usu,
        ))

    # Heatmap dia/hora usando el timestamp de la muestra inyectada.
    dia_hora = fec
    if dia_hora.tzinfo is None:
        dia_hora = dia_hora.replace(tzinfo=timezone.utc)
    heat = (
        db.query(HeatmapAnomalias)
        .filter(
            HeatmapAnomalias.hma_fec == dia_hora.date(),
            HeatmapAnomalias.hma_hora == dia_hora.hour,
            HeatmapAnomalias.hma_sev == "alerta_alta",
        )
        .first()
    )
    if heat is None:
        db.add(HeatmapAnomalias(
            hma_fec=dia_hora.date(),
            hma_hora=dia_hora.hour,
            hma_sev="alerta_alta",
            hma_cant=1,
            reg_usu=reg_usu,
        ))
    else:
        heat.hma_cant += 1


def importar_lote_detalle(detalle: list[dict], reg_usu: str = "importacion") -> dict:
    """Importa una lista de filas: {nodo, ip, fec, variables}.

    - Agrupa por nodo, ordena por fecha y reproduce el detector por grupo.
    - Separa normales (Muestras_Normales) de anomalias
      (Predicciones_ML + Alertas + Heatmap), conservando el timestamp.
    - Devuelve un reporte con conteos por nodo.

    ``fec`` es opcional: sin timestamp se usa la hora actual.
    """
    if not detalle:
        return {"exito": True, "total_recibidas": 0, "evaluadas": 0,
                "normales": 0, "anomalias": 0, "por_nodo": {}}

    # 1. Agrupar por nodo, conservando las variables.
    grupos: dict[str, list[dict]] = defaultdict(list)
    for fila in detalle:
        nodo = str(fila.get("nodo") or "desconocido")
        grupos[nodo].append(fila)

    detector = get_detector()
    ventana = detector._ventana

    db = SessionLocal()
    try:
        modelo = obtener_modelo_activo(db)
        if modelo is None:
            log.warning("Sin modelo activo: la importacion NO persiste nada.")
            return {"exito": False, "mensaje": "No hay un modelo activo para clasificar.",
                    "total_recibidas": len(detalle)}

        reporte = {"exito": True, "total_recibidas": len(detalle),
                   "evaluadas": 0, "normales": 0, "anomalias": 0, "por_nodo": {}}

        for nodo, filas in grupos.items():
            ip = str(filas[0].get("ip") or "0.0.0.0")
            variables = [fila.get("variables") or fila for fila in filas]
            fechas = [_extraer_fecha(fila) for fila in filas]

            # Ordenar por fecha (las sin fecha al final).
            parejas = sorted(zip(fechas, variables), key=lambda p: p[0] is None)
            variables_orden = [v for _, v in parejas]
            fechas_orden = [f for f, _ in parejas]

            predicciones = detector.evaluar_lote(nodo, variables_orden)

            ndo_cod = _obtener_nodo(db, nodo, ip)
            normales = anomalias = 0
            # Ventana incompletas: solo se evaluan a partir de la n-esima.
            descartadas = max(0, len(variables_orden) - len(predicciones))

            for pred in predicciones:
                idx = pred["indice"]
                fec = fechas_orden[idx] or datetime.utcnow()
                try:
                    if pred["es_anomalia"]:
                        _persistir_anomalia(db, modelo, ndo_cod, fec, pred, reg_usu)
                        anomalias += 1
                    else:
                        _persistir_normal(db, ndo_cod, fec, pred, reg_usu)
                        normales += 1
                except Exception:
                    db.rollback()
                    log.exception("Error persistiendo resultado (nodo=%s)", nodo)

            db.commit()

            per_nodo = {
                "ip": ip,
                "muestras": len(variables_orden),
                "evaluadas": len(predicciones),
                "descartadas_primera_ventana": descartadas,
                "normales": normales,
                "anomalias": anomalias,
            }
            reporte["por_nodo"][nodo] = per_nodo
            reporte["evaluadas"] += len(predicciones)
            reporte["normales"] += normales
            reporte["anomalias"] += anomalias

        log.info(
            "Importacion: %d muestras -> %d normales / %d anomalias",
            reporte["total_recibidas"], reporte["normales"], reporte["anomalias"],
        )
        return reporte
    except Exception:
        db.rollback()
        log.exception("Fallo la importacion en lote")
        return {"exito": False, "mensaje": "Error interno al importar.",
                "total_recibidas": len(detalle)}
    finally:
        db.close()


def importar_muestras(nodo: str, ip: str, muestras: list[dict], reg_usu: str = "importacion") -> dict:
    """Importa una carga para un nodo unico (formato JSON del API).

    ``muestras``: [{"fec" (opcional), "variables": {...}}, ...]
    """
    detalle = [
        {"nodo": nodo, "ip": ip, "fec": m.get("fec"), "variables": m.get("variables") or m}
        for m in muestras
    ]
    return importar_lote_detalle(detalle, reg_usu=reg_usu)


def importar_csv(texto: str, nodo_default: str = "", ip: str = "0.0.0.0",
                 reg_usu: str = "importacion") -> dict:
    """Importa una carga desde el texto de un CSV.

    Columnas esperadas:
      - Una columna de tiempo (fec/fecha/timestamp/ts/fecha_str), opcional.
      - Columnas de las variables del modelo (se ignora el resto).
      - Columna ``nodo`` opcional (si falta usa ``nodo_default``).
    """
    import csv
    import io

    reader = csv.DictReader(io.StringIO(texto))
    if not reader.fieldnames:
        return {"exito": False, "mensaje": "CSV vacio o sin encabezados."}

    # Columnas de las 21 variables que el detector usa.
    features = get_detector()._features21

    detalle: list[dict] = []
    for fila in reader:
        variables = {c: _coercion_valor(fila.get(c)) for c in features}
        nodo = (fila.get("nodo") or nodo_default or "desconocido").strip() or "desconocido"
        detalle.append({
            "nodo": nodo,
            "ip": ip,
            "fec": fila.get("fec") or fila.get("fecha") or fila.get("timestamp")
                   or fila.get("ts") or fila.get("fecha_str"),
            "variables": variables,
        })

    return importar_lote_detalle(detalle, reg_usu=reg_usu)


def _coercion_valor(valor):
    if valor is None or valor == "":
        return 0.0
    try:
        return float(valor)
    except (ValueError, TypeError):
        return 0.0