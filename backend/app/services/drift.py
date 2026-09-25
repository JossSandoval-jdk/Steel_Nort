"""Etapa 2 (Anti-Drift): monitor de deriva de distribucion en produccion.

Compara cada N minutos la distribucion de las variables del modelo en el
ring buffer (produccion) contra el baseline de entrenamiento, por variable:

  - Kolmogorov-Smirnov a dos muestras (valores estandarizados recientes
    vs valores estandarizados del dataset de entrenamiento, reconstruidos
    en el MISMO espacio del scaler de produccion).
  - Desplazamiento (``media_z``) y dispersion (``razon_desv``) como senales
    complementarias (con muchas muestras el KS se satura).

Una variable se marca en deriva si ``p < ALPHA`` y (media desplazada
``>= MIN_SHIFT`` o desviacion inflada ``>= RATIO_DESV``). El monitor
recomienda "reentrenar" cuando el numero de variables en deriva supera
``MIN_VARS`` durante ``RACHA_CONFIRM`` revisiones consecutivas (histeresis:
una sola superada no dispara nada). NUNCA reentrena solo.

Reguarda Anti-FP: solo se usan datos de nodos en operacion NORMAL sin
anomalias superpuestas (se descartan nodos en CRITICA/alerta reciente),
para que la deriva no se contamine con las anomalias que se estan
analizando.

El estado en vivo se expone via ``GET /drift/estado`` y se puede forzar
una revision con ``POST /drift/revisar``.

Variables de entorno:

  STEELNORT_DRIFT_ENABLED      "1" | "0"              (default 1)
  STEELNORT_DRIFT_MINUTOS      intervalo en minutos    (default 5)
  STEELNORT_DRIFT_ALPHA        p de KS                (default 0.01)
  STEELNORT_DRIFT_MIN_SHIFT    |media_z| minima        (default 0.25)
  STEELNORT_DRIFT_RATIO_DESV   ratio desv maximo       (default 1.5)
  STEELNORT_DRIFT_MIN_VARS     variables minimas       (default 25% de 17)
  STEELNORT_DRIFT_RACHA        revisiones consecutivas (default 2)
  STEELNORT_DRIFT_MIN_MUESTRAS muestras vivas por var  (default 30)
"""

from __future__ import annotations

import logging
import os
from collections import deque
from datetime import datetime, timezone

import joblib
import numpy as np
from scipy.stats import ks_2samp

from app.services.monitor import MonitorPeriodico
from app.services.telemetria import buffer_telemetria

log = logging.getLogger("steelnort.drift")

ENABLED = os.getenv("STEELNORT_DRIFT_ENABLED", "1") == "1"
INTERVALO_MIN = float(os.getenv("STEELNORT_DRIFT_MINUTOS", "5"))
ALPHA = float(os.getenv("STEELNORT_DRIFT_ALPHA", "0.01"))
MIN_SHIFT = float(os.getenv("STEELNORT_DRIFT_MIN_SHIFT", "0.25"))
RATIO_DESV = float(os.getenv("STEELNORT_DRIFT_RATIO_DESV", "1.5"))
RACHA_CONFIRM = int(os.getenv("STEELNORT_DRIFT_RACHA", "2"))
MIN_MUESTRAS = int(os.getenv("STEELNORT_DRIFT_MIN_MUESTRAS", "30"))
# Proporcion de variables que deben derivar para sugerir reentrenar.
MIN_VARS_PCT = float(os.getenv("STEELNORT_DRIFT_MIN_VARS_PCT", "0.25"))
MAX_MUESTRAS_NODO = 200         # ventana de samples vivos considerados por nodo
VENTANAS_LIMPIEZA = 6           # nodo limpio si no alerto en sus ult. 6 ventanas

_historial: deque[int] = deque(maxlen=max(2, RACHA_CONFIRM * 2 + 1))
_pkl_cache: tuple = (None, None)  # (ruta_pkl, dict var->z_np)


# ---------------------------------------------------------------------------
# Baseline de entrenamiento (mismo espacio del scaler de produccion)
# ---------------------------------------------------------------------------

