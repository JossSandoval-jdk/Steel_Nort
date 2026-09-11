"""
04_integracion.py
=================

Paso 4 de la preparación de datos (CRISP-DM): Integración.

Consolida las diferentes corridas/cargas ya transformadas en un único
dataset tabular.

Cada corrida es independiente y se conserva su identificación mediante:

    - run_name
    - experiment_id

IMPORTANTE:
    - No se etiqueta ninguna anomalía.
    - No existe una carga normal predefinida.
    - No se utiliza CORRIDAS_CARGA_NORMAL.
    - No se genera is_anomaly.
    - No se mezclan las corridas conceptualmente; solo se concatenan
      conservando su identificador.

Fuentes utilizadas:

    metrics.log
    events.log
    sqlserver_logs.log

Salidas:

    datasets/integrado/dataset_steelnort_preparado.csv
    datasets/integrado/dataset_eventos.csv
    datasets/integrado/dataset_logs.csv
    datasets/integrado/metadata_transformaciones.json
    datasets/integrado/reporte_calidad_datos.csv
"""

import json
import os

import numpy as np
import pandas as pd

import config


# ============================================================
# LOG
# ============================================================

def log(msg):
    print(f"[INTEGRACION] {msg}", flush=True)


# ============================================================
# CARGAR DATASETS TRANSFORMADOS
# ============================================================

def cargar_transformadas():
    """
    Carga el dataset transformado de cada corrida.

    Cada corrida tiene su propio archivo:

        DIR_LIMPIO/
        ├── carga_001/
        │   └── datos_transformados.csv
        ├── carga_002/
        │   └── datos_transformados.csv
        └── carga_003/
            └── datos_transformados.csv

    Devuelve una lista:

        [
            ("carga_001", df1),
            ("carga_002", df2),
            ...
        ]
    """

    if not os.path.isdir(config.DIR_LIMPIO):
        return []

    corridas = sorted([
        d
        for d in os.listdir(config.DIR_LIMPIO)
        if os.path.isdir(
            os.path.join(
                config.DIR_LIMPIO,
                d
            )
        )
        and os.path.exists(
            os.path.join(
                config.DIR_LIMPIO,
                d,
                config.NOMBRE_TRANSFORMADO
            )
        )
    ])

    out = []

    for corrida in corridas:

        ruta = os.path.join(
            config.DIR_LIMPIO,
            corrida,
            config.NOMBRE_TRANSFORMADO
        )

        try:

            df = pd.read_csv(
                ruta,
                encoding="utf-8-sig"
            )

            if df.empty:
                log(
                    f"   Advertencia: {corrida} "
                    f"tiene un dataset vacío."
                )
                continue

            if "timestamp" not in df.columns:
                log(
                    f"   Advertencia: {corrida} "
                    f"no contiene timestamp."
                )
                continue

            df["timestamp"] = pd.to_datetime(
                df["timestamp"],
                errors="coerce"
            )

            df = df.dropna(
                subset=["timestamp"]
            )

            if df.empty:
                log(
                    f"   Advertencia: {corrida} "
                    f"no tiene timestamps válidos."
                )
                continue

            out.append(
                (corrida, df)
            )

        except Exception as e:

            log(
                f"   ERROR leyendo {corrida}: {e}"
            )

    return out


# ============================================================
# CONSTRUIR DATASET INTEGRADO
# ============================================================

def construir_integrado(corridas):
    """
    Integra todas las corridas en un único DataFrame.

    Cada corrida conserva:

        run_name
        experiment_id

    No se genera ninguna etiqueta de normalidad ni anomalía.
    """

    frames = []

    feats = config.columnas_features()

    for idx, (corrida, df) in enumerate(corridas):

        d = df.copy()

        # ----------------------------------------------------
        # Asegurar columnas canónicas
        # ----------------------------------------------------

        for col in feats:

            if col not in d.columns:
                d[col] = np.nan

        # ----------------------------------------------------
        # Identificación de la corrida
        # ----------------------------------------------------

        d["run_name"] = corrida

        d["experiment_id"] = (
            f"exp_{idx + 1:02d}"
        )

        # ----------------------------------------------------
        # Orden final
        # ----------------------------------------------------

        orden = [
            "timestamp"
        ] + feats + [
            "run_name",
            "experiment_id",
        ]

        d = d[orden]

        frames.append(d)

    if not frames:
        return pd.DataFrame()

    # --------------------------------------------------------
    # Concatenar todas las corridas
    # --------------------------------------------------------

    df = pd.concat(
        frames,
        ignore_index=True,
        sort=False
    )

    # --------------------------------------------------------
    # Ordenar conservando independencia de cada corrida
    # --------------------------------------------------------

    df = df.sort_values(
        [
            "experiment_id",
            "timestamp"
        ]
    ).reset_index(
        drop=True
    )

    return df


