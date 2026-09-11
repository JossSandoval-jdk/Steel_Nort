"""
util_normalizacion.py
=====================

Normalización RELATIVA por corrida.

Cada corrida define su propio baseline (media/desviación por
variable) y las muestras se expresan como desviaciones respecto
a ese baseline interno:

    valor_relativo = (valor - media_run) / desviacion_run

Esto elimina la deriva de entorno entre corridas (niveles,
concurrencia, versión de captura, incidencias de red, etc.) y
deja que el detector mida la FORMA/DINÁMICA dentro de cada
corrida, que es donde se manifiesta una anomalía OLTP.

Las variables constantes dentro de una corrida se dejan en 0
(no aportan variación).
"""

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------
# CONSTANTES
# ---------------------------------------------------------------------
# Si la desviación de una variable dentro de una corrida es menor que
# EPS, la tratamos como CONSTANTE → no puede ser anomalía → se deja en 0.
EPS = 1e-12


def transformar_relativo(datos, features):
    """
    Devuelve una copia de `datos` con las columnas `features`
    reemplazadas por su desviación relativa al baseline interno
    de la corrección correspondiente.
    """

    out = datos.copy()

    # -----------------------------------------------------------------
    # Haz del screener: asegurar que todas las variables sean float64.
    # -----------------------------------------------------------------
    # Sin esto, pandas no permite escribir valores decimales (el resultado
    # del z-score) en columnas que se leyeron como int (p. ej. lock_waits
    # que vale 0 durante toda una corrida se infiere como int64).
    for feature in features:
        out[feature] = pd.to_numeric(
            out[feature], errors="coerce"
        ).astype("float64")

    # -----------------------------------------------------------------
    # BASELINE INTERNO POR CORRIDA
    # -----------------------------------------------------------------
    # Cada corrida define su propia media/desviación. Una corrida con
    # concurrencia 50 NO se compara contra una con concurrencia 10:
    # cada una se mide contra su propia "normalidad".
    for run in out["run_name"].unique():

        ix = out["run_name"] == run

        for feature in features:

            valores = (
                pd.to_numeric(
                    out.loc[ix, feature],
                    errors="coerce"
                )
            )

            # Estadísticos del baseline interno de la corrida.
            media = float(valores.mean())

            desviacion = float(valores.std())

            # Media no finita → la variable es todo NaN en esta corrida.
            # No hay información: se asigna 0 (no se puede evaluar variación).
            if not np.isfinite(media):
                out.loc[ix, feature] = 0.0
                continue

            # Desviación nula → variable constante dentro de la corrida.
            # Dividir por 0 rompería, y además una constante no puede ser
            # anomalía → se deja en 0 también.
            if desviacion < EPS:
                out.loc[ix, feature] = 0.0
                continue

            # z-score interno: (valor − media)/desviación. El 0 es el
            # centro de la corrida; los valores grandes = desviación.
            out.loc[ix, feature] = (
                (valores - media) / desviacion
            ).fillna(0.0)

    return out