def _baseline_z(pkl_path: str, detector) -> dict[str, np.ndarray]:
    """Reconstruye el z por variable del train con el scaler de produccion.

    El pkl guarda valores YA estandarizados con su propio scaler; se
    des-escala a bruto y se re-estandariza con el scaler de produccion
    (el mismo que usa ``detector._escalar``) para comparar peras con
    peras contra el vivo.
    """
    global _pkl_cache
    key = str(pkl_path)
    if _pkl_cache[0] == key:
        return _pkl_cache[1]

    prod_scaler = detector._scaler
    if prod_scaler is None or not hasattr(prod_scaler, "mean_"):
        log.warning("Sin scaler de produccion: deriva sin baseline")
        _pkl_cache = (key, {})
        return {}

    train = joblib.load(pkl_path)
    X = np.asarray(train["X"], dtype="float64")
    feats: list[str] = list(train["features"])
    tmean = np.asarray(train["scaler"].mean_, dtype="float64")
    tscale = np.asarray(train["scaler"].scale_, dtype="float64")
    pmean = np.asarray(prod_scaler.mean_, dtype="float64")
    pscale = np.asarray(prod_scaler.scale_, dtype="float64")

    baseline: dict[str, np.ndarray] = {}
    for nombre in detector._features_modelo:
        i22 = feats.index(nombre) if nombre in feats else -1
        ppos = detector._posiciones.get(nombre, -1)
        if i22 < 0 or ppos < 0 or ppos >= len(pmean):
            continue
        raw = (X[..., i22] * tscale[i22] + tmean[i22]).ravel()
        z = (raw - pmean[ppos]) / (pscale[ppos] or 1.0)
        baseline[nombre] = z
    _pkl_cache = (key, baseline)
    log.info("Baseline de deriva construido (%d variables, %s)", len(baseline), key)
    return baseline


# ---------------------------------------------------------------------------
# Recoleccion viva (solo nodos limpios)
# ---------------------------------------------------------------------------

def _nodo_limpio(detector, nodo: str, buffer) -> bool:
    """Un nodo es limpio si su capa zonal no reporta alerta/CRITICA reciente."""
    zonas = detector.estado().get("zonas_nodo", {})
    info = zonas.get(nodo)
    if not info:
        return False
    if info.get("alerta"):
        return False
    if info.get("zona") == "CRITICA":
        return False
    pasadas = list(info.get("hist_alertar", []))
    if any(pasadas[-VENTANAS_LIMPIEZA:]):
        return False
    return True


def _muestras_vivas(buffer, nodo: str) -> list[dict]:
    return list(buffer.serie(nodo, n=MAX_MUESTRAS_NODO))


# ---------------------------------------------------------------------------
# Revision
# ---------------------------------------------------------------------------

