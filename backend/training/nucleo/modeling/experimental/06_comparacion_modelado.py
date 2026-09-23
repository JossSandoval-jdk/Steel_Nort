"""
06_comparacion_modelos.py
=========================
Consolida las métricas de prueba de todos los modelos entrenados
(alertas_test*.csv en deteccion/) y genera una tabla comparativa global.

Para cada modelo y cada umbral estadístico (q10/q05/q01) calcula:
    - Alertas totales sobre el test.
    - TPR (Recall): ventanas con fault real del timeline que fueron alertadas.
    - FPR (falsas alarmas): ventanas normales que fueron alertadas.
    - F1: combinación de precisión y recall.

El archivo de producción ``alertas_test.csv`` pertenece al modelo vigente
(IsolationForest) y se etiqueta como ISOLATION_FOREST.
"""

import glob
import os

import numpy as np
import pandas as pd

import config

MATRICES = ["q10", "q05", "q01"]
UMBRAL_RANKING = "q05"


def log(msg):
    print(f"[COMPARACION] {msg}", flush=True)


def nombre_modelo(archivo):
    if archivo == "alertas_test.csv":
        return "ISOLATION_FOREST"
    return archivo.replace("alertas_test_", "").replace(".csv", "").upper()


def cargar_timelines():
    rutas = sorted(set(
        glob.glob(os.path.join(config.DIR_CORRIDAS, "anomalias", "*", "anomalias_timeline.csv"))
        + glob.glob(os.path.join(config.DIR_CORRIDAS, "*", "anomalias_timeline.csv"))
    ))
    frames = []
    for r in rutas:
        run = os.path.basename(os.path.dirname(r))
        df = pd.read_csv(r, encoding="utf-8-sig")
        df["run_name"] = run
        frames.append(df)
    if not frames:
        return None
    tl = pd.concat(frames, ignore_index=True)
    tl["inicio"] = pd.to_datetime(tl["inicio"])
    tl["fin"] = pd.to_datetime(tl["fin"])
    return tl


def marcar_fault(df, timelines):
    """Fecha ventana -> fase: True si la ventana cruza con algún fault."""
    es_fault = pd.Series(False, index=df.index)
    if timelines is None:
        return es_fault
    for run, g in timelines.groupby("run_name"):
        mask_run = df["run"] == run
        if not mask_run.any():
            continue
        ini_w = pd.to_datetime(df["inicio"][mask_run])
        fin_w = pd.to_datetime(df["fin"][mask_run])
        for _, f in g.iterrows():
            es_fault.loc[mask_run] |= (
                (ini_w <= f["fin"]) & (fin_w >= f["inicio"])
            )
    return es_fault


def main():
    dir_det = config.DIR_DETECCION

    if not os.path.exists(dir_det):
        log(f"No existe el directorio de detección: {dir_det}")
        return

    archivos = sorted(
        f for f in os.listdir(dir_det)
        if f.startswith("alertas_test") and f.endswith(".csv")
    )

    if not archivos:
        log("No se encontraron archivos de alertas para comparar.")
        return

    timelines = cargar_timelines()
    if timelines is not None:
        log(f"Timelines cargados: {sorted(timelines['run_name'].unique())}")
    else:
        log("Sin timelines: la tabla incluirá solo alertas/FPR.")

    resumen_global = []

    for archivo in archivos:
        ruta_csv = os.path.join(dir_det, archivo)
        df = pd.read_csv(ruta_csv, encoding="utf-8-sig")

        columnas_faltantes = [
            c for c in ["run", "inicio", "fin"] if c not in df.columns
        ]
        if columnas_faltantes:
            log(f"Omitido (faltan {columnas_faltantes}): {archivo}")
            continue

        es_fault = marcar_fault(df, timelines)
        total_fault = int(es_fault.sum())
        total_normal = int((~es_fault).sum())

        fila = {
            "Modelo": nombre_modelo(archivo),
            "Muestras Test": len(df),
            "Ventanas Fault": total_fault,
        }

        for umbral in MATRICES:
            if umbral not in df.columns:
                continue
            alerta = df[umbral] == 1
            n_alertas = int(alerta.sum())
            tp = int((alerta & es_fault).sum())
            fp = int((alerta & ~es_fault).sum())

            tpr = (tp / total_fault) if total_fault else None
            fpr = (fp / total_normal) if total_normal else None
            prec = (tp / (tp + fp)) if (tp + fp) else 0.0
            f1 = (
                2 * prec * tpr / (prec + tpr)
                if (prec and tpr is not None and (prec + tpr) > 0)
                else 0.0
            )

            fila[f"Alertas ({umbral})"] = n_alertas
            fila[f"TPR ({umbral}) %"] = round(tpr * 100, 2) if tpr is not None else None
            fila[f"FPR ({umbral}) %"] = round(fpr * 100, 2) if fpr is not None else None
            fila[f"F1 ({umbral})"] = round(f1, 3)

        resumen_global.append(fila)

    if not resumen_global:
        log("Ningún archivo de alertas pudo procesarse.")
        return

    df_comparativa = pd.DataFrame(resumen_global)
    df_comparativa = df_comparativa.sort_values(
        [f"F1 ({UMBRAL_RANKING})", f"TPR ({UMBRAL_RANKING}) %"],
        ascending=False,
    ).reset_index(drop=True)

    ruta_salida = os.path.join(dir_det, "tabla_comparativa_modelos.csv")
    df_comparativa.to_csv(ruta_salida, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 72)
    print(" TABLA COMPARATIVA DE RENDIMIENTO (test con faults del timeline)")
    print("=" * 72)
    print(df_comparativa.to_string(index=False))
    print("=" * 72)

    if df_comparativa.get(f"F1 ({UMBRAL_RANKING})").notna().any():
        mejor = df_comparativa.iloc[0]
        print(
            f"\nMejor modelo según F1 ({UMBRAL_RANKING}): {mejor['Modelo']} "
            f"(TPR={mejor[f'TPR ({UMBRAL_RANKING}) %']}%, "
            f"FPR={mejor[f'FPR ({UMBRAL_RANKING}) %']}%, "
            f"F1={mejor[f'F1 ({UMBRAL_RANKING})']})"
        )

    log(f"Tabla comparativa guardada en: {ruta_salida}")


if __name__ == "__main__":
    main()