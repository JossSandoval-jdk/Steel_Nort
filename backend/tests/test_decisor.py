"""Pruebas de la Etapa 1 (Anti-FP): capa zonal con histeresis, consenso
asimetrico N-de-M, anti-flap y coherencia MVN (app/ml/decisor.py).
"""

import numpy as np
import pytest

from app.ml.decisor import CRITICA, NORMAL, WARNING_ESCALA, DecisorZonal

Q10, Q05, Q01 = -1.1804, -1.3569, -2.1446


def dz(**kw):
    return DecisorZonal(q10=Q10, q05=Q05, q01=Q01, mvn=None, **kw)


# ---------------------------------------------------------------------------
# Zonas e histeresis
# ---------------------------------------------------------------------------
def test_zona_normal_warning_critica_por_score():
    d = dz(cooldown=0)
    assert d.alimentar(0.0)["zona"] == NORMAL
    assert d.alimentar(-1.5)["zona"] == WARNING_ESCALA
    assert d.alimentar(-2.5)["zona"] == CRITICA


def test_histeresis_sale_al_superar_salida_efectiva():
    d = dz(cooldown=0)
    d.alimentar(-2.5)            # entra CRITICA (< q01)
    paso = d.alimentar(-1.5)     # supera la salida efectiva, entra en zona gris
    assert paso["zona"] == WARNING_ESCALA
    paso2 = d.alimentar(-1.1)    # score >= q10: llega a NORMAL
    assert paso2["zona"] in (NORMAL, WARNING_ESCALA)


def test_alerta_nueva_solo_se_emite_al_activar_el_estado():
    d = dz(cooldown=0, n_alertar=2, m_alertar=3)
    assert d.alimentar(-2.5)["alerta_nueva"] is False
    segunda = d.alimentar(-2.5)
    assert segunda["alerta_nueva"] is True
    tercera = d.alimentar(-2.5)
    assert tercera["es_anomalia"] is True
    assert tercera["alerta_nueva"] is False


# ---------------------------------------------------------------------------
# Consenso asimetrico N-de-M
# ---------------------------------------------------------------------------
def test_una_ventana_critica_no_alerta():
    d = dz(cooldown=0, n_alertar=2, m_alertar=3, n_limpiar=3, m_limpiar=3)
    d.alimentar(-2.5)            # una sola CRITICA
    d.alimentar(-1.0)
    d.alimentar(-1.0)
    assert d.estado()["alerta"] is False


def test_dos_criticas_consecutivas_alerta_y_limpieza_asimetrica():
    d = dz(cooldown=0, n_alertar=2, m_alertar=3, n_limpiar=3, m_limpiar=3)
    d.alimentar(-2.5)            # 1/<3 -> sin alerta
    d.alimentar(-2.5)
    assert d.estado()["alerta"] is True
    # salir hacia NORMAL con 2 normales no alcanza a limpiar (exige 3)
    d.alimentar(-1.0)
    d.alimentar(-1.0)
    assert d.estado()["alerta"] is True
    d.alimentar(0.0)             # tercera normal: limpia
    assert d.estado()["alerta"] is False


# ---------------------------------------------------------------------------
# Anti-flap (cooldown)
# ---------------------------------------------------------------------------
def test_cooldown_congela_la_zona_una_ventana():
    d = dz(cooldown=2)
    d.alimentar(0.0)             # NORMAL
    p1 = d.alimentar(-2.5)       # intenta CRITICA -> entra, arranca cooldown
    assert p1["zona"] == CRITICA
    p2 = d.alimentar(1.0)        # ventana siguiente: congelada en CRITICA
    assert p2["zona"] == CRITICA and p2["cooldown"] is True
    p3 = d.alimentar(1.0)        # segunda congelada
    assert p3["zona"] == CRITICA and p3["cooldown"] is True
    p4 = d.alimentar(1.0)        # cooldown agotado -> NORMAL
    assert p4["zona"] == NORMAL


# ---------------------------------------------------------------------------
# Coherencia MVN
# ---------------------------------------------------------------------------
def test_mvn_ventana_lejana_incoherente():
    ref = {"mu": np.zeros(5), "cov_inv": np.eye(5),
           "df": 5.0, "chi2_99": 15.086}
    d = DecisorZonal(q10=Q10, q05=Q05, q01=Q01, mvn=ref)
    paso_cerca = d.alimentar(0.0, flat=np.zeros(5))
    assert paso_cerca["mvn_coherente"] is True
    paso_lejos = d.alimentar(0.0, flat=np.full(5, 3.0))
    assert paso_lejos["mvn_coherente"] is False
    assert paso_lejos["mvn_dist"] > 15.0


def test_mvn_sin_referencia_es_coherente():
    d = dz()
    assert d.alimentar(0.0, flat=np.zeros(5))["mvn_coherente"] is True


# ---------------------------------------------------------------------------
# Threshold empirico del train (cuantil de las distancias)
# ---------------------------------------------------------------------------
def test_mvn_umbral_empirico_marca_el_1pct_teorico():
    rng = np.random.default_rng(7)
    X = rng.normal(size=(200, 10))
    inv = np.linalg.pinv(np.cov(X, rowvar=False) + 1e-6 * np.eye(10))
    d = X - X.mean(0)
    dists = np.einsum("ij,jk,ik->i", d, inv, d)
    ref = {"mu": X.mean(0), "cov_inv": inv, "df": 10.0,
           "chi2_99": float(np.quantile(dists, 0.99))}
    dzv = DecisorZonal(q10=Q10, q05=Q05, q01=Q01, mvn=ref)
    # una ventana 6 sigma en las 10 dims => incoherente
    paso = dzv.alimentar(-2.5, flat=np.full(10, 6.0))
    assert paso["mvn_coherente"] is False