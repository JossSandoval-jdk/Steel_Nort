"""Suite de validación del detector (EN SSTE_Z + IsolationForest).

Ejecutar desde la raíz del backend:
    python -m pytest tests -q

Las pruebas leen los artefactos ya generados por experimental/validar_candidato.py
(hold-out por corrida) y verifican: esquema de features, transformación/reshape,
umbrales, determinismo, latencia, robustez y resultados de hold-out.
"""

import csv
import json
import os
import time

import joblib
import numpy as np
import pandas as pd

import config

DIR_VAL = os.path.join(config.DIR_DETECCION, "validacion")
PKL_TRAIN = os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl")
PKL_TEST = os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl")
FEATURES_CSV = os.path.join(config.DIR_CORRELACION, "features_modelo.csv")


def cargar_bundle():
    return joblib.load(os.path.join(DIR_VAL, "modelo_candidato.joblib"))


def cargar_muestra(ruta):
    w = joblib.load(ruta)
    return w


def ens_score(bundle, X):
    si = bundle["iso"].decision_function(X)
    scp = -bundle["copod"].decision_function(X)
    es = bundle["ens_stats"]
    return ((si - es["mu_iso"]) / es["sd_iso"] + (scp - es["mu_copod"]) / es["sd_copod"]) / 2.0


def ventanas_escaladas(bundle, muestra):
    """Devuelve (X 1D por ventana, n) en el espacio del candidato.

    Rehace el mismo pipeline que stage_freeze: des-hace la estandarización
    guardada en el pkl y re-escala con el scaler del bundle.
    """
    ind = bundle["indice_22"]
    raw = (muestra["X"] * muestra["scaler"].scale_ + muestra["scaler"].mean_)[:, :, ind]
    F = len(bundle["features"])
    n = raw.shape[0]
    X = bundle["scaler"].transform(raw.reshape(-1, F)).reshape(n, -1)
    return X, n


# ---------------------------------------------------------------------------
# Esquema de features
# ---------------------------------------------------------------------------
def test_esquema_features_consistentes():
    bundle = cargar_bundle()
    train = cargar_muestra(PKL_TRAIN)

    assert len(train["features"]) == 22
    assert bundle["ventana"] == 10
    assert bundle["features"] == config.VARIABLES_MODELO, "orden/lista del bundle != VARIABLES_MODELO"
    assert len(bundle["indice_22"]) == 17
    assert set(bundle["features"]) <= set(train["features"])


def test_features_modelo_csv_igual_a_variables_modelo():
    with open(FEATURES_CSV, encoding="utf-8-sig") as f:
        cols = [r[0] for r in csv.reader(f) if r and r[0].strip()]
    # la primera fila es el encabezado ('columna')
    cols = cols[1:]
    assert cols == config.VARIABLES_MODELO


# ---------------------------------------------------------------------------
# Transformación / reshape
# ---------------------------------------------------------------------------
def test_transformacion_reshape():
    bundle = cargar_bundle()
    train = cargar_muestra(PKL_TRAIN)
    assert train["X"].shape[1:] == (10, 22), f"esperaba (10,22), tengo {train['X'].shape}"

    X, n = ventanas_escaladas(bundle, train)
    assert X.shape == (n, 10 * 17)
    # el scaler del bundle está ajustado sobre el train; el z-score global es ~1
    assert 0.7 < X.std() < 1.3


# ---------------------------------------------------------------------------
# Umbrales
# ---------------------------------------------------------------------------
def test_umbrales_orden_y_alertas_train():
    bundle = cargar_bundle()
    umb = bundle["umbrales"]
    assert umb["q10"] > umb["q05"] > umb["q01"]

    # el umbral fue definido como cuantil del train completo (230 ventanas):
    # ~1% bajo q01 y ~10% bajo q10
    train = cargar_muestra(PKL_TRAIN)
    X, n = ventanas_escaladas(bundle, train)
    s = ens_score(bundle, X)
    f_q01 = float((s < umb["q01"]).mean())
    f_q10 = float((s < umb["q10"]).mean())
    assert 0.001 < f_q01 < 0.03
    assert 0.05 < f_q10 < 0.15


