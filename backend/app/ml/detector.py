"""Detector de anomalias en streaming.

Carga los artefactos entrenados (modelo_isolation_forest.joblib,
scaler.joblib y features_modelo.csv) y mantiene, por nodo, una ventana
movil de ``VENTANA`` muestras de las 21 variables seleccionadas.

Replica EXACTAMENTE la transformacion del entrenamiento:
  1. Se toman las 21 variables en el orden de ``features_modelo.csv``.
  2. Se escala cada variable con el StandardScaler (que se ajusto sobre
     las 22 variables del dataset) usando la posicion que cada nombre
     ocupa en la lista completa de 22 features.
  3. Cuando la ventana tiene 10 muestras se aplana a un vector de
     21 * 10 = 210 y se puntua con ``decision_function`` del
     IsolationForest. Score ALTO = normal, score BAJO = anomalo.

Los umbrales q10/q05/q01 se recalculan al arranque a partir del dataset
de entrenamiento (scaled) copiado en ``training/datasets``, igual que
hacia el pipeline offline.

Nota de coherencia: el pipeline offline normaliza "relativo por corrida";
en streaming se usa el scaler fijo del modelo (decision documentada en el
plan). Los features faltantes en una muestra se rellenan con 0.
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
UMBRAL_DEFECTO = os.getenv("TELEMETRIA_UMBRAL", "q01")  # q10 | q05 | q01


class Detector:
    """Puntua ventanas por nodo reusando el IsolationForest entrenado."""

    def __init__(
        self,
        ruta_modelo: str,
        ruta_scaler: str,
        ruta_features: str,
        ruta_train_pkl: str | None,
        ventana: int = VENTANA,
        umbral_nombre: str = UMBRAL_DEFECTO,
    ) -> None:
        self._ruta_modelo = ruta_modelo
        self._ruta_scaler = ruta_scaler
        self._ruta_features = ruta_features
        self._ventana = max(1, ventana)
        self._umbral_nombre = umbral_nombre if umbral_nombre in ("q10", "q05", "q01") else "q01"
        self._lock = Lock()
        self._windows: dict[str, deque] = {}
        self._modelo = None
        self._scaler: StandardScaler | None = None
        self._features21: list[str] = []
        self._posiciones: dict[str, int] = {}
        self._umbrales: dict[str, float] = {}

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

        df_feats = pd.read_csv(self._ruta_features)
        # La columna "columna" tiene por fila el nombre de cada feature.
        self._features21 = df_feats.iloc[:, 0].astype(str).str.strip().tolist()

        # Mapeo nombre -> posicion en el escalador (lista completa de 22).
        # Se deriva de la columna de nombres que el archivo de correlacion
        # usaba; si no coincide con las 22 del scaler, se asume 1:1.
        mean_len = len(self._scaler.mean_) if hasattr(self._scaler, "mean_") else 0
        if mean_len == len(self._features21):
            self._posiciones = {f: i for i, f in enumerate(self._features21)}
        # Si no coinciden (22 vs 21), las posiciones las resuelve
        # _calcular_umbrales() a partir del pkl de entrenamiento.

    def _calcular_umbrales(self, ruta_train_pkl: str | None) -> None:
        """Reconstruye q10/q05/q01 desde el dataset scaled de entrenamiento."""
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
            for nombre in self._features21:
                if nombre in self._posiciones:
                    indice.append(self._posiciones[nombre])
            if not indice or indice == [-1] * len(indice):
                indice = list(range(f))
            # X[:, :, indice].reshape(n, -1) exactamente como 03_deteccion.
            X_sel = X[:, :, indice].reshape(n, -1)
            scores = self._modelo.decision_function(X_sel)
            self._umbrales = {
                "q10": float(np.quantile(scores, 0.10)),
                "q05": float(np.quantile(scores, 0.05)),
                "q01": float(np.quantile(scores, 0.01)),
            }
            log.info("Umbrales deteccion: %s", self._umbrales)
        except Exception as exc:  # pragma: no cover - defensivo
            log.exception("No se pudieron calcular umbrales de train: %s", exc)

    def _escalar(self, valores: dict) -> list[float]:
        """Escala las 21 variables en el orden de features_modelo.csv."""
        out: list[float] = []
        for nombre in self._features21:
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

    @property
    def umbrales(self) -> dict[str, float]:
        return dict(self._umbrales)

    @property
    def umbral_actual(self) -> float:
        return self._umbrales.get(self._umbral_nombre, 0.0)

    def estado(self) -> dict:
        with self._lock:
            return {
                "ventana": self._ventana,
                "features": list(self._features21),
                "umbral_nombre": self._umbral_nombre,
                "umbrales": self._umbrales,
                "umbral_actual": self.umbral_actual,
                "ventanas_llenas": {
                    nodo: len(cola) >= self._ventana
                    for nodo, cola in self._windows.items()
                },
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
        score = float(self._modelo.decision_function(flat)[0])
        umbral = self.umbral_actual
        es_anom = score < umbral
        return {
            "es_anomalia": es_anom,
            "score": round(score, 4),
            "umbral": round(umbral, 4),
            "features": {name: float(muestra.get(name, 0.0) or 0.0)
                         for name in self._features21},
        }

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
            score = float(self._modelo.decision_function(flat)[0])
            umbral = self.umbral_actual
            resultados.append({
                "indice": idx,
                "es_anomalia": score < umbral,
                "score": round(score, 4),
                "umbral": round(umbral, 4),
                "features": {name: float(muestra.get(name, 0.0) or 0.0)
                             for name in self._features21},
            })
        return resultados


# Instancia unica a nivel de aplicacion.
_detector = None


def get_detector() -> Detector:
    global _detector
    if _detector is None:
        _detector = Detector(
            ruta_modelo=os.path.join(ML_ARTIFACTS, "modelo_isolation_forest.joblib"),
            ruta_scaler=os.path.join(ML_ARTIFACTS, "scaler.joblib"),
            ruta_features=os.path.join(ML_ARTIFACTS, "features_modelo.csv"),
            ruta_train_pkl=TRAIN_PKL if os.path.exists(TRAIN_PKL) else None,
        )
    return _detector