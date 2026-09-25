"""Pruebas del monitor de deriva (Etapa 2).

Usa un Detector y un buffer falsos: la referencia (baseline) se inyecta a
mano para no depender del pkl de entrenamiento.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.services import drift
from app.services.drift import evaluar_drift


# ---------------------------------------------------------------------------
# Dobles de prueba
# ---------------------------------------------------------------------------

class BufferFake:
    def __init__(self, por_nodo: dict[str, list[dict]]):
        self._datos = por_nodo

    def nodos(self) -> list[str]:
        return list(self._datos)

    def serie(self, nodo, n=None):
        serie = list(self._datos.get(nodo, []))
        return serie[-n:] if n else serie


class DetectorFake:
    """Expones la API que usa el drift (igual que Detector real)."""

    def __init__(self, features, clean=True, alert=False, hist_alertar=None):
        self._features_modelo = list(features)
        self._posiciones = {v: i for i, v in enumerate(features)}
        self._scaler = None
        self._alert = alert
        self._hist_alertar = (
            list(hist_alertar)
            if hist_alertar is not None
            else [False] * drift.VENTANAS_LIMPIEZA
        )

    def _escalar(self, muestra):
        return [float(muestra.get(v, 0.0)) for v in self._features_modelo]

    def estado(self):
        zona = "CRITICA" if self._alert else "NORMAL"
        return {
            "zonas_nodo": {
                "n1": {
                    "zona": zona,
                    "alerta": self._alert,
                    "hist_alertar": self._hist_alertar,
                }
            }
        }


def muestreo(central, n, desv=1.0, seed=7) -> list[dict]:
    rng = np.random.default_rng(seed)
    z = rng.normal(central, desv, n)
    return [{"v1": float(x), "v2": float(x)} for x in z]


def baseline_normal(features, n=4000) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(123)
    b = {}
    for _v in features:
        b[_v] = rng.normal(0.0, 1.0, n)
    return b


# ---------------------------------------------------------------------------
# Casos
# ---------------------------------------------------------------------------

def test_sin_datos_suficientes_sin_veredicto():
    det = DetectorFake(["v1", "v2"])
    buf = BufferFake({"n1": muestreo(0.0, 10)})
    res = evaluar_drift(det, buf, baseline=baseline_normal(["v1", "v2"]))
    assert res["recomendacion"] == "sin_datos"


def test_estado_normal_con_distribucion_igual():
    det = DetectorFake(["v1", "v2"])
    buf = BufferFake({"n1": muestreo(0.0, drift.MIN_MUESTRAS + 120)})
    res = evaluar_drift(det, buf, baseline=baseline_normal(["v1", "v2"]))
    assert res["recomendacion"] == "normal"
    assert res["variables_drifted"] == []
    assert res["muestras_usadas"] >= drift.MIN_MUESTRAS
    assert all(not f["drift"] for f in res["variables"])


def test_deriva_detectada_primera_superada_es_observacion():
    det = DetectorFake(["v1", "v2"])
    buf = BufferFake({"n1": muestreo(4.0, drift.MIN_MUESTRAS + 20)})
    res = evaluar_drift(det, buf, baseline=baseline_normal(["v1", "v2"]))
    assert res["variables_drifted"]
    assert res["recomendacion"] == "observacion"
    assert all(f["drift"] for f in res["variables"] if f["estado"] != "sin_datos")


def test_racha_consecutiva_activa_reentrenar():
    det = DetectorFake(["v1", "v2"])
    buf = BufferFake({"n1": muestreo(4.0, drift.MIN_MUESTRAS + 20)})
    base = baseline_normal(["v1", "v2"])
    drift._historial.clear()
    for i in range(drift.RACHA_CONFIRM - 1):
        res = evaluar_drift(det, buf, baseline=base)
        assert res["recomendacion"] == "observacion"
        assert res["racha_confirmacion"] == i + 1
    res = evaluar_drift(det, buf, baseline=base)
    assert res["recomendacion"] == "reentrenar"
    assert res["racha_confirmacion"] == drift.RACHA_CONFIRM
    # Una racha rota (vuelta a normal) resetea la confirmacion.
    drift._historial.clear()
    buf2 = BufferFake({"n1": muestreo(0.0, drift.MIN_MUESTRAS + 20)})
    res2 = evaluar_drift(det, buf2, baseline=base)
    assert res2["recomendacion"] == "normal"
    assert res2["racha_confirmacion"] == 0


def test_guardia_nodo_con_alerta_no_participa():
    det = DetectorFake(["v1", "v2"], alert=True, clean=False)
    buf = BufferFake({"n1": muestreo(4.0, drift.MIN_MUESTRAS + 20)})
    res = evaluar_drift(det, buf, baseline=baseline_normal(["v1", "v2"]))
    assert res["recomendacion"] == "sin_datos"
    assert res["nodos_descartados"] == ["n1"]


def test_guarda_descarta_ventanas_recientes_con_anomalia():
    hist = [False] * (drift.VENTANAS_LIMPIEZA - 1) + [True]
    det = DetectorFake(["v1", "v2"], alert=False, hist_alertar=hist)
    buf = BufferFake({"n1": muestreo(4.0, drift.MIN_MUESTRAS + 20)})
    res = evaluar_drift(det, buf, baseline=baseline_normal(["v1", "v2"]))
    assert res["nodos_descartados"] == ["n1"]


def test_deshabilitado_devuelve_sin_analisis():
    drift.ENABLED = False
    try:
        det = DetectorFake(["v1", "v2"])
        buf = BufferFake({"n1": muestreo(4.0, 100)})
        res = evaluar_drift(det, buf, baseline=baseline_normal(["v1", "v2"]))
        assert res["recomendacion"] == "deshabilitado"
    finally:
        drift.ENABLED = True