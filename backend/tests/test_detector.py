"""Pruebas del detector de producción (solo carga de artefactos, sin base de datos).

El detector se apunta al bundle real de ``produccion/`` desde ``conftest.py``.
Si los artefactos faltan, obtendremos un error de carga — justamente lo que
estas pruebas deben delatar.
"""

import math

from app.tools.motor.detector import get_detector


def _muestras(det, valor_fn):
    """Construye ``ventana + 2`` muestras sintéticas con las features del modelo."""
    filas = []
    for _ in range(det.ventana + 2):
        muestra = {n: float(valor_fn(n)) for n in det._features_modelo}
        muestra["fecha_str"] = "2026-01-01 00:00:00"
        filas.append(muestra)
    return filas


def test_detector_carga_desde_produccion():
    det = get_detector()
    assert det is not None
    assert det.ventana == 10
    assert det.umbrales, "el detector debe exponer umbrales calibrados"


def test_umbrales_ordenados():
    det = get_detector()
    u = det.umbrales
    assert u["q10"] > u["q05"] > u["q01"], u


def test_evaluar_lote_una_salida_por_desplazamiento():
    det = get_detector()
    muestras = _muestras(det, lambda n: det._scaler.mean_[det._posiciones[n]])
    salidas = det.evaluar_lote("test_run", muestras)
    assert len(salidas) == len(muestras) - det.ventana + 1
    for salida in salidas:
        assert isinstance(salida["es_anomalia"], bool)
        assert math.isfinite(float(salida["score"]))


def test_ventana_extrema_se_marca_anomala():
    det = get_detector()

    def muy_bajo(nombre):
        pos = det._posiciones[nombre]
        escala = float(det._scaler.scale_[pos]) or 1.0
        return float(det._scaler.mean_[pos]) - 20.0 * escala

    salidas = det.evaluar_lote("test_run_extremo", _muestras(det, muy_bajo))
    assert any(s["es_anomalia"] for s in salidas), (
        "una ventana a 20 desviaciones por debajo de la media debe marcarse"
    )