def test_umbrales_coinciden_registro():
    bundle = cargar_bundle()
    with open(os.path.join(DIR_VAL, "registro_modelo.json"), encoding="utf-8") as f:
        reg = json.load(f)
    for k in ("q10", "q05", "q01"):
        assert abs(bundle["umbrales"][k] - reg["umbrales_ensamble_z"][k]) < 1e-9


# ---------------------------------------------------------------------------
# Determinismo (misma entrada -> misma salida)
# ---------------------------------------------------------------------------
def test_determinismo_score():
    bundle = cargar_bundle()
    train = cargar_muestra(PKL_TRAIN)
    X, _ = ventanas_escaladas(bundle, train[:10] if isinstance(train, list) else train)
    s1 = ens_score(bundle, X)
    s2 = ens_score(bundle, X)
    np.testing.assert_array_equal(s1, s2)
    assert np.isfinite(s1).all()


# ---------------------------------------------------------------------------
# Latencia
# ---------------------------------------------------------------------------
def test_latencia_lote():
    bundle = cargar_bundle()
    test = cargar_muestra(PKL_TEST)
    X, n = ventanas_escaladas(bundle, test)
    rep = np.repeat(X, max(1, 1000 // n), axis=0)[:1000]
    t0 = time.perf_counter()
    ens_score(bundle, rep)
    dt = time.perf_counter() - t0
    assert dt < 10.0, f"1000 ventanas tardaron {dt:.2f}s"
    assert dt / 1000 < 0.01, ">10ms/ventana"


# ---------------------------------------------------------------------------
# Robustez
# ---------------------------------------------------------------------------
def test_nan_no_rompe_y_es_finito():
    bundle = cargar_bundle()
    test = cargar_muestra(PKL_TEST)
    X, _ = ventanas_escaladas(bundle, test)
    pert = X[:5].copy()
    pert[0, 0] = np.nan
    with np.errstate(all="ignore"):
        s = ens_score(bundle, pert)
    assert np.isfinite(s).all(), "NaN propagado a la decisión"


def test_decision_falla_estable_ante_ruido():
    # las ventanas de falla quedan lejos del umbral: ruido mínimo no las decide cambiar
    bundle = cargar_bundle()
    test = cargar_muestra(PKL_TEST)
    X, _ = ventanas_escaladas(bundle, test)
    umb = bundle["umbrales"]["q01"]
    base = ens_score(bundle, X) < umb
    rng = np.random.default_rng(42)
    pert = X + rng.normal(0, 0.05, X.shape)
    flips = int(np.count_nonzero((ens_score(bundle, pert) < umb) != base))
    assert flips == 0, f"{flips} ventanas de falla cambiaron de decisión bajo ruido"


# ---------------------------------------------------------------------------
# Resultados del hold-out (datos no vistos)
# ---------------------------------------------------------------------------
def test_holdout_ensamble_z_ok():
    df = pd.read_csv(os.path.join(DIR_VAL, "resumen_modelos.csv"))
    ez = df[(df["esquema"] == "ENSEMBLE_Z") & (df["umbral"] == "q01")].iloc[0]
    ej = df[(df["esquema"] == "ENSEMBLE_Z") & (df["umbral"] == "q10")].iloc[0]
    assert ez["tpr"] == 1.0
    assert ez["fpr"] <= 0.10
    assert ez["precision"] >= 0.9
    # el umbral más exigente (q10) no puede superar al más relajado en TPR por mucho
    assert ej["tpr"] >= 0.85


def test_aucs_presentes():
    auc = pd.read_csv(os.path.join(DIR_VAL, "aucs.csv"), index_col=0)
    assert {"roc_auc", "pr_auc"}.issubset(auc.columns)
    ez = auc.loc["ENSEMBLE_Z"]
    assert ez["roc_auc"] >= 0.99 and ez["pr_auc"] >= 0.99