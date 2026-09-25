"""Etapa 1 del plan Anti-FP/Anti-Drift: capa de decision por zonas.

Convierte el score bruto por ventana en una decision ESTABLE para emision
de alertas, combinando cuatro mecanismos (todos configurables por entorno):

  Zonas + histeresis
      score <  q01            -> CRITICA
      q01 <= score < q10      -> WARNING_ESCALA  (zona gris)
      score >= q10            -> NORMAL
      Una vez en CRITICA solo se sale cuando el score vuelve a >= q10
      (entrar cuesta q01, salir cuesta q10: histeresis anti-recaida).

  Consenso asimetrico N-de-M
      La alerta estable se ACTIVA cuando >= N de las ultimas M ventanas
      estan en CRITICA, pero solo se DESACTIVA cuando >= N_LIMPIAR de las
      ultimas M_LIMPIAR vuelven a NORMAL (N_limpiar/M_limpiar distintos
      hace la transicion asimetrica a proposito).

  Anti-flap (cooldown)
      Tras un cambio de zona, la zona queda congelada COOLDOWN ventanas
      (debounce: ignora parpadeos inmediatos).

  Coherencia MVN
      Cada ventana (vector aplanado F*V en el espacio estandarizado) se
      contrasta contra la referencia multivariate normal de entrenamiento
      (Mahalanobis). El umbral de coherencia es EMPIRICO: el cuantil 0.99
      de las distancias del propio train (la referencia es de rango
      deficiente cuando hay pocas ventanas). Fuera de ese cuantil la ventana
      se marca incoherente (fuera de distribucion); se expone como senal
      para diagnostico/deriva, no decide sola.

La clase es un automata de estado puro (sin BD, sin I/O): recibe una ventana
a la vez y devuelve la decision de ese paso. Consumo tipico:

    dz = DecisorZonal(q10=..., q05=..., q01=..., mvn={'mu':...,'cov_inv':...})
    for score, flat in flujo:
        paso = dz.alimentar(score, flat)
        if paso['es_anomalia']:  # alerta estable (ya con persistencia)
            ...

Variables de entorno (ver tambien ``Detector``):

    STEELNORT_ZONAL          "1" (activado) | "0"  (solo score bruto)
    STEELNORT_ZONA_N         N para activar  (default 2)
    STEELNORT_ZONA_M         M para activar  (default 3)
    STEELNORT_ZONA_N_LIMPIAR N para limpiar  (default 3)
    STEELNORT_ZONA_M_LIMPIAR M para limpiar  (default 3)
    STEELNORT_ZONA_COOLDOWN  ventanas de debounce (default 2)
"""

from __future__ import annotations

import os
from collections import deque

import numpy as np
from scipy.stats import chi2

NORMAL = "NORMAL"
WARNING_ESCALA = "WARNING_ESCALA"
CRITICA = "CRITICA"
ZONAS = (NORMAL, WARNING_ESCALA, CRITICA)


def _env_int(nombre: str, default: int) -> int:
    return int(os.getenv(nombre, str(default)))