# ============================================================
# REPORTE DE CALIDAD
# ============================================================

def reporte_calidad(df):
    """
    Genera estadísticas básicas de calidad para las variables
    canónicas del dataset integrado.
    """

    feats = config.columnas_features()

    n = len(df)

    filas = []

    if n == 0:
        return pd.DataFrame()

    for col in feats:

        if col not in df.columns:
            continue

        s = df[col].dropna()

        nulos = int(
            df[col].isna().sum()
        )

        unicos = int(
            df[col].nunique(
                dropna=True
            )
        )

        filas.append({

            "columna": col,

            "total": n,

            "nulos": nulos,

            "pct_nulos": round(
                nulos / n * 100,
                2
            ),

            "unicos": unicos,

            "media": (
                round(
                    float(s.mean()),
                    4
                )
                if len(s)
                else np.nan
            ),

            "desv_std": (
                round(
                    float(s.std()),
                    4
                )
                if len(s)
                else np.nan
            ),

            "min": (
                round(
                    float(s.min()),
                    4
                )
                if len(s)
                else np.nan
            ),

            "max": (
                round(
                    float(s.max()),
                    4
                )
                if len(s)
                else np.nan
            ),
        })

    return pd.DataFrame(
        filas
    )


# ============================================================
# EXPORTAR EVENTOS Y LOGS
# ============================================================

_COLUMNAS_INUTILES_EVENTOS = [
    "_linea",
    "status",
    "resource_type",
    "mode",
    "login_name",
    "program_name",
]

_COLUMNAS_INUTILES_LOGS = [
    "error_message",
    "error_level",
]


def quitar_columnas_inutiles(df, tipo):
    """
    Elimina columnas que no aportan señal al modelo:

        - artefactos internos     -> _linea
        - constantes              -> status
        - casi vacías             -> login_name, program_name,
                                     resource_type, mode, error_level
        - redundantes (duplicado) -> error_message (== mensaje)

    Devuelve el DataFrame sin esas columnas.
    """

    inutiles = (
        _COLUMNAS_INUTILES_EVENTOS
        if tipo == "eventos"
        else _COLUMNAS_INUTILES_LOGS
    )

    presentes = [
        c
        for c in inutiles
        if c in df.columns
    ]

    if presentes:

        df = df.drop(
            columns=presentes
        )

        log(
            f"   {tipo}: columnas removidas "
            f"(sin señal/redundantes) -> {presentes}"
        )

    return df


