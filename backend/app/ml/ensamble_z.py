"""Ensamble_Z: UNA sola fuente del z-score de componentes (ISO + COPOD).

Todo lo que toca el puntaje ENSEMBLE_Z vive aqui:

  - ``estadisticas()``: medias/devs de cada componente sobre el train
    (mismo contrato que el viejo ``ens_stats`` de los laboratorios).
  - ``z_score()``: estandariza los scores de los componentes y los
    promedia. Mayor = mas normal:
        z_comp = (score - media_train) / desv_train
        ENSEMBLE_Z = media(z_ISO, z_COPOD)
  - ``EnsambleZ``: envoltorio de produccion (modelo ISO + COPOD opcional)
    con ``ajustar()`` (calibra estadisticas y umbrales q10/q05/q01 sobre
    el train) y ``scores()/score()`` para predecir.

Consumidores: ``app/ml/detector.py`` (produccion) y los harness de
laboratorio ``validar_candidato.py``, ``medir_discriminacion.py`` y
``ajustar_isolation_forest.py`` (que importan ``estadisticas``/``z_score``).
"""

from __future__ import annotations

import numpy as np

EPS = 1e-12

# Umbrales por cuantil (orden del punto operativo de produccion).
QQ_NOMBRE = {0.10: "q10", 0.05: "q05", 0.01: "q01"}


def estadisticas(s_iso, s_cop) -> dict[str, float]:
    """Medias/desvs de train de cada componente (mayor = normal)."""
    return {
        "mu_iso": float(s_iso.mean()),
        "sd_iso": float(s_iso.std()) + EPS,
        "mu_copod": float(s_cop.mean()),
        "sd_copod": float(s_cop.std()) + EPS,
    }


def z_score(s_iso, s_cop, ens: dict | None):
    """ENSEMBLE_Z estandarizado (mayor = normal) para vectores o arrays.

    Sin componente COPOD (o sin estadisticas) devuelve el score de ISO
    tal cual, igual que el detector en modo "ISOLATION_FOREST".
    """
    if s_cop is None or ens is None:
        return s_iso
    return (
        (s_iso - ens["mu_iso"]) / ens["sd_iso"]
        + (s_cop - ens["mu_copod"]) / ens["sd_copod"]
    ) / 2.0


class EnsambleZ:
    """Envoltorio de produccion: modelos ISO (+COPOD) + estadisticas/umbrales."""

    def __init__(self, modelo_iso, modelo_copod=None) -> None:
        self.modelo_iso = modelo_iso
        self.modelo_copod = modelo_copod
        self._ens: dict | None = None
        self._umbrales: dict[str, float] = {}

    @property
    def modo(self) -> str:
        return "ENSEMBLE_Z" if self.modelo_copod is not None else "ISOLATION_FOREST"

    @property
    def estadisticas_ref(self) -> dict | None:
        return self._ens

    def _scores(self, X_sel):
        """Scores sin normalizar de cada componente (mayor = normal)."""
        s_iso = np.asarray(self.modelo_iso.decision_function(X_sel), dtype="float64")
        if self.modelo_copod is None:
            return s_iso, None
        s_cop = -np.asarray(self.modelo_copod.decision_function(X_sel), dtype="float64")
        return s_iso, s_cop

    def ajustar(self, X_train_sel, qs=(0.10, 0.05, 0.01)) -> dict[str, float]:
        """Calibra estadisticas y umbrales a partir del train."""
        s_iso, s_cop = self._scores(X_train_sel)
        self._ens = estadisticas(s_iso, s_cop) if s_cop is not None else None
        z = np.asarray(z_score(s_iso, s_cop, self._ens), dtype="float64")
        self._umbrales = {
            QQ_NOMBRE[q]: float(np.quantile(z, q)) for q in qs
        }
        return self._umbrales

    def scores(self, X_sel) -> np.ndarray:
        """ENSEMBLE_Z de cada ventana de ``X_sel``."""
        s_iso, s_cop = self._scores(X_sel)
        return np.asarray(z_score(s_iso, s_cop, self._ens), dtype="float64")

    def score(self, flat) -> float:
        """ENSEMBLE_Z de una sola ventana aplanada."""
        s_iso, s_cop = self._scores(flat)
        if s_cop is None or self._ens is None:
            return float(s_iso[0])
        return float((z_score(s_iso, s_cop, self._ens))[0])