class DecisorZonal:
    """Automata de zona + persistencia + anti-flap + coherencia MVN."""

    def __init__(
        self,
        q10: float,
        q05: float,
        q01: float,
        mvn: dict | None = None,
        n_alertar: int | None = None,
        m_alertar: int | None = None,
        n_limpiar: int | None = None,
        m_limpiar: int | None = None,
        cooldown: int | None = None,
    ) -> None:
        self._q10 = q10
        self._q05 = q05
        self._q01 = q01
        # histeresis: entrar en CRITICA exige cruzar q01; salir exige q10
        self._entrar = q01
        self._salir = q10

        self._n_alertar = n_alertar if n_alertar is not None else _env_int("STEELNORT_ZONA_N", 2)
        self._m_alertar = m_alertar if m_alertar is not None else _env_int("STEELNORT_ZONA_M", 3)
        self._n_limpiar = n_limpiar if n_limpiar is not None else _env_int("STEELNORT_ZONA_N_LIMPIAR", 3)
        self._m_limpiar = m_limpiar if m_limpiar is not None else _env_int("STEELNORT_ZONA_M_LIMPIAR", 3)
        self._cooldown = cooldown if cooldown is not None else _env_int("STEELNORT_ZONA_COOLDOWN", 2)

        self._mvn = mvn or {}

        self._zona: str = NORMAL
        self._alerta = False
        self._cooldown_restante = 0
        self._racha_critica = 0
        self._hist_alertar: deque[bool] = deque(maxlen=self._m_alertar)
        self._hist_limpiar: deque[bool] = deque(maxlen=self._m_limpiar)

    # ------------------------------------------------------------------
    # Coherencia MVN
    # ------------------------------------------------------------------

    def mvn_distancia(self, flat: np.ndarray) -> float:
        """Distancia de Mahalanobis de la ventana vs referencia de train."""
        if not self._mvn or flat is None:
            return float("nan")
        mu = np.asarray(self._mvn["mu"], dtype="float64")
        inv = np.asarray(self._mvn["cov_inv"], dtype="float64")
        try:
            x = np.asarray(flat, dtype="float64").reshape(-1)
            d = x - mu
            with np.errstate(all="ignore"):
                return float(d @ inv @ d)
        except Exception:
            return float("nan")

    def mvn_coherente(self, flat: np.ndarray) -> bool:
        if not self._mvn:
            return True
        df = float(self._mvn.get("df", 170.0))
        dist = self.mvn_distancia(flat)
        if not np.isfinite(dist):
            return False
        return dist <= float(self._mvn.get("chi2_99", chi2.ppf(0.99, df=df)))

    # ------------------------------------------------------------------
    # Automata
    # ------------------------------------------------------------------

    def _zona_raw(self, score: float) -> str:
        """Zona por score con histeresis de salida de CRITICA.

        Estando en CRITICA, solo se baja a WARNING/NORMAL cuando el score
        vuelve por encima de ``q10`` (si no, sigue CRITICA aunque pase por
        encima de q01).
        """
        if self._zona == CRITICA and score < self._salir:
            return CRITICA
        if score < self._entrar:
            return CRITICA
        if score < self._salir:
            return WARNING_ESCALA
        return NORMAL

    def alimentar(self, score: float, flat: np.ndarray | None = None) -> dict:
        """Procesa una ventana y devuelve la decision del paso.

        ``score`` es el ENSEMBLE_Z (menor = mas anomalo); ``flat`` es el
        vector aplanado V*F estandarizado (opcional, solo para MVN).
        """
        zona_previa = self._zona

        helado = self._cooldown_restante > 0
        if helado:
            self._cooldown_restante -= 1
            nueva = zona_previa  # congelada durante el debounce
        else:
            nueva = self._zona_raw(score)
            if nueva != zona_previa:
                self._cooldown_restante = self._cooldown

        self._zona = nueva
        self._racha_critica = self._racha_critica + 1 if nueva == CRITICA else 0

        critica = nueva == CRITICA
        self._hist_alertar.append(critica)
        self._hist_limpiar.append(nueva == NORMAL)

        n_c = sum(1 for c in self._hist_alertar if c)
        n_n = sum(1 for c in self._hist_limpiar if c)
        if n_c >= self._n_alertar:
            self._alerta = True
        elif n_n >= self._n_limpiar:
            self._alerta = False

        mvn_dist = self.mvn_distancia(flat)
        return {
            "zona": nueva,
            "es_anomalia": self._alerta,
            "score": round(float(score), 4),
            "racha_critica": int(self._racha_critica),
            "cooldown": helado,
            "mvn_dist": round(mvn_dist, 2) if np.isfinite(mvn_dist) else None,
            "mvn_coherente": self.mvn_coherente(flat),
            "hist_critica": "".join(
                "C" if c else "." for c in self._hist_alertar
            ),
        }

    def estado(self) -> dict:
        return {
            "zona": self._zona,
            "alerta": self._alerta,
            "racha_critica": self._racha_critica,
            "cooldown_restante": self._cooldown_restante,
            "hist_alertar": list(self._hist_alertar),
        }