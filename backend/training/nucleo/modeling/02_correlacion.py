"""
02_correlacion.py
=================

Análisis de correlación combinado con la selección de variables
principales (fase de "reglas de motor / alertas"):

    1. Calcula matrices Pearson y Spearman sobre las corridas de
       ENTRENAMIENTO (referencia normal).
    2. Reporta pares con correlación >= UMBRAL_CORRELACION.
    3. Poda iterativa: elimina la variable más correlacionada con
       el resto en cada paquete redundante.
    4. Calcula VIF (variance inflation factor) de las variables
       mantenidas incluyendo intercepto OLS estándar.
    5. Genera reglas de umbral (p90/p95/p99) por variable para el
       motor de alertas.

Salidas (en <OUTPUT>/modelado/correlacion/):
    variables_correlacion.csv
    variables_correlacion_descartadas.csv
    features_modelo.csv
    vif_variables.csv
    reglas_umbrales.csv
"""

import os

import numpy as np
import pandas as pd

import config
import util_normalizacion


def log(msg):
    print(f"[CORRELACION] {msg}", flush=True)


def reporte_pares(corr_pearson, corr_spearman, umbral):
    """
    Lista los pares de variables con correlación >= umbral.
    """

    vars_ = list(corr_pearson.columns)

    filas = []

    # Recorremos solo la "mitad superior" de la matriz de correlación
    # (i < j) para no reportar el mismo par dos veces. Un par cuenta si
    # CUALQUIERA de las dos medidas (Pearson o Spearman) supera el
    # umbral: Pearson captura lo lineal y Spearman lo monótono.
    for i in range(len(vars_)):

        for j in range(i + 1, len(vars_)):

            a = vars_[i]
            b = vars_[j]

            rp = corr_pearson.loc[a, b]
            rs = corr_spearman.loc[a, b]

            if abs(rp) >= umbral or abs(rs) >= umbral:

                filas.append({
                    "var_a": a,
                    "var_b": b,
                    "pearson": round(rp, 4),
                    "spearman": round(rs, 4),
                    "involucrada": "",
                })

    return pd.DataFrame(filas)


def podar_redundantes(corr_pearson, umbral, df_pares):
    """
    Poda iterativa: mientras exista un par correlacionado,
    elimina la variable con mayor correlación promedio con
    el resto.
    """

    vars_ = set(corr_pearson.columns)

    descartadas = []

    while True:

        activas = sorted(vars_)

        sub = corr_pearson.loc[activas, activas]

        mat = sub.to_numpy().astype(float)

        np.fill_diagonal(mat, 0.0)

        pares = [
            (a, b, sub.loc[a, b])
            for i, a in enumerate(activas)
            for j, b in enumerate(activas)
            if j > i and abs(sub.loc[a, b]) >= umbral
        ]

        if not pares:
            break

        media_abs = {
            a: float(np.abs(mat[i]).mean())
            for i, a in enumerate(activas)
        }

        involucradas = sorted({
            c
            for p in pares
            for c in (p[0], p[1])
        })

        peor = max(
            involucradas,
            key=lambda c: (media_abs[c], c)
        )

        descartadas.append({
            "columna": peor,
            "motivo": (
                f"correlación >= {umbral} con "
                f"{[p[1] if p[0] == peor else p[0] for p in pares if peor in (p[0], p[1])]}"
            ),
            "media_abs_corr": round(media_abs[peor], 4),
        })

        vars_.discard(peor)

    return sorted(vars_), descartadas


def vif(df):
    """
    Variance Inflation Factor por variable mediante regresión
    lineal múltiple con intercepto (1 / (1 - R^2)).
    """

    cols = list(df.columns)

    n, p = df.shape

    resultado = {}

    if p <= 1:
        return {c: 1.0 for c in cols}

    Xn = df.to_numpy().astype(float)

    for k, objetivo in enumerate(cols):

        y = Xn[:, k]

        # Matriz de predictores excluyendo la variable objetivo
        X_otros = np.column_stack(
            [Xn[:, j] for j in range(p) if j != k]
        )

        # Incorporar columna de unos para el intercepto OLS estándar
        X_otros_const = np.column_stack(
            [np.ones(n), X_otros]
        )

        beta, *_ = np.linalg.lstsq(
            X_otros_const, y, rcond=None
        )

        y_pred = X_otros_const @ beta

        ss_res = float(np.sum((y - y_pred) ** 2))

        ss_tot = float(np.sum((y - y.mean()) ** 2))

        r2 = 1.0 - (ss_res / ss_tot if ss_tot else 0.0)

        resultado[objetivo] = round(
            1.0 / (1.0 - r2)
            if r2 < 1.0
            else np.inf,
            2
        )

    return resultado