def exportar_fuentes_detalle(corridas):
    """
    Consolida los eventos y logs originales ya limpiados.

    Estos datasets se mantienen separados del dataset numérico
    principal porque contienen información de detalle.

    Se conserva run_name para identificar de qué corrida provienen.
    """

    eventos = []
    logs = []

    for corrida, _ in corridas:

        dir_salida = os.path.join(
            config.DIR_LIMPIO,
            corrida
        )

        # ----------------------------------------------------
        # EVENTOS
        # ----------------------------------------------------

        ruta_eventos = os.path.join(
            dir_salida,
            config.NOMBRE_EVENTOS_PREPARADOS
        )

        if os.path.exists(ruta_eventos):

            try:

                df_eventos = pd.read_csv(
                    ruta_eventos,
                    encoding="utf-8-sig"
                )

                if not df_eventos.empty:

                    df_eventos = df_eventos.copy()

                    df_eventos = quitar_columnas_inutiles(
                        df_eventos,
                        "eventos"
                    )

                    # Rellenar campos vacíos para evitar NaN en exportación
                    for col in df_eventos.columns:
                        if df_eventos[col].dtype == "object":
                            df_eventos[col] = df_eventos[col].fillna("")
                        else:
                            df_eventos[col] = df_eventos[col].fillna(0)

                    df_eventos["run_name"] = (
                        corrida
                    )

                    eventos.append(
                        df_eventos
                    )

            except Exception as e:

                log(
                    f"   Error leyendo eventos "
                    f"de {corrida}: {e}"
                )

        # ----------------------------------------------------
        # SQL SERVER LOGS
        # ----------------------------------------------------

        ruta_logs = os.path.join(
            dir_salida,
            config.NOMBRE_LOGS_PREPARADOS
        )

        if os.path.exists(ruta_logs):

            try:

                df_logs = pd.read_csv(
                    ruta_logs,
                    encoding="utf-8-sig"
                )

                if not df_logs.empty:

                    df_logs = df_logs.copy()

                    df_logs = quitar_columnas_inutiles(
                        df_logs,
                        "logs"
                    )

                    # Rellenar campos vacíos para evitar NaN en exportación
                    for col in df_logs.columns:
                        if df_logs[col].dtype == "object":
                            df_logs[col] = df_logs[col].fillna("")
                        else:
                            df_logs[col] = df_logs[col].fillna(0)

                    df_logs["run_name"] = (
                        corrida
                    )

                    logs.append(
                        df_logs
                    )

            except Exception as e:

                log(
                    f"   Error leyendo logs "
                    f"de {corrida}: {e}"
                )

    # --------------------------------------------------------
    # GUARDAR EVENTOS
    # --------------------------------------------------------

    if eventos:

        df_eventos_final = pd.concat(
            eventos,
            ignore_index=True,
            sort=False
        )

        ruta_eventos_salida = os.path.join(
            config.DIR_INTEGRADO,
            config.ARCHIVO_DATASET_EVENTOS
        )

        df_eventos_final.to_csv(
            ruta_eventos_salida,
            index=False,
            encoding="utf-8-sig"
        )

        log(
            f"Dataset de eventos: "
            f"{ruta_eventos_salida} "
            f"({len(df_eventos_final)} filas)"
        )

    # --------------------------------------------------------
    # GUARDAR LOGS
    # --------------------------------------------------------

    if logs:

        df_logs_final = pd.concat(
            logs,
            ignore_index=True,
            sort=False
        )

        ruta_logs_salida = os.path.join(
            config.DIR_INTEGRADO,
            config.ARCHIVO_DATASET_LOGS
        )

        df_logs_final.to_csv(
            ruta_logs_salida,
            index=False,
            encoding="utf-8-sig"
        )

        log(
            f"Dataset de logs: "
            f"{ruta_logs_salida} "
            f"({len(df_logs_final)} filas)"
        )


# ============================================================
# METADATA
# ============================================================

