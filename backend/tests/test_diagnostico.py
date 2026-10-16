"""Pruebas del diagnóstico: severidad, variables desviadas y regla probable."""

from app.v2.services import anomalia_v2 as diag


class _DetFalso:
    """Detector mínimo para aislar la lógica de ``_severidad``."""

    umbrales = {"q01": -3.0, "q05": -1.0}


def test_severidad_media_por_defecto():
    assert diag._severidad(_DetFalso(), score=0.5) == "M"


def test_severidad_alta_por_score_muy_bajo():
    # q01 - 3*brecha = -3 - 3*2 = -9
    assert diag._severidad(_DetFalso(), score=-10.0) == "A"


def test_severidad_alta_por_deadlock():
    eventos = [{"event_name": "xe.xml_deadlock_report"}]
    assert diag._severidad(_DetFalso(), 0.5, eventos) == "A"


def test_severidad_critica_por_error_grave():
    eventos = [{"event_name": "xe.error_reported", "severity": 25}]
    assert diag._severidad(_DetFalso(), 0.5, eventos) == "C"


def test_severidad_error_leve_no_es_critica():
    eventos = [{"event_name": "xe.error_reported", "severity": 10}]
    assert diag._severidad(_DetFalso(), 0.5, eventos) == "M"


def _features_desde_media(det, pico=None, n_sigmas=8.0):
    features = {
        n: float(det._scaler.mean_[det._posiciones[n]]) for n in det._features_modelo
    }
    if pico:
        pos = det._posiciones[pico]
        features[pico] = (
            float(det._scaler.mean_[pos])
            + n_sigmas * (float(det._scaler.scale_[pos]) or 1.0)
        )
    return features


def test_variables_desviadas_detectan_el_pico():
    from app.tools.motor.detector import get_detector

    det = get_detector()
    pred = {"features": _features_desde_media(det, pico="cpu_sys")}
    desviadas = diag._variables_desviadas(pred)
    assert desviadas, "debe reportar al menos la variable del pico"
    assert desviadas[0][0] == "cpu_sys"
    assert desviadas[0][2] is not None
    assert abs(desviadas[0][2]) >= diag.Z_MINIMO


def test_regla_probable_devuelve_tupla_etiquetada():
    from app.tools.motor.detector import get_detector

    det = get_detector()
    pred = {"features": _features_desde_media(det, pico="cpu_sys")}
    codigo, etiqueta, frase = diag._regla_probable(pred)
    assert codigo.startswith("R")
    assert etiqueta and frase