def main():

    if not os.path.exists(config.DATASET_PRINCIPALES):

        log(
            f"Falta el dataset: {config.DATASET_PRINCIPALES}."
        )

        return

    datos = pd.read_csv(
        config.DATASET_PRINCIPALES,
        encoding="utf-8-sig"
    )

    features = [
        c
        for c in datos.columns
        if c not in config.COLUMNAS_CONTEXTO
    ]

    train = datos.copy()

    if config.NORMALIZACION_RELATIVA:

        train = util_normalizacion.transformar_relativo(
            train, features
        )

        log(
            "Normalización RELATIVA por corrida aplicada "
            "(baseline interno por corrida)"
        )

    df_num = train[features].apply(
        pd.to_numeric,
        errors="coerce"
    ).fillna(0)

    log(
        f"Muestras de entrenamiento para correlación: {len(df_num)}"
    )

    corr_pearson = df_num.corr(method="pearson")

    corr_spearman = df_num.corr(method="spearman")

    # --------------------------------------------------------
    # 1. REPORTE DE PARES
    # --------------------------------------------------------

    df_pares = reporte_pares(
        corr_pearson,
        corr_spearman,
        config.UMBRAL_CORRELACION
    )

    os.makedirs(config.DIR_CORRELACION, exist_ok=True)

    ruta_pares = os.path.join(
        config.DIR_CORRELACION,
        "variables_correlacion.csv"
    )

    df_pares.to_csv(
        ruta_pares,
        index=False,
        encoding="utf-8-sig"
    )

    log(
        f"Pares con |correlación| >= {config.UMBRAL_CORRELACION}: "
        f"{len(df_pares)}"
    )

    log(f"Reporte en: {ruta_pares}")

    # --------------------------------------------------------
    # 2. PODA ITERATIVA
    # --------------------------------------------------------

    mantenidas, descartadas = podar_redundantes(
        corr_pearson,
        config.UMBRAL_CORRELACION,
        df_pares
    )

    log(
        f"Variables mantenidas: {len(mantenidas)} / {len(features)}"
    )

    ruta_mant = os.path.join(
        config.DIR_CORRELACION,
        "features_modelo.csv"
    )

    pd.DataFrame(
        [{"columna": c} for c in mantenidas]
    ).to_csv(ruta_mant, index=False, encoding="utf-8-sig")

    log(f"Features de modelo en: {ruta_mant}")

    if descartadas:

        df_desc = pd.DataFrame(descartadas)

        ruta_desc = os.path.join(
            config.DIR_CORRELACION,
            "variables_correlacion_descartadas.csv"
        )

        df_desc.to_csv(
            ruta_desc,
            index=False,
            encoding="utf-8-sig"
        )

        log(
            f"Poda por correlación en: {ruta_desc} "
            f"({len(df_desc)})"
        )

    # --------------------------------------------------------
    # 3. VIF
    # --------------------------------------------------------

    vifs = vif(df_num[mantenidas])

    df_vif = pd.DataFrame(
        [{"columna": c, "vif": vifs[c]} for c in mantenidas]
    ).sort_values("vif", ascending=False)

    ruta_vif = os.path.join(
        config.DIR_CORRELACION,
        "vif_variables.csv"
    )

    df_vif.to_csv(
        ruta_vif,
        index=False,
        encoding="utf-8-sig"
    )

    log(f"VIF en: {ruta_vif}")

    # --------------------------------------------------------
    # 4. REGLAS DE UMBRAL (motor de alertas)
    # --------------------------------------------------------

    df_reglas = pd.DataFrame({
        "columna": mantenidas,
        "p90": np.percentile(df_num[mantenidas], 90, axis=0),
        "p95": np.percentile(df_num[mantenidas], 95, axis=0),
        "p99": np.percentile(df_num[mantenidas], 99, axis=0),
    })

    ruta_reglas = os.path.join(
        config.DIR_CORRELACION,
        "reglas_umbrales.csv"
    )

    df_reglas.to_csv(
        ruta_reglas,
        index=False,
        encoding="utf-8-sig"
    )

    log(f"Reglas de umbral (referencia normal) en: {ruta_reglas}")

    # --------------------------------------------------------
    # 5. RESUMEN
    # --------------------------------------------------------

    print("\n=== PARES CORRELACIONADOS ===")

    if df_pares.empty:

        print(
            f"No hay pares con |correlación| >= "
            f"{config.UMBRAL_CORRELACION}"
        )

    else:

        print(
            df_pares.to_string(index=False)
        )

    print("\n=== VARIABLES MANTENIDAS ===")

    print(
        df_vif.to_string(index=False)
    )

    print("\n=== DESCARTADAS POR REDUNDANCIA ===")

    if descartadas:

        print(
            pd.DataFrame(descartadas).to_string(index=False)
        )

    print("\n=== REGLAS (REFERENCIA NORMAL) ===")

    print(
        df_reglas.to_string(index=False)
    )


if __name__ == "__main__":
    main()