def construir_metadata(corridas, df):
    """
    Construye la metadata descriptiva del dataset integrado.
    """

    detalle_corridas = []

    for corrida, d in corridas:

        detalle_corridas.append({

            "run_name": corrida,

            "filas": int(
                len(d)
            ),

            "rango": [
                str(
                    d["timestamp"].min()
                ),
                str(
                    d["timestamp"].max()
                )
            ]
        })

    metadata = {

        "descripcion":
            "Dataset integrado de cargas de trabajo "
            "SteelNort durante la fase de preparación "
            "de datos CRISP-DM.",

        "fase_crispdm":
            "Data Preparation",

        "fuentes":
            [
                config.NOMBRE_METRICAS,
                config.NOMBRE_EVENTS,
                config.NOMBRE_SQLSERVER_LOGS,
            ],

        "n_features":
            len(
                config.columnas_features()
            ),

        "features":
            config.columnas_features(),

        "contexto":
            config.columnas_contexto(),

        "corridas":
            detalle_corridas,

        "total_corridas":
            len(corridas),

        "total_filas":
            int(len(df)),

        "nota_independencia":
            (
                "Cada corrida representa una carga/captura "
                "independiente. Las corridas se integran "
                "únicamente mediante concatenación, "
                "conservando run_name y experiment_id "
                "para identificar su procedencia."
            ),

        "nota_etiquetado":
            (
                "Durante la preparación de datos no se "
                "asigna la columna is_anomaly ni se "
                "clasifican las corridas como normales o "
                "anómalas. La detección de anomalías "
                "corresponde a la fase de Modelado."
            ),

        "nota_tasas":
            (
                "total_reads y total_writes se transforman "
                "a tasas mediante delta/dt. Las variables "
                "page_reads_per_sec, page_writes_per_sec, "
                "rollbacks_per_sec, batch_requests_per_sec "
                "y sql_compilations_per_sec no se vuelven "
                "a diferenciar en esta etapa porque "
                "corresponden a valores entregados por "
                "el collector."
            ),
    }

    return metadata


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Verificar directorio
    # --------------------------------------------------------

    if not os.path.isdir(
        config.DIR_LIMPIO
    ):

        log(
            f"No existe el directorio de datos limpios: "
            f"{config.DIR_LIMPIO}"
        )

        return

    # --------------------------------------------------------
    # Cargar transformaciones
    # --------------------------------------------------------

    corridas = cargar_transformadas()

    if not corridas:

        log(
            "No hay datos transformados. "
            "Ejecuta 03_transformacion.py."
        )

        return

    nombres_corridas = [
        c[0]
        for c in corridas
    ]

    log(
        f"Corridas a integrar "
        f"({len(corridas)}): "
        f"{nombres_corridas}"
    )

    # --------------------------------------------------------
    # Crear directorio de salida
    # --------------------------------------------------------

    os.makedirs(
        config.DIR_INTEGRADO,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Construir dataset integrado
    # --------------------------------------------------------

    df = construir_integrado(
        corridas
    )

    if df.empty:

        log(
            "El dataset integrado quedó vacío."
        )

        return

    # --------------------------------------------------------
    # Guardar dataset principal
    # --------------------------------------------------------

    ruta_csv = os.path.join(
        config.DIR_INTEGRADO,
        config.ARCHIVO_DATASET_INTEGRADO
    )

    df.to_csv(
        ruta_csv,
        index=False,
        encoding="utf-8-sig"
    )

    log(
        f"Dataset integrado: "
        f"{ruta_csv} "
        f"({df.shape[0]} filas x "
        f"{df.shape[1]} columnas)"
    )

    # --------------------------------------------------------
    # Exportar eventos y logs
    # --------------------------------------------------------

    exportar_fuentes_detalle(
        corridas
    )

    # --------------------------------------------------------
    # Reporte de calidad
    # --------------------------------------------------------

    reporte = reporte_calidad(
        df
    )

    ruta_rep = os.path.join(
        config.DIR_INTEGRADO,
        config.ARCHIVO_REPORTE_CALIDAD
    )

    reporte.to_csv(
        ruta_rep,
        index=False,
        encoding="utf-8-sig"
    )

    log(
        f"Reporte de calidad: "
        f"{ruta_rep}"
    )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    metadata = construir_metadata(
        corridas,
        df
    )

    ruta_meta = os.path.join(
        config.DIR_INTEGRADO,
        config.ARCHIVO_METADATA
    )

    with open(
        ruta_meta,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            metadata,
            f,
            ensure_ascii=False,
            indent=2
        )

    log(
        f"Metadata: {ruta_meta}"
    )

    # --------------------------------------------------------
    # RESUMEN FINAL
    # --------------------------------------------------------

    print(
        "\n=== RESUMEN INTEGRACION (PREPARACION) ==="
    )

    print(
        f"Corridas integradas: {len(corridas)}"
    )

    print(
        f"Filas totales: {len(df)}"
    )

    print(
        f"Columnas totales: {df.shape[1]}"
    )

    print(
        f"Features: {len(config.columnas_features())}"
    )

    print(
        "\nFilas por corrida:"
    )

    print(
        df.groupby(
            "run_name"
        ).size().to_string()
    )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()