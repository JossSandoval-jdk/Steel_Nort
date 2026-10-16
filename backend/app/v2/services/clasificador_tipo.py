"""Capa de apoyo al diagnostico: clasificador supervisado del tipo de fallo.

ADITIVO. Carga ``clasificador_tipo.joblib`` del directorio de artefactos (si
existe) y estima el tipo de fallo mas probable a partir de la ventana cruda que
el detector ya devuelve en ``pred["muestras"]``.

Entrenamiento y validacion honesta (leave-one-run-out):
    top-1 = 66.5 % | top-2 = 96.1 % | top-3 = 98.1 %
    (ver modelado/indicadores/08_entrenar_clasificador_tipo.py)

Si el artefacto no existe, todas las funciones devuelven None/"" y el sistema
funciona exactamente igual que antes.
"""

from __future__ import annotations

import logging
import os

import joblib
import numpy as np

from app.tools.motor.detector import ML_ARTIFACTS

log = logging.getLogger("steelnort.v2.tipo")

RUTA_ARTEFACTO = os.path.join(ML_ARTIFACTS, "clasificador_tipo.joblib")

_paquete = None
_intentado = False


def _cargar():
    """Carga perezosa del artefacto. Devuelve None si no existe o falla."""
    global _paquete, _intentado
    if _intentado:
        return _paquete
    _intentado = True
    if not os.path.exists(RUTA_ARTEFACTO):
        log.info("Sin clasificador de tipo (%s); se omite.", RUTA_ARTEFACTO)
        return None
    try:
        _paquete = joblib.load(RUTA_ARTEFACTO)
        log.info("Clasificador de tipo cargado: %s clases.",
                 len(_paquete.get("clases", [])))
    except Exception as exc:                       # noqa: BLE001
        log.warning("No se pudo cargar el clasificador de tipo: %s", exc)
        _paquete = None
    return _paquete


def disponible() -> bool:
    """True si el artefacto del clasificador esta cargado."""
    return _cargar() is not None


def predecir(pred: dict) -> dict | None:
    """Tipo de fallo probable para la ventana de ``pred``.

    Devuelve ``{"tipo", "etiqueta", "top2", "prob", "prob_top2"}`` o None si no
    hay artefacto o la ventana no esta completa.
    """
    paquete = _cargar()
    if not paquete:
        return None
    muestras = pred.get("muestras") or []
    ventana = int(paquete.get("ventana", 10))
    if len(muestras) < ventana:
        return None
    features = paquete["features"]
    filas = [[float(m.get(n, 0.0) or 0.0) for n in features]
             for _, m in muestras[-ventana:]]
    matriz = np.asarray(filas, dtype="float64")
    vector = np.concatenate([matriz.mean(axis=0), matriz.std(axis=0)])
    modelo = paquete["modelo"]
    proba = modelo.predict_proba(vector.reshape(1, -1))[0]
    clases = list(modelo.classes_)
    orden = np.argsort(-proba)
    etiquetas = paquete.get("etiquetas", {})
    top2 = [clases[i] for i in orden[:2]]
    return {
        "tipo": clases[orden[0]],
        "etiqueta": etiquetas.get(clases[orden[0]], clases[orden[0]]),
        "top2": top2,
        "top2_etiquetas": [etiquetas.get(c, c) for c in top2],
        "prob": round(float(proba[orden[0]]), 4),
        "prob_top2": round(float(proba[orden[0]] + proba[orden[1]]), 4),
    }


def resumen(pred: dict) -> str:
    """Frase corta para el diagnostico de la alerta; "" si no hay clasificador."""
    info = predecir(pred)
    if not info:
        return ""
    segunda = info["top2_etiquetas"][1]
    return (f"Tipo probable (clasificador): {info['etiqueta']}. "
            f"Alternativa: {segunda}.")