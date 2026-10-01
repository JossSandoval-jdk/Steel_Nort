"""
06_comparacion_modelos.py
========================
Consolida las métricas de prueba de TODOS los modelos candidatos en una tabla
comparativa global (ISOLATION_FOREST, COPOD, LOF, OCSVM, ELLIPTIC,
ENSEMBLE_Z), TPR/FPR/F1 por umbral (q10/q05/q01) y AUC.

Fuente autoritativa (cuando existe): ``validacion/resumen_modelos.csv`` +
``validacion/aucs.csv`` de validar_candidato.py: todos los esquemas se evalúan
con el MISMO hold-out por corrida, mismo scaler, mismas features y la misma
definición de umbral (cuantil del train propio) → comparación justa.

Respaldo (legacy): si no existe el resumen, consolida los ``alertas_test*.csv``
de detección/ (modelos con artefacto de esa época).
"""

import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

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
    """Fecha ventana -> fase: True si la ventana cruza con algún fault.
    Convención del informe de validación: si la corrida no tiene timeline
    (p. ej. run5, eliminada en la limpieza) SUS ventanas de test se asumen
    fault (el test se compone solo de corridas de anomalía)."""
    es_fault = pd.Series(True, index=df.index)
    if timelines is None:
        return es_fault
    con_timeline = []
    for run, g in timelines.groupby("run_name"):
        mask_run = df["run"] == run
        if not mask_run.any():
            continue
        con_timeline.append(run)
        ini_w = pd.to_datetime(df["inicio"][mask_run])
        fin_w = pd.to_datetime(df["fin"][mask_run])
        crossing = pd.Series(False, index=df.index[mask_run])
        for _, f in g.iterrows():
            crossing |= (
                (ini_w <= f["fin"]) & (fin_w >= f["inicio"])
            )
        es_fault.loc[mask_run] = crossing
    sin_timeline = sorted(set(df["run"].unique()) - set(con_timeline))
    if sin_timeline:
        log(f"Run sin timeline asumido fault: {sin_timeline}")
    return es_fault


DIR_VAL = os.path.join(config.DIR_DETECCION, "validacion")
SEED_COMPARAR = 42  # semilla base del informe (resumen_modelos.csv)


def tabla_desde_resumen():
    """Comparativa autoritativa de TODOS los esquemas con protocolo uniforme
    (validar_candidato.run_experimento): resumen_modelos.csv + aucs.csv."""
    r_resumen = os.path.join(DIR_VAL, "resumen_modelos.csv")
    r_aucs = os.path.join(DIR_VAL, "aucs.csv")
    if not os.path.exists(r_resumen):
        return None, None
    df = pd.read_csv(r_resumen, encoding="utf-8-sig")
    if "seed" in df.columns:
        df = df[df["seed"] == SEED_COMPARAR]
    aucs = pd.read_csv(r_aucs, encoding="utf-8-sig") if os.path.exists(r_aucs) else None

    filas = []
    for esquema, g in df.groupby("esquema"):
        fila = {"Modelo": esquema}
        fila["Muestras Test"] = int(
            g["tp"].iloc[0] + g["fn"].iloc[0] + g["fp"].iloc[0] + g["tn"].iloc[0])
        fila["Ventanas Fault"] = int(g["tp"].iloc[0] + g["fn"].iloc[0])
        for q in MATRICES:
            row = g[g["umbral"] == q]
            if row.empty:
                continue
            r = row.iloc[0]
            fila[f"Alertas ({q})"] = int(r["tp"] + r["fp"])
            fila[f"TPR ({q}) %"] = round(float(r["tpr"]) * 100, 2) if pd.notna(r["tpr"]) else None
            fila[f"FPR ({q}) %"] = round(float(r["fpr"]) * 100, 2) if pd.notna(r["fpr"]) else None
            fila[f"F1 ({q})"] = round(float(r["f1"]), 3) if pd.notna(r["f1"]) else None
        if aucs is not None:
            au = aucs[aucs.iloc[:, 0].astype(str) == str(esquema)]
            if not au.empty:
                fila["ROC (AUC)"] = round(float(au.iloc[0]["roc_auc"]), 4)
                fila["PR (AUC)"] = round(float(au.iloc[0]["pr_auc"]), 4)
        filas.append(fila)
    if not filas:
        return None, None
    return (pd.DataFrame(filas),
            "resumen_modelos.csv + aucs.csv (validar_candidato, hold-out uniforme)")


def comparar_desde_artefactos():
    """Respaldo (legacy): consolidar alertas_test*.csv por su timeline."""
    dir_det = config.DIR_DETECCION
    archivos = sorted(
        f for f in os.listdir(dir_det)
        if f.startswith("alertas_test") and f.endswith(".csv")
    )
    if not archivos:
        log("No se encontraron archivos de alertas para comparar.")
        return None, None

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
        return None, None
    return pd.DataFrame(resumen_global), "alertas_test*.csv (artefactos legacy)"


def main():
    dir_det = config.DIR_DETECCION

    if not os.path.exists(dir_det):
        log(f"No existe el directorio de detección: {dir_det}")
        return

    df_comparativa, fuente = tabla_desde_resumen()
    if df_comparativa is None:
        log("[AVISO] Sin resumen_modelos.csv: uso artefactos legacy alertas_test*.csv")
        df_comparativa, fuente = comparar_desde_artefactos()
    if df_comparativa is None:
        return

    df_comparativa = df_comparativa.sort_values(
        [f"F1 ({UMBRAL_RANKING})", f"TPR ({UMBRAL_RANKING}) %"],
        ascending=False,
    ).reset_index(drop=True)

    ruta_salida = os.path.join(dir_det, "tabla_comparativa_modelos.csv")
    df_comparativa.to_csv(ruta_salida, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 72)
    print(" TABLA COMPARATIVA DE RENDIMIENTO (todos los esquemas, mismo split)")
    print("=" * 72)
    print(df_comparativa.to_string(index=False))
    print("=" * 72)
    print(f"Fuente: {fuente}")

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