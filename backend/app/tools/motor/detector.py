"""
detector.py
===========
Detector de anomalías en streaming (ensamble por z-scores).

Carga los artefactos entrenados (modelo_isolation_forest.joblib, scaler.joblib,
features_modelo.csv y, si están, modelo_lof.joblib / modelo_elliptic.joblib /
modelo_copod.joblib), mantiene por nodo una ventana móvil de VENTANA muestras
y puntúa cada ventana llena.

Componentes (mayor = normal):
    s_iso =  iso.decision_function(x)
    s_lof =  lof.decision_function(x)
    s_ell =  ell.decision_function(x)
    s_cop = -copod.decision_function(x)
    z     = media de z-scores de los componentes presentes
    score alto = normal, score bajo = anómalo

El ensamble se autoelige según los modelos disponibles (LOF+ELLIPTIC primero,
si no ISO+COPOD, si no ISO solo) y puede forzarse con STEELNORT_ENSEMBLE
(LOF_ELL / Z / ISO).

Con STEELNORT_ZONAL=1 (default), la decisión final pasa por el DecisorZonal
(zonas + histéresis + consenso N-de-M + anti-flap). ``es_anomalia`` es la
alerta ESTABLE; la decisión bruta por ventana queda en ``es_anomalia_cruda``.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Lock

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from app.utils import utc_now

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
except ImportError:
    pass

log = logging.getLogger("steelnort.detector")

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MOTOR_DIR = Path(__file__).resolve().parent
ML_ARTIFACTS = os.getenv(
    "ML_ARTIFACTS_DIR", str(MOTOR_DIR / "artifacts")
)
TRAIN_PKL = os.getenv(
    "ML_TRAIN_PKL",
    str(BACKEND_ROOT / "training" / "datasets" / "dataset_muestras_train.pkl"),
)
VENTANA = int(os.getenv("TELEMETRIA_VENTANA", "10"))
UMBRAL_DEFECTO = os.getenv("TELEMETRIA_UMBRAL", "q01")
ZONAL = os.getenv("STEELNORT_ZONAL", "1") == "1"

EPS = 1e-12
NOMBRES_Q = {0.10: "q10", 0.05: "q05", 0.01: "q01"}


# ==========================================
# Ensamble Z-score
# ==========================================
SIGLAS = {
    "ISOLATION_FOREST": "ISO",
    "COPOD": "COPOD",
    "LOF": "LOF",
    "ELLIPTIC": "ELL",
}


def _scores_de(nombre, modelo, X):
    """Score de un componente con la convención: mayor = normal."""
    s = np.asarray(modelo.decision_function(X), dtype="float64")
    return -s if nombre == "COPOD" else s


def _nombre_modo(componentes):
    """Nombre legible del ensamble según sus componentes."""
    nombres = [n for n, _ in componentes]
    if nombres == ["ISOLATION_FOREST", "COPOD"]:
        return "ENSEMBLE_Z"
    if nombres == ["LOF", "ELLIPTIC"]:
        return "ENSEMBLE_LOF_ELL"
    if len(nombres) == 1:
        return nombres[0]
    return "ENSEMBLE_" + "_".join(SIGLAS.get(n, n) for n in nombres)


class _Ensamble:
    """Componentes combinados por media de z-scores (mayor = normal)."""

    def __init__(self, componentes):
        # componentes: [(nombre, modelo), ...]; ISO/LOF/ELL aportan, COPOD invierte.
        self.componentes = list(componentes)
        self._stats = {}
        self._umbrales = {}

    @property
    def modo(self):
        return _nombre_modo(self.componentes)

    def _z(self, X):
        z = np.zeros(len(X), dtype="float64")
        for nombre, modelo in self.componentes:
            s = _scores_de(nombre, modelo, X)
            mu, sd = self._stats[nombre]
            z += (s - mu) / sd
        return z / len(self.componentes)

    def ajustar(self, X_train, qs=(0.10, 0.05, 0.01)):
        """Calibra estadísticas y umbrales sobre el train."""
        for nombre, modelo in self.componentes:
            s = _scores_de(nombre, modelo, X_train)
            self._stats[nombre] = (float(s.mean()), float(s.std()) + EPS)
        z = self._z(X_train)
        self._umbrales = {NOMBRES_Q[q]: float(np.quantile(z, q)) for q in qs}
        return self._umbrales

    def score(self, flat):
        """Score del ensamble de una ventana aplanada (mayor = normal)."""
        return float(self._z(flat)[0])


# ==========================================
# Utilidades internas
# ==========================================
def _instante(muestra):
    """Fecha de la muestra (ISO-8601 UTC)."""
    crudo = muestra.get("fecha_str")
    if crudo:
        try:
            return datetime.fromisoformat(str(crudo)).replace(tzinfo=None)
        except ValueError:
            pass
    return utc_now()


def _ref_mvn(X_sel, ridge=1e-6):
    """Referencia MVN + umbral empírico (cuantil 0.99) sobre el train."""
    mu = np.asarray(X_sel).mean(axis=0)
    cov = np.cov(np.asarray(X_sel), rowvar=False)
    cov = cov + ridge * np.eye(cov.shape[0])
    inv = np.linalg.pinv(cov)
    d = np.asarray(X_sel) - mu
    dists = np.einsum("ij,jk,ik->i", d, inv, d)
    return {
        "mu": mu, "cov_inv": inv, "df": float(X_sel.shape[1]),
        "chi2_99": float(np.quantile(dists, 0.99)),
    }


# ==========================================
# Detector
# ==========================================
class Detector:
    """Puntúa ventanas por nodo con ENSEMBLE_Z (+ capa zonal opcional)."""

    def __init__(
        self,
        ruta_modelo: str,
        ruta_scaler: str,
        ruta_features: str,
        ruta_train_pkl: str | None,
        ventana: int = VENTANA,
        umbral_nombre: str = UMBRAL_DEFECTO,
        ruta_modelo_copod: str | None = None,
        ruta_modelo_lof: str | None = None,
        ruta_modelo_elliptic: str | None = None,
    ) -> None:
        self._ruta_modelo = ruta_modelo
        self._ruta_scaler = ruta_scaler
        self._ruta_features = ruta_features
        self._ruta_modelo_copod = ruta_modelo_copod
        self._ruta_modelo_lof = ruta_modelo_lof
        self._ruta_modelo_elliptic = ruta_modelo_elliptic
        self.ruta_train_pkl = ruta_train_pkl
        self._ventana = max(1, ventana)
        self._umbral_nombre = umbral_nombre if umbral_nombre in ("q10", "q05", "q01") else "q01"

        self._lock = Lock()
        self._windows: dict[str, deque] = {}
        self._muestras: dict[str, deque] = {}
        self._decisores: dict[str, "DecisorZonal"] = {}

        self._modelo = None
        self._modelo_copod = None
        self._modelo_lof = None
        self._modelo_elliptic = None
        self._modo = "ISOLATION_FOREST"
        self._scaler: StandardScaler | None = None
        self._features_modelo: list[str] = []
        self._posiciones: dict[str, int] = {}
        self._umbrales: dict[str, float] = {}
        self._ens: _Ensamble | None = None
        self._zonal = ZONAL
        self._mvn_ref: dict | None = None

        self._cargar()
        self._calcular_umbrales(ruta_train_pkl)

    # ------------------------------------------------------------------
    # Carga y aritmética
    # ------------------------------------------------------------------
    def _cargar(self) -> None:
        if not os.path.exists(self._ruta_modelo):
            raise FileNotFoundError(f"No existe el modelo: {self._ruta_modelo}")
        self._modelo = joblib.load(self._ruta_modelo)

        if not os.path.exists(self._ruta_scaler):
            raise FileNotFoundError(f"No existe el scaler: {self._ruta_scaler}")
        self._scaler = joblib.load(self._ruta_scaler)

        # Componentes opcionales: sin ellos, el detector puntúa solo con ISO.
        self._modelo_copod = self._cargar_opcional(
            self._ruta_modelo_copod, "pyod no disponible: COPOD omitido")
        self._modelo_lof = self._cargar_opcional(self._ruta_modelo_lof)
        self._modelo_elliptic = self._cargar_opcional(self._ruta_modelo_elliptic)

        self._ens = _Ensamble(
            self._elegir_componentes(os.getenv("STEELNORT_ENSEMBLE", "")))
        self._modo = self._ens.modo

        # Orden de features del modelo (columna del CSV)
        df_feats = pd.read_csv(self._ruta_features)
        self._features_modelo = df_feats.iloc[:, 0].astype(str).str.strip().tolist()

        # Posiciones 1:1 si el scaler cubre las mismas columnas que features_modelo
        mean_len = len(self._scaler.mean_) if hasattr(self._scaler, "mean_") else 0
        if mean_len == len(self._features_modelo):
            self._posiciones = {f: i for i, f in enumerate(self._features_modelo)}
        # Si no coincide, _calcular_umbrales() resuelve las posiciones con el pkl.

    def _cargar_opcional(self, ruta: str | None, aviso: str | None = None):
        """Carga un modelo opcional; devuelve None si falta o no es importable."""
        if not (ruta and os.path.exists(ruta)):
            return None
        try:
            return joblib.load(ruta)
        except ImportError:
            if aviso:
                log.warning(aviso)
            return None

    def _elegir_componentes(self, preferencia: str):
        """Componentes del ensamble.

        ``preferencia`` (env STEELNORT_ENSEMBLE) fuerza uno concreto; por
        defecto se autoelige: LOF+ELLIPTIC > LOF > ISO+COPOD > ISO.
        """
        disp = {}
        if self._modelo is not None:
            disp["ISOLATION_FOREST"] = self._modelo
        if self._modelo_copod is not None:
            disp["COPOD"] = self._modelo_copod
        if self._modelo_lof is not None:
            disp["LOF"] = self._modelo_lof
        if self._modelo_elliptic is not None:
            disp["ELLIPTIC"] = self._modelo_elliptic

        def par(a, b):
            return [(a, disp[a]), (b, disp[b])]

        pref = (preferencia or "").strip().upper()
        if pref in ("LOF_ELL", "ENSEMBLE_LOF_ELL") and {"LOF", "ELLIPTIC"} <= disp.keys():
            return par("LOF", "ELLIPTIC")
        if pref == "LOF" and "LOF" in disp:
            return [("LOF", disp["LOF"])]
        if pref in ("Z", "ENSEMBLE_Z") and {"ISOLATION_FOREST", "COPOD"} <= disp.keys():
            return par("ISOLATION_FOREST", "COPOD")
        if pref in ("ISO", "ISOLATION_FOREST") and "ISOLATION_FOREST" in disp:
            return [("ISOLATION_FOREST", disp["ISOLATION_FOREST"])]

        # Auto: el mejor honesto primero; fallbacks mantienen lo de antes.
        if {"LOF", "ELLIPTIC"} <= disp.keys():
            return par("LOF", "ELLIPTIC")
        if "LOF" in disp:
            return [("LOF", disp["LOF"])]
        if {"ISOLATION_FOREST", "COPOD"} <= disp.keys():
            return par("ISOLATION_FOREST", "COPOD")
        if "ISOLATION_FOREST" in disp:
            return [("ISOLATION_FOREST", disp["ISOLATION_FOREST"])]
        return list(disp.items())[:1]

    def _calcular_umbrales(self, ruta_train_pkl: str | None) -> None:
        """Recalcula umbrales y referencia MVN desde el train."""
        self._umbrales = {"q10": 0.0, "q05": 0.0, "q01": 0.0}
        if not (ruta_train_pkl and os.path.exists(ruta_train_pkl)):
            log.warning("Sin pkl de entrenamiento: umbrales quedan en 0.0")
            return
        try:
            train = joblib.load(ruta_train_pkl)
            features_full: list[str] = train["features"]
            self._posiciones = {n: i for i, n in enumerate(features_full)}

            X = np.asarray(train["X"], dtype="float64")   # [n, VENTANA, 22] ya escalado
            n, v, f = X.shape
            indice = [self._posiciones[n] for n in self._features_modelo
                      if n in self._posiciones]
            if not indice:
                indice = list(range(f))

            X_sel = X[:, :, indice].reshape(n, -1)
            self._umbrales = self._ens.ajustar(X_sel)
            self._mvn_ref = _ref_mvn(X_sel)
            log.info("Modo detector: %s | Umbrales: %s", self._modo, self._umbrales)
        except Exception as exc:
            log.exception("No se pudieron calcular umbrales de train: %s", exc)

    def _escalar(self, valores: dict) -> list[float]:
        """Escala las variables del modelo en el orden de features_modelo."""
        out = []
        for nombre in self._features_modelo:
            pos = self._posiciones.get(nombre, -1)
            v = float(valores.get(nombre, 0.0) or 0.0)
            if pos < 0 or self._scaler is None or not hasattr(self._scaler, "mean_"):
                out.append(v)
                continue
            mean = float(self._scaler.mean_[pos])
            scale = float(self._scaler.scale_[pos]) or 1.0
            out.append((v - mean) / scale)
        return out

    def _score_ensamble(self, flat: np.ndarray) -> float:
        """Score ENSEMBLE_Z (mayor = normal)."""
        return self._ens.score(flat)

    # ------------------------------------------------------------------
    # Capa zonal
    # ------------------------------------------------------------------
    def _decisor_para(self, nodo: str) -> "DecisorZonal | None":
        if not self._zonal:
            return None
        with self._lock:
            d = self._decisores.get(nodo)
            if d is None:
                from app.tools.motor.decisor import DecisorZonal
                d = DecisorZonal(
                    q10=self._umbrales.get("q10", 0.0),
                    q05=self._umbrales.get("q05", 0.0),
                    q01=self._umbrales.get("q01", 0.0),
                    mvn=self._mvn_ref,
                )
                self._decisores[nodo] = d
            return d

    def _ampliar_con_zona(self, resultado: dict, nodo: str,
                          score: float, flat: np.ndarray) -> dict:
        """Enriquece la predicción con la decisión zonal."""
        raw = resultado["es_anomalia"]
        if not self._zonal:
            return resultado
        paso = self._decisor_para(nodo)
        if paso is None:
            return resultado
        info = paso.alimentar(score, flat)
        resultado["zona"] = info["zona"]
        resultado["es_anomalia"] = info["es_anomalia"]
        resultado["es_anomalia_cruda"] = raw
        resultado["alerta_activa"] = info["alerta_activa"]
        resultado["alerta_nueva"] = info["alerta_nueva"]
        resultado["racha_critica"] = info["racha_critica"]
        resultado["cooldown"] = info["cooldown"]
        resultado["regla"] = info["regla"]
        resultado["umbral_entrada"] = info["umbral_entrada"]
        resultado["umbral_salida"] = info["umbral_salida"]
        resultado["mvn_dist"] = info["mvn_dist"]
        resultado["mvn_coherente"] = info["mvn_coherente"]
        return resultado

    # ------------------------------------------------------------------
    # Propiedades
    # ------------------------------------------------------------------
    @property
    def umbrales(self) -> dict[str, float]:
        return dict(self._umbrales)

    @property
    def umbral_actual(self) -> float:
        return self._umbrales.get(self._umbral_nombre, 0.0)

    @property
    def modo(self) -> str:
        return self._modo

    @property
    def features(self) -> list[str]:
        return list(self._features_modelo)

    @property
    def ventana(self) -> int:
        return self._ventana

    @property
    def umbral_nombre(self) -> str:
        return self._umbral_nombre

    def estado(self) -> dict:
        with self._lock:
            zonas = {n: d.estado() for n, d in self._decisores.items()}
            return {
                "ventana": self._ventana,
                "modo": self._modo,
                "zonal": self._zonal,
                "mvn_ref": self._mvn_ref is not None,
                "features": list(self._features_modelo),
                "umbral_nombre": self._umbral_nombre,
                "umbrales": self._umbrales,
                "umbral_actual": self.umbral_actual,
                "ventanas_llenas": {
                    n: len(c) >= self._ventana for n, c in self._windows.items()
                },
                "zonas_nodo": zonas,
            }

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def evaluar(self, nodo: str, muestra: dict) -> dict | None:
        """Puntúa una muestra para el nodo.

        Devuelve None hasta juntar VENTANA muestras; luego la predicción
        con score, ventana temporal (prd_ini/prd_fin) y las muestras crudas.
        """
        vector = self._escalar(muestra)
        with self._lock:
            cola = self._windows.setdefault(nodo, deque(maxlen=self._ventana))
            cola.append(vector)
            crudas = self._muestras.setdefault(nodo, deque(maxlen=self._ventana))
            crudas.append((_instante(muestra), dict(muestra)))
            if len(cola) < self._ventana:
                return None
            flat = np.asarray(list(cola), dtype="float64").reshape(1, -1)
            ventana = list(crudas)

        score = self._score_ensamble(flat)
        umbral = self.umbral_actual
        resultado = {
            "es_anomalia": score < umbral,
            "score": round(score, 4),
            "umbral": round(umbral, 4),
            "prd_ini": ventana[0][0],
            "prd_fin": ventana[-1][0],
            "muestras": ventana,
            "features": {n: float(muestra.get(n, 0.0) or 0.0)
                         for n in self._features_modelo},
        }
        return self._ampliar_con_zona(resultado, nodo, score, flat[0])

    def evaluar_lote(self, nodo: str, muestras: list[dict]) -> list[dict]:
        """Puntúa una secuencia SIN tocar la ventana en vivo.

        Útil para importar cargas externas. Devuelve predicciones a partir
        de que la ventana local se llena (con el índice original).
        """
        if not muestras:
            return []
        cola = deque(maxlen=self._ventana)
        resultados = []
        for idx, muestra in enumerate(muestras):
            cola.append(self._escalar(muestra))
            if len(cola) < self._ventana:
                continue
            flat = np.asarray(list(cola), dtype="float64").reshape(1, -1)
            score = self._score_ensamble(flat)
            umbral = self.umbral_actual
            resultado = {
                "indice": idx,
                "es_anomalia": score < umbral,
                "score": round(score, 4),
                "umbral": round(umbral, 4),
                "features": {n: float(muestra.get(n, 0.0) or 0.0)
                             for n in self._features_modelo},
            }
            resultados.append(
                self._ampliar_con_zona(resultado, nodo, score, flat[0])
            )
        return resultados


# Instancia única a nivel de aplicación.
_detector = None


def get_detector() -> Detector:
    global _detector
    if _detector is None:
        _detector = Detector(
            ruta_modelo=os.path.join(ML_ARTIFACTS, "modelo_isolation_forest.joblib"),
            ruta_modelo_copod=os.path.join(ML_ARTIFACTS, "modelo_copod.joblib"),
            ruta_modelo_lof=os.path.join(ML_ARTIFACTS, "modelo_lof.joblib"),
            ruta_modelo_elliptic=os.path.join(ML_ARTIFACTS, "modelo_elliptic.joblib"),
            ruta_scaler=os.path.join(ML_ARTIFACTS, "scaler.joblib"),
            ruta_features=os.path.join(ML_ARTIFACTS, "features_modelo.csv"),
            ruta_train_pkl=TRAIN_PKL if os.path.exists(TRAIN_PKL) else None,
        )
    return _detector