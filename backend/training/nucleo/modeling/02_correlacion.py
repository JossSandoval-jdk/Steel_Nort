"""
02_correlacion.py
=================

Análisis de correlación + selección de variables y reglas de referencia
normal para el motor de alertas:

    1. Matrices Pearson y Spearman sobre las CORRIDAS DE ENTRENAMIENTO
       (referencia normal).
    2. Pares con |correlación| >= UMBRAL_CORRELACION.
    3. Poda automática de redundancias (recomendación) que valida la
       lista VARIABLES_MODELO de config.
    4. VIF de las variables del modelo (colinealidad remanente).
    5. Reglas de referencia normal (p90/p95/p99) por variable.

Salidas (en <OUTPUT>/modelado/correlacion/):
    variables_correlacion.csv
    features_modelo.csv
    poda_recomendada.csv
    vif_variables.csv
    reglas_umbrales.csv
    corridas_referencia_normal.csv
"""

import os

import numpy as np
import pandas as pd

import config
import util_normalizacion


def log(msg):
    print(f"[CORRELACION] {msg}", flush=True)


def reporte_pares(corr_pearson, corr_spearman, umbral):
    """Pares (arriba de la diagonal) con |correlación| >= umbral."""
    vars_ = list(corr_pearson.columns)
    filas = [
        {"var_a": a, "var_b": b,
         "pearson": round(corr_pearson.loc[a, b], 4),
         "spearman": round(corr_spearman.loc[a, b], 4)}
        for i, a in enumerate(vars_)
        for j, b in enumerate(vars_)
        if j > i
        and (abs(corr_pearson.loc[a, b]) >= umbral
             or abs(corr_spearman.loc[a, b]) >= umbral)
    ]
    return pd.DataFrame(filas)


def podar_redundantes(corr_pearson, umbral):
    """Poda iterativa: mientras exista un par con |r| >= umbral, elimina
    la variable con mayor correlación promedio con el resto.
    Devuelve (mantenidas_auto, descartadas)."""
    activas = list(corr_pearson.columns)
    descartadas = []

    while True:
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

        media_abs = {a: float(np.nanmean(np.abs(mat[i])))
                     for i, a in enumerate(activas)}
        involucradas = sorted({c for p in pares for c in (p[0], p[1])})
        peor = max(involucradas, key=lambda c: (media_abs[c], c))

        descartadas.append({
            "columna": peor,
            "motivo": (f"correlación >= {umbral} con "
                       f"{[p[1] if p[0] == peor else p[0]
                            for p in pares if peor in (p[0], p[1])]}"),
            "media_abs_corr": round(media_abs[peor], 4),
        })
        activas.remove(peor)

    return sorted(activas), descartadas