def evaluar_drift(detector, buffer=None, pkl_path: str | None = None,
                  baseline: dict[str, np.ndarray] | None = None) -> dict:
    """Corre una revision de deriva y devuelve el dict completo del estado.

    ``detector`` debe exponer ``_features_modelo``, ``_escalar``, ``_scaler``,
    ``_posiciones`` y ``estado()`` (API de ``app.ml.detector.Detector``).
    ``baseline`` permite inyectar la referencia en tests (fichero normal).
    """
    if not ENABLED:
        return {"habilitado": False, "recomendacion": "deshabilitado"}
    if baseline is None:
        if pkl_path is None or not os.path.exists(pkl_path):
            return {"habilitado": True, "recomendacion": "sin_datos",
                    "mensaje": f"Sin pkl de baseline: {pkl_path}"}
        baseline = _baseline_z(pkl_path, detector)

    buffer = buffer or buffer_telemetria
    vars_modelo = list(detector._features_modelo)
    nodos = buffer.nodos()
    limpios = [n for n in nodos if _nodo_limpio(detector, n, buffer)]

    vivo: dict[str, list] = {}
    total = 0
    for nodo in limpios:
        for muestra in _muestras_vivas(buffer, nodo):
            try:
                vec = detector._escalar(muestra)
            except Exception:
                continue
            total += 1
            for nombre, valor in zip(vars_modelo, vec):
                vivo.setdefault(nombre, []).append(float(valor))

    if total < MIN_MUESTRAS:
        return {
            "habilitado": True, "recomendacion": "sin_datos",
            "nodos_limpios": limpios,
            "nodos_descartados": sorted(set(nodos) - set(limpios)),
            "muestras_usadas": total,
            "min_muestras": MIN_MUESTRAS,
        }

    filas: list[dict] = []
    drifted: list[str] = []
    for nombre in vars_modelo:
        base = baseline.get(nombre)
        vals = vivo.get(nombre, [])
        if base is None or len(vals) < MIN_MUESTRAS:
            filas.append({"variable": nombre, "datos": len(vals),
                          "drift": False, "estado": "sin_datos"})
            continue
        k_stat, p_val = ks_2samp(np.asarray(vals, dtype="float64"), base)
        media = float(np.mean(vals))
        desv = float(np.std(vals))
        desv_base = float(np.std(base)) or 1.0
        razon = desv / desv_base
        shift_ok = abs(media) >= MIN_SHIFT
        desv_ok = razon >= RATIO_DESV
        es_drift = bool((p_val < ALPHA) and (shift_ok or desv_ok))
        if es_drift:
            drifted.append(nombre)
        filas.append({
            "variable": nombre, "datos": len(vals),
            "ks_stat": round(float(k_stat), 4),
            "p_valor": round(float(p_val), 6),
            "media_z": round(media, 3),
            "desv_z": round(desv, 3),
            "razon_desv": round(razon, 3),
            "drift": es_drift,
            "estado": "observado" if p_val < ALPHA else "normal",
        })

    min_vars = max(1, int(round(MIN_VARS_PCT * len(vars_modelo))))

    def _actualizar_racha(n: int) -> int:
        if n >= min_vars:
            _historial.append(1)
        else:
            _historial.clear()
        return sum(1 for x in _historial if x == 1)

    racha = _actualizar_racha(len(drifted))
    recomendacion = (
        "reentrenar" if racha >= RACHA_CONFIRM
        else ("observacion" if drifted else "normal")
    )

    return {
        "habilitado": True,
        "recomendacion": recomendacion,
        "racha_confirmacion": racha,
        "min_vars": min_vars,
        "racha_requerida": RACHA_CONFIRM,
        "nodos_limpios": limpios,
        "nodos_descartados": sorted(set(nodos) - set(limpios)),
        "muestras_usadas": total,
        "variables_drifted": drifted,
        "variables": filas,
        "revisado": datetime.now(timezone.utc).isoformat(),
        "proximo_en_seg": int(INTERVALO_MIN * 60),
    }


# ---------------------------------------------------------------------------
# Hilo periodico + API de estado (infraestructura en app/services/monitor.py)
# ---------------------------------------------------------------------------

def _base_estado() -> dict:
    return {
        "habilitado": ENABLED,
        "intervalo_min": INTERVALO_MIN,
        "alpha": ALPHA,
        "min_shift": MIN_SHIFT,
        "ratio_desv": RATIO_DESV,
        "min_vars_pct": MIN_VARS_PCT,
        "racha_requerida": RACHA_CONFIRM,
        "min_muestras": MIN_MUESTRAS,
    }


def _paso_monitor() -> dict:
    """Pasada del hilo: revisa la deriva y junta config + resultado."""
    from app.ml.detector import get_detector
    det = get_detector()
    resultado = evaluar_drift(det, buffer_telemetria, pkl_path=det.ruta_train_pkl)
    if resultado.get("recomendacion") == "reentrenar":
        log.warning(
            "DERIVA DETECTADA (%d variables): se recomienda reentrenar. %s",
            len(resultado.get("variables_drifted", [])),
            resultado.get("variables_drifted"),
        )
    documento = _base_estado()
    documento.update(resultado)
    return documento


monitor = MonitorPeriodico(
    "deriva", int(INTERVALO_MIN * 60), _paso_monitor,
    estado_inicial=lambda: {**_base_estado(), "recomendacion": "sin_revisar"},
)


def start_drift_monitor() -> None:
    """Arranca el hilo del monitor de deriva (idempotente)."""
    if not ENABLED:
        log.info("Monitor de deriva deshabilitado (STEELNORT_DRIFT_ENABLED=0)")
        return
    monitor.start()


def stop_drift_monitor() -> None:
    """Detiene el hilo del monitor de deriva."""
    monitor.stop()


def fuerza_revision() -> dict:
    """Ejecuta una revision inmediata (POST /drift/revisar)."""
    return monitor.publicar(_paso_monitor())


def estado_drift() -> dict:
    """Devuelve el ultimo estado del monitor de deriva."""
    return monitor.estado()