"""Deteccion de candidatos (LOF / Elliptic Envelope / OCSVM / COPOD).

Un solo script parametrizado reemplaza los viejos ``03.1`` a ``03.4`` que
eran copias casi identicas de ``03_deteccion_isolation_forest.py``.

Para cada detector: entrena sobre train, guarda el modelo, evalua alertas
en test por umbral (q10/q05/q01), guarda scores del train e importancia de
variables por permutacion. Los CSVs llevan el prefijo del detector
(``alertas_test_<prefix>.csv``, ``scores_muestras_<prefix>.csv``,
``importancia_variables_<prefix>.csv``) y el modelo ``modelo_<archivo>.joblib``.

Convencion de scores: mayor = normal (COPOD se invierte porque PyOD da
valores altos a las anomalias).

Uso (desde ``nucleo/modeling``):
    python experimental/detectar_candidatos.py              # todos
    python experimental/detectar_candidatos.py lof ocsvm    # solo los indicados
"""

import argparse
import os
import pickle
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.covariance import EllipticEnvelope
from sklearn.inspection import permutation_importance
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from pyod.models.copod import COPOD

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

DETECTORES = {
    # prefijo, nombre de archivo del modelo, constructor, con copod=PyOD
    "lof":      ("lof",      "modelo_lof",      lambda: LocalOutlierFactor(
                     n_neighbors=35, contamination="auto", novelty=True), False),
    "elliptic": ("elliptic", "modelo_elliptic_envelope",
                 lambda: EllipticEnvelope(random_state=config.SEED,
                                          contamination=0.05), False),
    "ocsvm":    ("ocsvm",    "modelo_ocsvm",
                 lambda: OneClassSVM(nu=0.05, kernel="rbf", gamma="scale"), False),
    "copod":    ("copod",    "modelo_copod", lambda: COPOD(contamination=0.05), True),
}

# Importancia por permutacion: hay que subir cuando mas normal -> signo -1
# (ocsvm y copod, porque su decision_function crece con lo anormal).
SIGNO_IMPORTANCIA = {"ocsvm": -1.0, "copod": -1.0}


def log(msg):
    print(f"[DETECCION] {msg}", flush=True)


def cargar_muestras(ruta):
    with open(ruta, "rb") as f:
        return pickle.load(f)


def seleccionar_features(datos):
    """Usa SOLO las VARIABLES_MODELO de config (igual que el pipeline)."""
    modelo = [c for c in config.VARIABLES_MODELO if c in datos["features"]]
    indice = [datos["features"].index(c) for c in modelo]
    log(f"Modelo con {len(indice)} variables del motor/apoyo - poda aplicada.")
    return indice


def flat(x, indice):
    return x[:, :, indice].reshape(x.shape[0], -1)


def banderillas(s_train, test, scores, pred):
    """DataFrame de alertas por ventana de test con los 3 umbrales del train."""
    df = pd.DataFrame({
        "idx": range(len(test["ventanas"])),
        "run": test["runs"],
        "inicio": [w["inicio"] for w in test["ventanas"]],
        "fin": [w["fin"] for w in test["ventanas"]],
        "score": scores,
        "prediccion": pred,
    })
    for etiqueta, cuantil in (("q10", 0.10), ("q05", 0.05), ("q01", 0.01)):
        df[etiqueta] = (df["score"] < np.quantile(s_train, cuantil)).astype(int)
    return df


def detectar(nombre):
    prefijo, archivo, fab, pyod = DETECTORES[nombre]
    log(f"==> {nombre.upper()}")

    ruta_train = os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl")
    ruta_test = os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl")
    if not (os.path.exists(ruta_train) and os.path.exists(ruta_test)):
        log("Faltan las muestras. Ejecuta 01_muestras.py.")
        return

    train = cargar_muestras(ruta_train)
    test = cargar_muestras(ruta_test)
    indice = seleccionar_features(train)
    X_train, X_test = flat(train["X"], indice), flat(test["X"], indice)
    log(f"Train: {X_train.shape[0]} muestras x {X_train.shape[1]} caracteristicas")
    log(f"Test: {X_test.shape[0]} muestras")

    modelo = fab()
    modelo.fit(X_train)

    os.makedirs(config.DIR_DETECCION, exist_ok=True)
    joblib.dump(modelo, os.path.join(config.DIR_DETECCION, f"{archivo}.joblib"))

    # Scores: mayor = normal. PyOD (copod) devuelve mayor = anormal -> se invierte.
    def scores(modelo, X):
        s = modelo.decision_function(X)
        return -s if pyod else s

    s_train, s_test = scores(modelo, X_train), scores(modelo, X_test)

    if pyod:
        pred = lambda X: np.where(modelo.predict(X) == 1, -1, 1)  # noqa: E731
    else:
        pred = lambda X: modelo.predict(X)  # noqa: E731

    df_alertas = banderillas(s_train, test, s_test, pred(X_test))
    df_alertas.to_csv(os.path.join(config.DIR_DETECCION,
                                   f"alertas_test_{prefijo}.csv"),
                      index=False, encoding="utf-8-sig")

    df_scores = pd.DataFrame({
        "idx": range(len(train["ventanas"])),
        "run": train["runs"],
        "score": s_train,
        "prediccion": pred(X_train),
    })
    df_scores.to_csv(os.path.join(config.DIR_DETECCION,
                                  f"scores_muestras_{prefijo}.csv"),
                     index=False, encoding="utf-8-sig")

    signo = SIGNO_IMPORTANCIA.get(nombre, 1.0)
    X_imp = X_test if len(X_test) > 0 else X_train
    perm = permutation_importance(
        modelo, X_imp, y=np.zeros(len(X_imp)),
        scoring=lambda est, X, y=None: signo * np.mean(est.decision_function(X)),
        n_repeats=5, random_state=config.SEED, n_jobs=-1,
    )
    mant = [train["features"][i] for i in indice]
    v = config.VENTANA
    agg = {c: float(np.mean(np.abs(perm.importances_mean[i * v:(i + 1) * v]))) for i, c in enumerate(mant)}
    df_imp = pd.DataFrame([{"columna": c, "importancia": agg[c]} for c in mant])
    df_imp.sort_values("importancia", ascending=False).to_csv(
        os.path.join(config.DIR_DETECCION, f"importancia_variables_{prefijo}.csv"),
        index=False, encoding="utf-8-sig")

    print(f"\n=== {nombre.upper()} SOBRE REFERENCIA NORMAL ===")
    for q, _v in (("q10", 0.10), ("q05", 0.05), ("q01", 0.01)):
        fpr = float(df_alertas[q].mean())
        print(f"  umbral {q}: {int(df_alertas[q].sum())} / {len(df_alertas)} "
              f"alertas ({fpr * 100:.2f}%)")


def main():
    parser = argparse.ArgumentParser(description="Entrena detectores candidatos.")
    parser.add_argument("detectores", nargs="*", choices=list(DETECTORES),
                        default=list(DETECTORES), help="En blanco = todos.")
    args = parser.parse_args()
    for nombre in args.detectores:
        detectar(nombre)


if __name__ == "__main__":
    main()