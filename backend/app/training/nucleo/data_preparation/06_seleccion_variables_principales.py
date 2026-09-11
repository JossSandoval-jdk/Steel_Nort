"""
06_seleccion_variables_principales.py
=====================================
Paso 6 de la preparación de datos (CRISP-DM): selección final de las
variables PRINCIPALES (expert-driven por dominio de rendimiento).

Parte de las variables que pasaron el filtro de señal (variables_clave.csv)
y las reduce a las MÁS IMPORTANTES y ESENCIALES para:
  * detección de anomalías de rendimiento (aislar desviaciones),
  * diagnóstico de apoyo (qué variables explican "por qué" es anómalo),
  * análisis de correlación y reglas de motor (alertas).

Clasificaciones soportadas por config.py (config canónico reescrito):

    - VARIABLES_PRINCIPALES
    - VARIABLES_DIAGNOSTICO
    - VARIABLES_REDUNDANTES
    - VARIABLES_REQUIEREN_CORRECCION
    - EXCLUIR_MEDICION_CORRUPTA

IMPORTANTE:
    - No existe una "carga normal" de referencia (CORRIDAS_CARGA_NORMAL
      fue removida del config).
    - No se etiqueta ninguna anomalía ni se genera is_anomaly.
    - El dataset final se construye sobre TODAS las corridas disponibles.

Salidas:
    datasets/integrado/variables_principales.csv
        (justificación trazable de cada variable principal)
    datasets/integrado/variables_principales_descartadas.csv
        (trazabilidad de variables que pasaron la señal pero no son
        principales, más las excluidas por medición incorrecta)
    datasets/integrado/dataset_carga_principales.csv
        (solo variables principales + contexto)
"""


import os

import pandas as pd

import config


def log(msg):
    print(f"[PRINCIPALES] {msg}", flush=True)


# ============================================================
# CLASIFICACIÓN CANÓNICA
# ============================================================

def clasificar(columna):
    """
    Devuelve la clasificación canónica de una variable según
    los conjuntos definidos en config.py.
    """

    if columna in config.EXCLUIR_MEDICION_CORRUPTA:
        return "excluida"

    if columna in config.VARIABLES_PRINCIPALES:
        return "principal"

    if columna in config.VARIABLES_REDUNDANTES:
        return "redundante"

    if columna in config.VARIABLES_REQUIEREN_CORRECCION:
        return "requiere_correccion"

    if columna in config.VARIABLES_DIAGNOSTICO:
        return "diagnostico"

    return "disponible"


def metadatos_variable(columna):
    """
    Recupera dominio, tipo y descripción de la variable desde el
    inventario canónico FEATURES_SELECCIONADAS.
    """

    for f in config.FEATURES_SELECCIONADAS:

        if f["columna"] == columna:

            return {
                "fuente": f.get("fuente", ""),
                "dominio": f.get("dominio", ""),
                "tipo": f.get("tipo", ""),
                "descripcion": f.get("descripcion", ""),
            }

    return {
        "fuente": "",
        "dominio": "",
        "tipo": "",
        "descripcion": "",
    }


# ============================================================
# CATÁLOGO DE VARIABLES PRINCIPALES
# ============================================================

def construir_catalogo_principales():
    """
    Construye variables_principales.csv con trazabilidad
    (dominio, tipo, descripcion) para cada variable principal.
    """

    filas = []

    for columna in config.VARIABLES_PRINCIPALES:

        meta = metadatos_variable(columna)

        filas.append({
            "columna": columna,
            "clasificacion": "principal",
            "fuente": meta["fuente"],
            "dominio": meta["dominio"],
            "tipo": meta["tipo"],
            "descripcion": meta["descripcion"],
        })

    return pd.DataFrame(filas)


# ============================================================
# DESCARTES TRAZABLES
# ============================================================

def construir_descartes():
    """
    Construye variables_principales_descartadas.csv.

    Incluye dos grupos:

        1. Variables que pasaron el filtro de señal (CLAVE en
           variables_clave.csv) pero NO son principales.
        2. Variables excluidas por medición incorrecta en el
           collector, aunque no hayan pasado el filtro de señal.
    """

    ruta_clave = os.path.join(
        config.DIR_INTEGRADO,
        config.ARCHIVO_VARIABLES_CLAVE
    )

    if not os.path.exists(ruta_clave):
        log(f"Falta {ruta_clave}. Ejecuta 05_seleccion_variables_clave.py.")
        return None

    clave = pd.read_csv(
        ruta_clave,
        encoding="utf-8-sig"
    )

    columnas_clave = set(
        clave[
            clave["senal"] == "CLAVE"
        ]["columna"]
    )

    principales = set(
        config.VARIABLES_PRINCIPALES
    )

    filas = []

    # --------------------------------------------------------
    # Grupo 1: señal CLAVE pero no principal
    # --------------------------------------------------------

    for columna in sorted(columnas_clave - principales):

        clasificacion = clasificar(columna)

        filas.append({
            "columna": columna,
            "clasificacion": clasificacion,
            "motivo": (
                "supera el filtro de señal pero no forma "
                "parte del conjunto principal"
            ),
            "detalle": (
                "usada para diagnóstico o descartada por "
                "redundancia/dominio"
                if clasificacion == "diagnostico"
                else "redundante o de menor relevancia "
                     "para el modelo de anomalías"
            ),
        })

    # --------------------------------------------------------
    # Grupo 2: exclusión por medición incorrecta
    # --------------------------------------------------------

    for columna in sorted(
        set(config.EXCLUIR_MEDICION_CORRUPTA) - principales
    ):

        filas.append({
            "columna": columna,
            "clasificacion": "excluida",
            "motivo": "medición no confiable o incorrecta en el collector",
            "detalle": "",
        })

    return pd.DataFrame(filas)


