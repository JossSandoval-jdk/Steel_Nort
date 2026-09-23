"""
util_normalizacion.py
=====================

Normalización RELATIVA por corrida utilizando estadística robusta.

Cada corrida define su propio baseline (mediana/MAD por variable)
y las muestras se expresan como desviaciones robustas respecto
a ese baseline interno:

    valor_relativo = (valor - mediana_run) / escala_mad_run

Esto elimina la deriva de entorno entre corridas y evita que
las anomalías extremas contaminen el baseline (a diferencia de
la media y la desviación estándar tradicionales).
"""

import numpy as np
import pandas as pd

CONSTANTE_MAD = 1.4826
EPS = 1e-12

def transformar_relativo(datos, features):
    """
    Devuelve una copia de `datos` con las columnas `features`
    reemplazadas por su desviación robusta al baseline interno
    de la corrida correspondiente (vectorizado).
    """
    out = dataset_copia = datos.copy()

    for feature in features:
        out[feature] = pd.to_numeric(
            out[feature], errors="coerce"
        ).astype("float64")

    sub_df = out[features]

    medianas = out.groupby("run_name")[features].transform("median")

    abs_dev = (sub_df - medianas).abs()
    mads = abs_dev.groupby(out["run_name"]).transform("median")

    escala = CONSTANTE_MAD * mads + EPS

    normalizado = (sub_df - medianas) / escala

    normalizado = normalizado.fillna(0.0)
    normalizado = normalizado.mask(mads < EPS, 0.0)

    out[features] = normalizado

    return out
