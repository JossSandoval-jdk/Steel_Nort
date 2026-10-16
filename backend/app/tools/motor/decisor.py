"""
decisor.py
==========
Capa de decisión por zonas para emitir alertas estables.

Convierte el score bruto por ventana en una decisión con:
  - Zonas + histéresis: CRITICA < q01 <= WARNING_ESCALA < q10 <= NORMAL.
    Una vez en CRITICA solo se sale cruzando el umbral de salida efectivo.
  - Consenso asimétrico N-de-M: activar exige N de M en CRITICA; limpiar
    exige N_LIMPIAR de M_LIMPIAR en NORMAL.
  - Anti-flap (cooldown): tras un cambio de zona, la zona queda congelada
    COOLDOWN ventanas.
  - Coherencia MVN: distancia de Mahalanobis vs train, umbral empírico
    (cuantil 0.99 del propio train). Señal para diagnóstico, no decide.

La clase es un autómata puro (sin BD, sin I/O). Alimenta una ventana a la
vez y devuelve la decisión de ese paso.

Variables de entorno:
    STEELNORT_ZONAL           "1" (activado) | "0"
    STEELNORT_ZONA_N          N para activar (default 2)
    STEELNORT_ZONA_M          M para activar (default 3)
    STEELNORT_ZONA_N_LIMPIAR  N para limpiar (default 3)
    STEELNORT_ZONA_M_LIMPIAR  M para limpiar (default 3)
    STEELNORT_ZONA_COOLDOWN   ventanas de debounce (default 2)
    STEELNORT_ZONA_SALIR      umbral de salida de CRITICA (opcional)
    STEELNORT_ZONA_MAX_CRITICA ventanas seguidas antes del valve (default 12)
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
    """Autómata de zona + persistencia + anti-flap + coherencia MVN."""

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
        n_max_critica: int | None = None,
    ) -> None:
        self._q10 = q10
        self._q05 = q05
        self._q01 = q01

        # Entrada y salida de CRITICA (histéresis).
        self._entrar = q01
        self._salir = q10

        self._n_alertar = n_alertar if n_alertar is not None else _env_int("STEELNORT_ZONA_N", 2)
        self._m_alertar = m_alertar if m_alertar is not None else _env_int("STEELNORT_ZONA_M", 3)
        self._n_limpiar = n_limpiar if n_limpiar is not None else _env_int("STEELNORT_ZONA_N_LIMPIAR", 3)
        self._m_limpiar = m_limpiar if m_limpiar is not None else _env_int("STEELNORT_ZONA_M_LIMPIAR", 3)
        self._cooldown = cooldown if cooldown is not None else _env_int("STEELNORT_ZONA_COOLDOWN", 2)

        # Umbral de salida efectivo. Si q10 queda fuera de alcance en
        # operación (score desplazado), se usa el punto medio de la banda
        # [q01, q10] para que el autómata pueda volver a NORMAL.
        salida_env = os.getenv("STEELNORT_ZONA_SALIR")
        if salida_env:
            self._salir_ef = float(salida_env)
        elif q10 > q01 and (q10 - q01) > 1e-9:
            self._salir_ef = q01 + 0.5 * (q10 - q01)
        else:
            self._salir_ef = q10

        self._mvn = mvn or {}

        self._zona = NORMAL
        self._alerta = False
        self._cooldown_restante = 0
        self._racha_critica = 0
        self._hist_alertar = deque(maxlen=self._m_alertar)
        self._hist_limpiar = deque(maxlen=self._m_limpiar)

        # Válvula de escape: si el score operativo está desplazado y nunca
        # cruza la salida, se fuerza la salida tras N ventanas seguidas en
        # CRITICA. Evita alerta infinita por desajuste train/servicio.
        self._max_critica = n_max_critica if n_max_critica is not None else _env_int(
            "STEELNORT_ZONA_MAX_CRITICA", 12
        )

    # ------------------------------------------------------------------
    # Coherencia MVN
    # ------------------------------------------------------------------
    def mvn_distancia(self, flat: np.ndarray) -> float:
        """Distancia de Mahalanobis vs referencia de train."""
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
    # Autómata
    # ------------------------------------------------------------------
    def _zona_raw(self, score: float) -> str:
        """Zona por score con histéresis de salida de CRITICA."""
        if self._zona == CRITICA and score < self._salir_ef:
            return CRITICA
        if score < self._entrar:
            return CRITICA
        if score < self._salir:
            return WARNING_ESCALA
        return NORMAL

    def alimentar(self, score: float, flat: np.ndarray | None = None) -> dict:
        """Procesa una ventana y devuelve la decisión del paso."""
        zona_previa = self._zona
        alerta_previa = self._alerta

        helado = self._cooldown_restante > 0
        valve = False

        if helado:
            self._cooldown_restante -= 1
            nueva = zona_previa  # congelada durante el debounce
        else:
            nueva = self._zona_raw(score)
            # Válvula: demasiadas ventanas seguidas en CRITICA indican
            # desajuste entre score de operación y umbrales de train.
            if (
                self._max_critica
                and zona_previa == CRITICA
                and nueva == CRITICA
                and self._racha_critica >= self._max_critica
            ):
                nueva = WARNING_ESCALA
                valve = True
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

        # Tras el valve hay que apagar la alerta a propósito: si el score
        # está desplazado, NORMAL tampoco se alcanza.
        if valve:
            self._alerta = False
            self._hist_alertar.clear()
            self._hist_limpiar.clear()
            self._hist_alertar.append(False)
            self._hist_limpiar.append(False)

        mvn_dist = self.mvn_distancia(flat)
        regla = self._texto_regla(
            score, nueva, zona_previa, helado, valve)
        return {
            "zona": nueva,
            "es_anomalia": self._alerta,
            "alerta_activa": self._alerta,
            "alerta_nueva": self._alerta and not alerta_previa,
            "score": round(float(score), 4),
            "racha_critica": int(self._racha_critica),
            "cooldown": helado,
            "valve": valve,
            "regla": regla,
            "umbral_entrada": round(float(self._entrar), 4),
            "umbral_salida": round(float(self._salir_ef), 4),
            "mvn_dist": round(mvn_dist, 2) if np.isfinite(mvn_dist) else None,
            "mvn_coherente": self.mvn_coherente(flat),
            "hist_critica": "".join("C" if c else "." for c in self._hist_alertar),
        }

    def _texto_regla(self, score, nueva, zona_previa, helado, valve) -> str:
        """Texto de la regla que produjo la decisión (para el diagnóstico)."""
        if valve:
            return (
                f"R-VALVE: {self._racha_critica} ventanas seguidas en CRITICA "
                f"superan el máximo {self._max_critica}; se fuerza salida a "
                f"WARNING_ESCALA (score {score:.4f}). Indica desajuste entre "
                f"el score de operación y los umbrales del entrenamiento."
            )
        if helado:
            return (
                f"R-DEBOUNCE: zona congelada {zona_previa} por "
                f"{self._cooldown_restante + 1} ventana(s) de cooldown"
            )
        if nueva == CRITICA:
            return (
                f"R-CRITICA: score {score:.4f} < umbral de entrada q01 "
                f"{self._entrar:.4f} (o en racha crítica {self._racha_critica})"
            )
        if nueva == WARNING_ESCALA:
            return (
                f"R-ADVERTENCIA: score {score:.4f} entre q01 {self._entrar:.4f} "
                f"y q10 {self._salir:.4f} (zona gris, no alerta)"
            )
        return (
            f"R-NORMAL: score {score:.4f} >= salida efectiva "
            f"{self._salir_ef:.4f}"
        )

    def estado(self) -> dict:
        return {
            "zona": self._zona,
            "alerta": self._alerta,
            "racha_critica": self._racha_critica,
            "cooldown_restante": self._cooldown_restante,
            "hist_alertar": list(self._hist_alertar),
            "umbral_entrada": self._entrar,
            "umbral_salida": self._salir_ef,
            "umbral_salida_train": self._salir,
        }