# ============================================================
# DATASET FINAL DE VARIABLES PRINCIPALES
# ============================================================

def construir_dataset_principales(df):
    """
    Devuelve un dataset con solo las variables principales
    más las columnas de contexto disponibles.

    La base es el dataset para modelado generado por 05.

    Limpieza del dataset final:
        1. Se descartan variables principales 100% vacías
           (el collector nunca generó esa métrica).
        2. Los NaN residuales (muestras iniciales sin delta)
           se rellenan con 0.
    """

    columnas = [
        "timestamp"
    ] + config.columnas_principales()

    columnas_contexto = [
        c
        for c in config.columnas_contexto()
        if c in df.columns
    ]

    columnas_final = list(
        dict.fromkeys(
            columnas + columnas_contexto
        )
    )

    df_final = df.copy()

    for col in columnas_final:

        if col not in df_final.columns:
            df_final[col] = pd.NA

    # --------------------------------------------------------
    # Descartar variables principales sin datos
    # --------------------------------------------------------

    vacias = [
        col
        for col in config.columnas_principales()
        if df_final[col].isna().all()
    ]

    if vacias:
        log(
            f"Variables principales descartadas (100% vacías): "
            f"{len(vacias)} -> {vacias}"
        )

    columnas_final = [
        col
        for col in columnas_final
        if col not in vacias
    ]

    df_final = df_final[columnas_final]

    # --------------------------------------------------------
    # Rellenar NaN residuales con 0
    # --------------------------------------------------------

    numericas = df_final.select_dtypes(
        include="number"
    ).columns

    df_final[numericas] = (
        df_final[numericas].fillna(0)
    )

    return df_final


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # 1. BASE: DATASET PARA MODELADO (05)
    # --------------------------------------------------------

    ruta_modelo = os.path.join(
        config.DIR_INTEGRADO,
        config.ARCHIVO_DATASET_MODELO
    )

    if not os.path.exists(ruta_modelo):
        log(
            f"Falta {ruta_modelo}. "
            "Ejecuta 05_seleccion_variables_clave.py."
        )
        return

    df = pd.read_csv(
        ruta_modelo,
        encoding="utf-8-sig"
    )

    if df.empty:
        log("El dataset para modelado está vacío.")
        return

    log(
        f"Dataset base cargado: "
        f"{len(df)} filas x {df.shape[1]} columnas"
    )

    # --------------------------------------------------------
    # 2. CATÁLOGO DE VARIABLES PRINCIPALES
    # --------------------------------------------------------

    df_vars = construir_catalogo_principales()

    ruta_vars = os.path.join(
        config.DIR_INTEGRADO,
        config.ARCHIVO_VARIABLES_PRINCIPALES
    )

    df_vars.to_csv(
        ruta_vars,
        index=False,
        encoding="utf-8-sig"
    )

    log(
        f"Selección en: {ruta_vars} "
        f"({len(df_vars)} variables)"
    )

    # --------------------------------------------------------
    # 3. DESCARTES TRAZABLES
    # --------------------------------------------------------

    df_desc = construir_descartes()

    if df_desc is not None and not df_desc.empty:

        ruta_desc = os.path.join(
            config.DIR_INTEGRADO,
            "variables_principales_descartadas.csv"
        )

        df_desc.to_csv(
            ruta_desc,
            index=False,
            encoding="utf-8-sig"
        )

        log(
            f"Descartes en: {ruta_desc} "
            f"({len(df_desc)} registros)"
        )

    # --------------------------------------------------------
    # 4. DATASET FINAL
    # --------------------------------------------------------

    df_final = construir_dataset_principales(
        df
    )

    ruta_ds = os.path.join(
        config.DIR_INTEGRADO,
        config.ARCHIVO_DATASET_PRINCIPALES
    )

    df_final.to_csv(
        ruta_ds,
        index=False,
        encoding="utf-8-sig"
    )

    log(
        f"Dataset de variables principales en: {ruta_ds} "
        f"({df_final.shape[0]} filas x {df_final.shape[1]} cols)"
    )

    # --------------------------------------------------------
    # 5. RESUMEN
    # --------------------------------------------------------

    print("\n=== VARIABLES PRINCIPALES FINALES ===")

    print(
        df_vars[
            ["columna", "dominio", "tipo"]
        ].to_string(index=False)
    )

    print(f"\nTotal principales: {len(df_vars)}")

    if df_desc is not None and not df_desc.empty:

        print("\n=== DESCARTADAS (por redundancia/diagnóstico) ===")

        print(
            df_desc[
                ["columna", "clasificacion", "motivo"]
            ].to_string(index=False)
        )


if __name__ == "__main__":
    main()