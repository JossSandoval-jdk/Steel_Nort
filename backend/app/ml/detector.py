"""Detector de anomalias en streaming (ensamble COPOD + IsolationForest).

Carga los artefactos entrenados (modelo_isolation_forest.joblib,
modelo_copod.joblib, scaler.joblib y features_modelo.csv) y mantiene, por
nodo, una ventana movil de ``VENTANA`` muestras de las variables del
modelo definidas en ``features_modelo.csv`` (17 variables del motor SQL
Server + apoyo).

Replica EXACTAMENTE la transformacion del entrenamiento:
  1. Se toman las variables del modelo en el orden de ``features_modelo.csv``.
  2. Se escala cada variable con el StandardScaler (que se ajusto sobre
     las variables del dataset) usando la posicion que cada nombre
     ocupa en la lista completa de features del pkl de entrenamiento.
  3. Cuando la ventana tiene 10 muestras se aplana a un vector de F * 10
     y se puntua con la decision_function de AMBOS modelos:
       s_iso  = isolation_forest.decision_function(x)      alto = normal
       s_cop  = -copod.decision_function(x)                alto = normal
  4. Se fusionan en ENSEMBLE_Z = media de los z de cada componente
     (z = (s - media_train)/desv_train). Score ALTO = normal,
     score BAJO = anomalo.

5. Con ``STEELNORT_ZONAL=1`` (default, Etapa 1 Anti-FP) la decision
       final sale de la capa zonal de app/ml/decisor.py: zonas
       NORMAL/WARNING_ESCALA/CRITICA con histeresis, consenso asimetrico
       N-de-M y anti-flap. ``es_anomalia`` pasa a ser la alerta ESTABLE
       (la decision bruta queda en ``es_anomalia_cruda``). Se suma la
       coherencia MVN de cada ventana (Mahalanobis vs train).

Los umbrales q10/q05/q01 (y las medias/desv de cada componente) se
recalculan al arranque a partir del dataset de entrenamiento (scaled)
copiado en ``training/datasets``, igual que hacia el pipeline offline.

Punto operativo validado (experimental/medir_discriminacion.py, set mixto
normal+fallo, misma condiciones): ENSEMBLE_Z @ q01 -> TPR 100 %, FPR 1.7 %,
F1 0.98. Por eso el umbral por defecto es ``q01``.

Fallback: si el artefacto COPOD no existe o pyod no esta disponible, el
detector puntua solo con IsolationForest (modo ``ISOLATION_FOREST``).
Los features faltantes en una muestra se rellenan con 0.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from pathlib import Path
from threading import Lock

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from app.ml.ensamble_z import EnsambleZ

log = logging.getLogger("steelnort.detector")

# Carpeta raiz del backend (BACKEND_ROOT) para resolver rutas relativas.
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

ML_ARTIFACTS = os.getenv(
    "ML_ARTIFACTS_DIR", str(BACKEND_ROOT / "ml" / "artifacts")
)
TRAIN_PKL = os.getenv(
    "ML_TRAIN_PKL", str(BACKEND_ROOT / "training" / "datasets" / "dataset_muestras_train.pkl")
)
VENTANA = int(os.getenv("TELEMETRIA_VENTANA", "10"))
# Punto operativo validado (medir_discriminacion.py): ENSEMBLE_Z @ q01
# -> TPR 100 %, FPR 1.7 %, F1 0.98 sobre el set mixto normal+fallo.
# q10/q05 siguen disponibles via env TELEMETRIA_UMBRAL.
UMBRAL_DEFECTO = os.getenv("TELEMETRIA_UMBRAL", "q01")  # q10 | q05 | q01
# Etapa 1 (Anti-FP): capa de decision por zonas con histeresis + persistencia
# N-de-M + anti-flap + coherencia MVN. Ver app/ml/decisor.py. Al estar
# activa, ``es_anomalia`` refleja la alerta ESTABLE; la decision bruta por
# ventana queda en ``es_anomalia_cruda``.
ZONAL = os.getenv("STEELNORT_ZONAL", "1") == "1"


def _ref_mvn(X_sel: np.ndarray, ridge: float = 1e-6) -> dict:
    """Referencia MVN del entrenamiento y umbral EMPIRICO de coherencia.

    ``X_sel`` son las ventanas aplanadas (n, F*V) ya estandarizadas. Con
    n < F*V la pseudoinversa es de rango deficiente, asi que el cuantil
    teorico (chi2) no sirve: se usa el cuantil 0.99 de las distancias de
    Mahalanobis de las propias ventanas de train (datos normales).
    """
    mu = np.asarray(X_sel).mean(axis=0)
    cov = np.cov(np.asarray(X_sel), rowvar=False)
    cov = cov + ridge * np.eye(cov.shape[0])
    inv = np.linalg.pinv(cov)
    d = np.asarray(X_sel) - mu
    dists = np.einsum("ij,jk,ik->i", d, inv, d)
    df = float(X_sel.shape[1])
    return {
        "mu": mu, "cov_inv": inv, "df": df,
        "chi2_99": float(np.quantile(dists, 0.99)),
    }


class Detector:
    """Puntua ventanas por nodo con el ensamble COPOD + IsolationForest.

    Si el artefacto COPOD no esta disponible cae a IsolationForest solo
    (modo ``ISOLATION_FOREST``).
    """

    def __init__(
        self,
        ruta_modelo: str,
        ruta_scaler: str,
        ruta_features: str,
        ruta_train_pkl: str | None,
        ventana: int = VENTANA,
        umbral_nombre: str = UMBRAL_DEFECTO,
        ruta_modelo_copod: str | None = None,
    ) -> None:
        self._ruta_modelo = ruta_modelo
        self._ruta_scaler = ruta_scaler
        self._ruta_features = ruta_features
        self._ruta_modelo_copod = ruta_modelo_copod
        self.ruta_train_pkl = ruta_train_pkl
        self._ventana = max(1, ventana)
        self._umbral_nombre = umbral_nombre if umbral_nombre in ("q10", "q05", "q01") else "q01"
        self._lock = Lock()
        self._windows: dict[str, deque] = {}
        self._modelo = None
        self._modelo_copod = None
        self._modo = "ISOLATION_FOREST"
        self._scaler: StandardScaler | None = None
        self._features_modelo: list[str] = []
        self._posiciones: dict[str, int] = {}
        self._umbrales: dict[str, float] = {}
        self._ens: EnsambleZ | None = None
        self._zonal = ZONAL
        self._mvn_ref: dict | None = None
        self._decisores: dict[str, "DecisorZonal"] = {}

        self._cargar()
        self._calcular_umbrales(ruta_train_pkl)

    # ------------------------------------------------------------------
    # Carga y aritmetica interna
    # ------------------------------------------------------------------

    def _cargar(self) -> None:
        if not os.path.exists(self._ruta_modelo):
            raise FileNotFoundError(f"No existe el modelo: {self._ruta_modelo}")
        self._modelo = joblib.load(self._ruta_modelo)
        if not os.path.exists(self._ruta_scaler):
            raise FileNotFoundError(f"No existe el scaler: {self._ruta_scaler}")
        self._scaler = joblib.load(self._ruta_scaler)

        # Componente COPOD del ensamble (opcional). Sin el, el detector
        # puntua solo con IsolationForest.
        if self._ruta_modelo_copod and os.path.exists(self._ruta_modelo_copod):
            try:
                from pyod.models.copod import COPOD
                self._modelo_copod = joblib.load(self._ruta_modelo_copod)
            except ImportError:  # pragma: no cover - defensivo
                log.warning("pyod no disponible: detector en modo ISO solo")
                self._modelo_copod = None
        self._ens = EnsambleZ(self._modelo, self._modelo_copod)
        self._modo = self._ens.modo

        df_feats = pd.read_csv(self._ruta_features)
        # La columna "columna" tiene por fila el nombre de cada feature.
        self._features_modelo = df_feats.iloc[:, 0].astype(str).str.strip().tolist()

        # Mapeo nombre -> posicion en el escalador (lista completa de 22).
        # Se deriva de la columna de nombres que el archivo de correlacion
        # usaba; si no coincide con las 22 del scaler, se asume 1:1.
        mean_len = len(self._scaler.mean_) if hasattr(self._scaler, "mean_") else 0
        if mean_len == len(self._features_modelo):
            self._posiciones = {f: i for i, f in enumerate(self._features_modelo)}
        # Si no coinciden (22 del dataset vs 17 del modelo, por la poda),
        # las posiciones las resuelve _calcular_umbrales() a partir del
        # pkl de entrenamiento.

    def _score_ensamble(self, flat: np.ndarray) -> float:
        """ENSEMBLE_Z de la ventana aplanada (mayor = normal). Ver ensamble_z."""
        return float(self._ens.score(flat))

    def _calcular_umbrales(self, ruta_train_pkl: str | None) -> None:
        """Reconstruye q10/q05/q01 desde el dataset scaled de entrenamiento.

        En modo ensamble, los umbrales y las medias/desv de cada componente
        salen de la distribucion ENSEMBLE_Z del propio train (identico a
        como se validaron en experimental/medir_discriminacion.py).
        """
        self._umbrales = {"q10": 0.0, "q05": 0.0, "q01": 0.0}
        if not (ruta_train_pkl and os.path.exists(ruta_train_pkl)):
            log.warning("Sin pkl de entrenamiento: umbrales quedan en 0.0")
            return
        try:
            train = joblib.load(ruta_train_pkl)
            features_full: list[str] = train["features"]
            self._posiciones = {
                nombre: i for i, nombre in enumerate(features_full)
            }
            X = np.asarray(train["X"], dtype="float64")  # [n, VENTANA, 22] ya escalado
            n, v, f = X.shape
            indice = []
            for nombre in self._features_modelo:
                if nombre in self._posiciones:
                    indice.append(self._posiciones[nombre])
            if not indice or indice == [-1] * len(indice):
                indice = list(range(f))
            # X[:, :, indice].reshape(n, -1) exactamente como 03_deteccion.
            X_sel = X[:, :, indice].reshape(n, -1)

            # Estadisticas y umbrales del ensamble salen del propio train
            # (identico a como se validaron en experimental/).
            self._umbrales = self._ens.ajustar(X_sel)
            # Referencia MVN (Etapa 1) en el mismo espacio de X_sel.
            self._mvn_ref = _ref_mvn(X_sel)
            log.info("Modo detector: %s | Umbrales: %s", self._modo, self._umbrales)
        except Exception as exc:  # pragma: no cover - defensivo
            log.exception("No se pudieron calcular umbrales de train: %s", exc)

    def _escalar(self, valores: dict) -> list[float]:
        """Escala las variables del modelo en el orden de features_modelo.csv."""
        out: list[float] = []
        for nombre in self._features_modelo:
            pos = self._posiciones.get(nombre, -1)
            v = float(valores.get(nombre, 0.0) or 0.0)
            if pos is None or pos < 0 or self._scaler is None or \
                    not hasattr(self._scaler, "mean_"):
                out.append(v)
                continue
            mean = float(self._scaler.mean_[pos])
            scale = float(self._scaler.scale_[pos]) or 1.0
            out.append((v - mean) / scale)
        return out

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def _decisor_para(self, nodo: str) -> "DecisorZonal | None":
        """Devuelve (creandolo) el automata zonal para el nodo."""
        if not self._zonal:
            return None
        with self._lock:
            d = self._decisores.get(nodo)
            if d is None:
                from app.ml.decisor import DecisorZonal
                d = DecisorZonal(
                    q10=self._umbrales.get("q10", 0.0),
                    q05=self._umbrales.get("q05", 0.0),
                    q01=self._umbrales.get("q01", 0.0),
                    mvn=self._mvn_ref,
                )
                self._decisores[nodo] = d
            return d

    def _ampliar_con_zona(
        self, resultado: dict, nodo: str, score: float, flat: np.ndarray,
    ) -> dict:
        """Enriquece la prediccion con la decision zonal (Etapa 1)."""
        raw = resultado["es_anomalia"]
        if self._zonal:
            paso = self._decisor_para(nodo)
            if paso is not None:
                info = paso.alimentar(score, flat)
                resultado["zona"] = info["zona"]
                resultado["es_anomalia"] = info["es_anomalia"]
                resultado["es_anomalia_cruda"] = raw
                resultado["racha_critica"] = info["racha_critica"]
                resultado["cooldown"] = info["cooldown"]
                resultado["mvn_dist"] = info["mvn_dist"]
                resultado["mvn_coherente"] = info["mvn_coherente"]
        return resultado

    @property
    def umbrales(self) -> dict[str, float]:
        return dict(self._umbrales)

    @property
    def umbral_actual(self) -> float:
        return self._umbrales.get(self._umbral_nombre, 0.0)

    def estado(self) -> dict:
        with self._lock:
            zonas = {
                nodo: d.estado()
                for nodo, d in self._decisores.items()
            }
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
                    nodo: len(cola) >= self._ventana
                    for nodo, cola in self._windows.items()
                },
                "zonas_nodo": zonas,
            }

    def evaluar(self, nodo: str, muestra: dict) -> dict | None:
        """Puntua una muestra para ``nodo``.

        Devuelve None hasta juntar las 10 muestras de la ventana; cuando
        la ventana esta llena devuelve el resultado de la prediccion:
        {es_anomalia, score, umbral, features}.
        """
        vector = self._escalar(muestra)
        with self._lock:
            cola = self._windows.setdefault(
                nodo, deque(maxlen=self._ventana)
            )
            cola.append(vector)
            if len(cola) < self._ventana:
                return None
            flat = np.asarray(list(cola), dtype="float64").reshape(1, -1)
        # decision_function es seguro fuera del candado (solo lectura).
        score = self._score_ensamble(flat)
        umbral = self.umbral_actual
        es_anom = score < umbral
        resultado = {
            "es_anomalia": es_anom,
            "score": round(score, 4),
            "umbral": round(umbral, 4),
            "features": {name: float(muestra.get(name, 0.0) or 0.0)
                         for name in self._features_modelo},
        }
        return self._ampliar_con_zona(resultado, nodo, score, flat[0])

    def evaluar_lote(self, nodo: str, muestras: list[dict]) -> list[dict]:
        """Puntua una secuencia de muestras SIN tocar la ventana en vivo.

        Usada por la importacion de cargas de trabajo externas: crea una
        ventana local por llamada, reproduce el detector en orden y
        devuelve las predicciones a partir de que la ventana se llena.

        ``muestras`` deben venir ordenadas cronologicamente. Devuelve una
        lista con las predicciones y el indice original de cada una.
        """
        if not muestras:
            return []
        cola = deque(maxlen=self._ventana)
        resultados: list[dict] = []
        for idx, muestra in enumerate(muestras):
            vector = self._escalar(muestra)
            cola.append(vector)
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
                "features": {name: float(muestra.get(name, 0.0) or 0.0)
                             for name in self._features_modelo},
            }
            resultados.append(
                self._ampliar_con_zona(resultado, nodo, score, flat[0])
            )
        return resultados


# Instancia unica a nivel de aplicacion.
_detector = None


def get_detector() -> Detector:
    global _detector
    if _detector is None:
        _detector = Detector(
            ruta_modelo=os.path.join(ML_ARTIFACTS, "modelo_isolation_forest.joblib"),
            ruta_modelo_copod=os.path.join(ML_ARTIFACTS, "modelo_copod.joblib"),
            ruta_scaler=os.path.join(ML_ARTIFACTS, "scaler.joblib"),
            ruta_features=os.path.join(ML_ARTIFACTS, "features_modelo.csv"),
            ruta_train_pkl=TRAIN_PKL if os.path.exists(TRAIN_PKL) else None,
        )
    return _detector