"""Integracion de la capa zonal dentro del Detector de produccion.

Verifica que, con STEELNORT_ZONAL activo, una secuencia real de falla
termina en alerta estable (con zona, racha y MVN) y que los campos nuevos
estan presentes en evaluar_lote.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import joblib
import pytest

import config
from app.ml.detector import Detector


def construir_detector(zonal: bool = True) -> Detector:
    old = os.environ.get("STEELNORT_ZONAL", "1")
    try:
        os.environ["STEELNORT_ZONAL"] = "1" if zonal else "0"
        det = Detector(
            ruta_modelo=os.path.join(config.DIR_DETECCION, "modelo_isolation_forest.joblib"),
            ruta_modelo_copod=os.path.join(config.DIR_DETECCION, "modelo_copod.joblib"),
            ruta_scaler=os.path.join(config.DIR_DETECCION, "scaler.joblib"),
            ruta_features=os.path.join(config.DIR_CORRELACION, "features_modelo.csv"),
            ruta_train_pkl=os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl"),
            ventana=10, umbral_nombre="q01",
        )
        return det
    finally:
        os.environ["STEELNORT_ZONAL"] = old


def _muestras_de_ventana(muestra) -> list[dict]:
    return [
        dict(zip(muestra["features"], [float(v) for v in fila]))
        for fila in muestra["X"][0]
    ]


def test_campos_zonal_presentes_en_evaluar_lote():
    test = joblib.load(os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl"))
    det = construir_detector(zonal=True)
    res = det.evaluar_lote("z7", _muestras_de_ventana(test))
    assert res
    ultimo = res[-1]
    # una ventana de falla real: score por debajo del umbral
    assert ultimo["score"] < ultimo["umbral"]
    assert ultimo["zona"] in ("NORMAL", "WARNING_ESCALA", "CRITICA")
    assert "es_anomalia_cruda" in ultimo
    assert "racha_critica" in ultimo
    assert "mvn_coherente" in ultimo


def test_secuencia_falla_termina_en_alerta_estable():
    test = joblib.load(os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl"))
    det = construir_detector(zonal=True)
    # corriendo las primeras 27 ventanas de la corrida de falla (run '11'):
    # se alimentan de a una (mismo nodo) para acumular estado zonal
    res = []
    for k in range(27):
        paso = det.evaluar_lote("z8", _muestras_de_ventana(test))
        if paso:
            res.append(paso[-1])
    assert any(r["es_anomalia"] for r in res), \
        "la falla real debe terminar en alerta estable"
    ultima = res[-1]
    assert ultima["zona"] == "CRITICA"
    assert ultima["racha_critica"] >= 2
    # la decision cruda con la que coincidimos ante el fallo ya es anomalia
    assert ultima["es_anomalia_cruda"] is True