def vif(df):
    """VIF por variable: 1 / (1 - R²) regresando la variable contra el
    resto (con intercepto). >10 = colinealidad fuerte."""
    cols = list(df.columns)
    n, p = df.shape
    if p <= 1:
        return {c: 1.0 for c in cols}

    Xn = df.to_numpy().astype(float)
    resultado = {}
    for k, objetivo in enumerate(cols):
        y = Xn[:, k]
        X_otros = np.column_stack([Xn[:, j] for j in range(p) if j != k])
        X_otros = np.column_stack([np.ones(n), X_otros])
        beta, *_ = np.linalg.lstsq(X_otros, y, rcond=None)
        ss_res = float(np.sum((y - X_otros @ beta) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - (ss_res / ss_tot if ss_tot else 0.0)
        resultado[objetivo] = round(1.0 / (1.0 - r2) if r2 < 1.0 else np.inf, 2)
    return resultado


def mostrar(titulo, df=None, texto=None):
    print(f"\n=== {titulo} ===")
    print(df.to_string(index=False) if df is not None else texto)


def main():
    if not os.path.exists(config.DATASET_PRINCIPALES):
        log(f"Falta el dataset: {config.DATASET_PRINCIPALES}.")
        return

    datos = pd.read_csv(config.DATASET_PRINCIPALES, encoding="utf-8-sig")
    features = [c for c in datos.columns if c not in config.COLUMNAS_CONTEXTO]

    corridas_sanas = config.corridas_entrenamiento(datos["run_name"])
    train = datos[datos["run_name"].isin(corridas_sanas)].copy()
    if config.NORMALIZACION_RELATIVA:
        train = util_normalizacion.transformar_relativo(train, features)

    df_num = train[features].apply(pd.to_numeric,
                                   errors="coerce").fillna(0)
    log(f"Referencia NORMAL ({len(train)} filas): {corridas_sanas}")

    corr_pearson = df_num.corr(method="pearson")
    corr_spearman = df_num.corr(method="spearman")

    df_pares = reporte_pares(corr_pearson, corr_spearman,
                             config.UMBRAL_CORRELACION)
    os.makedirs(config.DIR_CORRELACION, exist_ok=True)

    ruta = lambda nombre: os.path.join(config.DIR_CORRELACION, nombre)
    df_pares.to_csv(ruta("variables_correlacion.csv"),
                    index=False, encoding="utf-8-sig")
    log(f"Pares con |correlación| >= {config.UMBRAL_CORRELACION}: "
        f"{len(df_pares)}")

    mantenidas = [c for c in config.VARIABLES_MODELO if c in features]
    log(f"Variables del modelo: {len(mantenidas)} / {len(features)}")
    pd.DataFrame([{"columna": c} for c in mantenidas]).to_csv(
        ruta("features_modelo.csv"), index=False, encoding="utf-8-sig")

    mantenidas_auto, descartadas_auto = podar_redundantes(
        corr_pearson, config.UMBRAL_CORRELACION)
    if descartadas_auto:
        pd.DataFrame(descartadas_auto).to_csv(
            ruta("poda_recomendada.csv"), index=False, encoding="utf-8-sig")

    auto = {d["columna"] for d in descartadas_auto}
    conflictos = sorted(auto & set(mantenidas))
    sugerencias = sorted(auto - set(features) - set(mantenidas))
    if conflictos:
        log(f"VALIDACIÓN: la poda automática descartaría variables que "
            f"VARIABLES_MODELO conserva -> {conflictos}. Revisar.")
    if sugerencias:
        log(f"VALIDACIÓN: la poda automática sugiere descartar también -> "
            f"{sugerencias}")
    if not conflictos and not sugerencias:
        log("VALIDACIÓN OK: la poda automática coincide con VARIABLES_MODELO.")

    vifs = vif(df_num[mantenidas])
    df_vif = pd.DataFrame(
        [{"columna": c, "vif": vifs[c]} for c in mantenidas]
    ).sort_values("vif", ascending=False)
    df_vif.to_csv(ruta("vif_variables.csv"),
                  index=False, encoding="utf-8-sig")
    colineales = df_vif.loc[df_vif["vif"] > 10, "columna"].tolist()
    if colineales:
        log(f"Colinealidad alta (VIF>10): {colineales}")

    df_reglas = pd.DataFrame({
        "columna": mantenidas,
        "p90": np.percentile(df_num[mantenidas], 90, axis=0),
        "p95": np.percentile(df_num[mantenidas], 95, axis=0),
        "p99": np.percentile(df_num[mantenidas], 99, axis=0),
    })
    df_reglas.to_csv(ruta("reglas_umbrales.csv"),
                     index=False, encoding="utf-8-sig")

    pd.DataFrame([{"run_name": c} for c in corridas_sanas]).to_csv(
        ruta("corridas_referencia_normal.csv"),
        index=False, encoding="utf-8-sig")

    mostrar("PARES CORRELACIONADOS", df_pares if len(df_pares) else None,
            f"No hay pares con |correlación| >= {config.UMBRAL_CORRELACION}")
    mostrar("VARIABLES MANTENIDAS (VIF)", df_vif)
    mostrar("PODA AUTOMÁTICA (RECOMENDACIÓN)",
            pd.DataFrame(descartadas_auto) if descartadas_auto else None,
            f"No hay variables descartables (|r| < {config.UMBRAL_CORRELACION})")
    mostrar("REGLAS (REFERENCIA NORMAL)", df_reglas)


if __name__ == "__main__":
    main()