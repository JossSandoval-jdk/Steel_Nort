"""
05_seleccion_variables_clave.py
================================

Paso 5 de la preparación de datos (CRISP-DM):
Selección de variables clave.

El dataset integrado contiene todas las variables candidatas. En esta etapa
se seleccionan las variables que presentan suficiente calidad y variabilidad
para ser utilizadas posteriormente durante el Modelado.

IMPORTANTE:
    - No existe una "carga normal" de referencia.
    - No se utiliza CORRIDAS_CARGA_NORMAL.
    - No se etiqueta ninguna anomalía.
    - No se genera is_anomaly.
    - La selección se realiza sobre TODAS las cargas disponibles.
    - Cada corrida conserva su run_name y experiment_id.

Criterios de selección:

    1. La variable debe existir en el dataset integrado.
    2. El porcentaje de NaN debe ser <= UMBRAL_NAV.
    3. Debe tener al menos MIN_UNICOS valores distintos.
    4. No debe corresponder a una medición declarada corrupta.

Salidas:

    datasets/integrado/variables_clave.csv
    datasets/integrado/dataset_steelnort_preparado_modelo.csv
"""


import os

import numpy as np
import pandas as pd

import config


# ============================================================
# LOG
# ============================================================

def log(msg):
    print(f"[CLAVE] {msg}", flush=True)


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # 1. LOCALIZAR DATASET INTEGRADO
    # --------------------------------------------------------

    ruta_integrado = os.path.join(
        config.DIR_INTEGRADO,
        config.ARCHIVO_DATASET_INTEGRADO
    )

    if not os.path.exists(ruta_integrado):

        log(
            f"Falta el dataset integrado: "
            f"{ruta_integrado}. Ejecuta 04_integracion.py."
        )

        return

    # --------------------------------------------------------
    # 2. CARGAR DATASET
    # --------------------------------------------------------

    df = pd.read_csv(
        ruta_integrado,
        encoding="utf-8-sig"
    )

    if df.empty:

        log(
            "El dataset integrado está vacío."
        )

        return

    log(
        f"Dataset integrado cargado: "
        f"{len(df)} filas x {df.shape[1]} columnas"
    )

    # --------------------------------------------------------
    # 3. VARIABLES CANDIDATAS
    # --------------------------------------------------------

    feats = config.columnas_features()

    log(
        f"Variables candidatas: {len(feats)}"
    )

    # --------------------------------------------------------
    # 4. EVALUAR CADA VARIABLE
    # --------------------------------------------------------

    filas = []

    n = len(df)

    for col in feats:

        # ----------------------------------------------------
        # VARIABLE NO PRESENTE
        # ----------------------------------------------------

        if col not in df.columns:

            filas.append({

                "columna": col,

                "presente": False,

                "senal": "NO_PRESENTE",

                "nulos_pct": np.nan,

                "unicos": 0,

                "media": np.nan,

                "decision_modelo": "ELIMINAR",

                "motivo_decision":
                    "variable no presente en el dataset integrado"
            })

            continue

        # ----------------------------------------------------
        # DATOS DE LA VARIABLE
        # ----------------------------------------------------

        s = pd.to_numeric(
            df[col],
            errors="coerce"
        )

        nulos_pct = round(
            float(
                s.isna().mean() * 100
            ),
            2
        )

        unicos = int(
            s.nunique(
                dropna=True
            )
        )

        no_nulos = s.dropna()

        media = (
            round(
                float(
                    no_nulos.mean()
                ),
                4
            )
            if len(no_nulos)
            else np.nan
        )

        # ----------------------------------------------------
        # MEDICIÓN CORRUPTA
        # ----------------------------------------------------

        if col in config.EXCLUIR_MEDICION_CORRUPTA:

            senal = "DESCARTADA_MEDICION"

            decision = "ELIMINAR"

            motivo = (
                "medición no confiable o incorrecta "
                "en el collector"
            )

        # ----------------------------------------------------
        # DEMASIADOS NaN
        # ----------------------------------------------------

        elif nulos_pct > config.UMBRAL_NAV:

            senal = "MUCHO_NAN"

            decision = "ELIMINAR"

            motivo = (
                "supera el límite permitido de "
                "valores NaN"
            )

        # ----------------------------------------------------
        # VARIABLE CONSTANTE
        # ----------------------------------------------------

        elif unicos < config.MIN_UNICOS:

            senal = "CONSTANTE"

            decision = "ELIMINAR"

            if unicos == 0:

                motivo = (
                    "no contiene valores válidos"
                )

            elif float(
                no_nulos.iloc[0]
            ) == 0:

                motivo = (
                    "todos los valores disponibles "
                    "son 0"
                )

            else:

                motivo = (
                    "presenta un único valor constante"
                )

        # ----------------------------------------------------
        # VARIABLE CLAVE
        # ----------------------------------------------------

        else:

            senal = "CLAVE"

            decision = "MANTENER"

            if nulos_pct > 0:

                motivo = (
                    "senal suficiente; contiene algunos "
                    "NaN que pueden corresponder a "
                    "muestras iniciales o datos faltantes"
                )

            else:

                motivo = (
                    "variabilidad y disponibilidad "
                    "suficientes para el modelado"
                )

        # ----------------------------------------------------
        # REGISTRO
        # ----------------------------------------------------

        filas.append({

            "columna": col,

            "presente": True,

            "senal": senal,

            "nulos_pct": nulos_pct,

            "unicos": unicos,

            "media": media,

            "decision_modelo": decision,

            "motivo_decision": motivo
        })

    # --------------------------------------------------------
    # 5. DATAFRAME DE SELECCIÓN
    # --------------------------------------------------------

    df_selec = pd.DataFrame(
        filas
    )

    # --------------------------------------------------------
    # 6. GUARDAR TRAZABILIDAD
    # --------------------------------------------------------

    os.makedirs(
        config.DIR_INTEGRADO,
        exist_ok=True
    )

    ruta_var = os.path.join(
        config.DIR_INTEGRADO,
        config.ARCHIVO_VARIABLES_CLAVE
    )

    df_selec.to_csv(
        ruta_var,
        index=False,
        encoding="utf-8-sig"
    )

    log(
        f"Selección de variables en: "
        f"{ruta_var}"
    )

    # --------------------------------------------------------
    # 7. OBTENER VARIABLES CLAVE
    # --------------------------------------------------------

    clave = (
        df_selec[
            df_selec["senal"] == "CLAVE"
        ]["columna"]
        .tolist()
    )

    mantener = (
        df_selec[
            df_selec["decision_modelo"] == "MANTENER"
        ]["columna"]
        .tolist()
    )

    log(
        f"Variables clave: "
        f"{len(clave)} de {len(feats)}"
    )

    # --------------------------------------------------------
    # 8. DATASET PARA MODELADO
    # --------------------------------------------------------

    # Las variables seleccionadas se conservan junto con
    # timestamp e identificación de la corrida.

    columnas_contexto = config.columnas_contexto()

    cols_modelo = (
        ["timestamp"]
        + mantener
        + columnas_contexto
    )

    # Evitar columnas duplicadas.
    cols_modelo = list(
        dict.fromkeys(cols_modelo)
    )

    # Verificar que todas existan.
    cols_modelo = [
        col
        for col in cols_modelo
        if col in df.columns
    ]

    df_modelo = df[
        cols_modelo
    ].copy()

    ruta_modelo = os.path.join(
        config.DIR_INTEGRADO,
        config.ARCHIVO_DATASET_MODELO
    )

    df_modelo.to_csv(
        ruta_modelo,
        index=False,
        encoding="utf-8-sig"
    )

    log(
        f"Dataset para modelado en: "
        f"{ruta_modelo} "
        f"({df_modelo.shape[0]} filas x "
        f"{df_modelo.shape[1]} cols)"
    )

    # --------------------------------------------------------
    # 9. RESUMEN
    # --------------------------------------------------------

    print(
        "\n=== VARIABLES CLAVE ==="
    )

    if clave:

        print(
            df_selec[
                df_selec["senal"] == "CLAVE"
            ][
                [
                    "columna",
                    "nulos_pct",
                    "unicos",
                    "media"
                ]
            ].to_string(
                index=False
            )
        )

    else:

        print(
            "No se encontraron variables clave."
        )

    # --------------------------------------------------------
    # 10. VARIABLES DESCARTADAS
    # --------------------------------------------------------

    descartadas = (
        len(df_selec) - len(clave)
    )

    print(
        f"\n=== VARIABLES DESCARTADAS "
        f"({descartadas}) ==="
    )

    print(
        df_selec
        .groupby("senal")
        .size()
        .to_string()
    )

    # --------------------------------------------------------
    # 11. RESUMEN POR DECISIÓN
    # --------------------------------------------------------

    print(
        "\n=== DECISIONES PARA MODELADO ==="
    )

    print(
        df_selec
        .groupby("decision_modelo")
        .size()
        .to_string()
    )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()