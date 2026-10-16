"""
04_exportar_produccion.py
=========================
Genera un bundle listo para el detector de producción a partir de
`artefactos_modelo.pkl`.

Ensemble elegido por la validación honesta (dejar-una-corrida-fuera +
normalización por corrida, ver experimental/HALLAZGOS_VALIDACION.md):

    ENSEMBLE_LOF_ELL (LOF + ELLIPTIC): F1 ventana ~0.96, TPR corrida 1.00,
    FPR corrida 0.00.
    ENSEMBLE_Z (ISO + COPOD, el anterior): F1 ~0.44, TPR corrida 0.38.

Salida (nuevo directorio, no modifica lo existente):
    output/modelado/produccion/
        scaler.joblib                 (alineado con las features del train)
        features_modelo.csv           (orden de columnas del scaler)
        modelo_isolation_forest.joblib
        modelo_lof.joblib
        modelo_elliptic.joblib
        dataset_muestras_train.pkl    (features completas + X_train 3D)
        meta.json
"""

import json
import os
import pickle

import joblib
import numpy as np
import pandas as pd
from sklearn.covariance import EllipticEnvelope
from sklearn.neighbors import LocalOutlierFactor

from modelado_config import DIR_MODELADO, SEED, VARIABLES_MODELO, VENTANA, log

DIR_PROD = os.path.join(DIR_MODELADO, "produccion")


def cargar_artefactos():
    ruta = os.path.join(DIR_MODELADO, "artefactos_modelo.pkl")
    if not os.path.exists(ruta):
        log(f"Falta {ruta}. Ejecuta modelado/01_entrenamiento.py.")
        return None
    with open(ruta, "rb") as f:
        return pickle.load(f)


def main():
    art = cargar_artefactos()
    if art is None:
        return

    features = art["features"]
    indices = [features.index(c) for c in VARIABLES_MODELO if c in features]
    columnas = [c for c in VARIABLES_MODELO if c in features]
    log(f"Features del modelo: {len(columnas)}")

    Xtr = art["X_train"][:, :, indices].reshape(len(art["X_train"]), -1)

    # Reentrena los componentes del ensamble sobre el espacio del modelo.
    lof = LocalOutlierFactor(n_neighbors=20, novelty=True,
                             contamination=0.05).fit(Xtr)
    ell = EllipticEnvelope(contamination=0.05, random_state=SEED).fit(Xtr)
    iso = art["modelo"]  # ya entrenado sobre el mismo espacio (VARIABLES_MODELO)
    log("Componentes entrenados: ISO (reusado), LOF, ELLIPTIC")

    # Umbrales de referencia del ensamble (media de z-scores).
    s_lof = lof.decision_function(Xtr)
    s_ell = ell.decision_function(Xtr)
    z = ((s_lof - s_lof.mean()) / (s_lof.std() + 1e-9)
         + (s_ell - s_ell.mean()) / (s_ell.std() + 1e-9)) / 2
    umbrales = {q: float(np.quantile(z, p))
                for q, p in (("q10", 0.10), ("q05", 0.05), ("q01", 0.01))}

    os.makedirs(DIR_PROD, exist_ok=True)
    joblib.dump(iso, os.path.join(DIR_PROD, "modelo_isolation_forest.joblib"))
    joblib.dump(lof, os.path.join(DIR_PROD, "modelo_lof.joblib"))
    joblib.dump(ell, os.path.join(DIR_PROD, "modelo_elliptic.joblib"))
    # Escalador completo (alineado con `features`): el detector lo indexa por
    # la posicion de cada variable del modelo dentro de esa lista.
    joblib.dump(art["scaler"], os.path.join(DIR_PROD, "scaler.joblib"))
    pd.DataFrame({"variable": columnas}).to_csv(
        os.path.join(DIR_PROD, "features_modelo.csv"), index=False)

    # pkl de train para que el detector calibre umbrales (features completas).
    with open(os.path.join(DIR_PROD, "dataset_muestras_train.pkl"), "wb") as f:
        pickle.dump({"features": features, "X": art["X_train"]}, f)

    meta = {
        "ensemble": "ENSEMBLE_LOF_ELL",
        "componentes": ["LOF", "ELLIPTIC"],
        "ventana": VENTANA,
        "n_features": len(columnas),
        "features": columnas,
        "umbrales": umbrales,
        "n_train": int(len(Xtr)),
    }
    with open(os.path.join(DIR_PROD, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    log(f"Bundle de producción: {DIR_PROD}")
    log(f"Umbrales LOF+ELL: {umbrales}")


if __name__ == "__main__":
    main()
