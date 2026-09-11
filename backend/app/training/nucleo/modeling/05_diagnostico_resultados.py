"""
05_diagnostico_resultados.py
============================

Etapa RESULTADO del flujo entrada → preparación → modelo → resultado.

Cruza las cuatro piezas para emitir el diagnóstico final de cada
anomalía inyectada en carga5:

  1. GROUND TRUTH  : output/carga5/anomalias_timeline.csv (qué fault
                     y en qué ventana se inyectó).
  2. DETECCIÓN     : scores_muestras.csv + dataset_muestras_test.pkl
                     (qué ventanas de test marcó el modelo como fuera
                     de lo normal).
  3. VARIABLES     : atribución estilo DBPA (create_models): para cada
                     fault se comparan las variables de la ventana
                     anormal contra el baseline NORMAL de la misma
                     corrida; las de mayor desviación robusta son las
                     variables que provocaron la anomalía.
  4. REGLAS R1-R7  : detecciones_reglas.csv + diagnostico_reglas.json
                     (qué regla se disparó, su diagnóstico textual y la
                     causa probable según conocimiento de dominio).

Empalma faul→ventana temporal→window de prueba→reglas y produce:

    output/modelado/diagnostico/informe_deteccion.json
    output/modelado/diagnostico/resumen_consola.txt
"""

import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

import config

# ---------------------------------------------------------------------
# CORRIDA DE ANOMALIAS (dinámica: la carpeta con anomalias_timeline.csv)
# ---------------------------------------------------------------------
# Normalmente carga5, vive en <OUTPUT>/anomalias/carga5/. Se detecta sola
# para no depender de un nombre hardcodeado.
CORRIDA = config.corrida_anomalia_principal()
if not CORRIDA:
    raise SystemExit(
        "No hay corrida de anomalias (falta anomalias_timeline.csv "
        "en <OUTPUT>/anomalias/). Ejecuta la captura con inyeccion.")
RUTA_CORRIDA = config.ruta_corrida(config.OUTPUT_BASE, CORRIDA)

# ---------------------------------------------------------------------
# RUTAS
# ---------------------------------------------------------------------
DIR_DIAG = os.path.join(config.DIR_MODELADO, "diagnostico")

RUTA_TIMELINE = os.path.join(RUTA_CORRIDA, "anomalias_timeline.csv")
RUTA_DATASET = config.DATASET_PRINCIPALES
RUTA_SCORES = os.path.join(
    config.DIR_DETECCION, "scores_muestras.csv")
RUTA_ALERTAS = os.path.join(
    config.DIR_DETECCION, "alertas_test.csv")
RUTA_TEST_PKL = os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl")
RUTA_REGLAS = os.path.join(
    config.DIR_REGLAS, "detecciones_reglas.csv")
RUTA_DIAG_REGLAS = os.path.join(
    config.DIR_REGLAS, "diagnostico_reglas.json")

# Huella esperada por fault según DBPA (domain knowledge, para el cruce).
FOOTPRINT_ESPERADO = {
    "fault1":   {"sospecha": "Escrituras al log de transacciones por INSERTs"
                              " altamente concurrentes",
                 "vars": ["total_writes", "disk_write_per_sec",
                          "transactions_per_sec", "wait_log_count"]},
    "fault2":   {"sospecha": "Falta de índice (full scan): lecturas físicas "
                             "muy altas y esperas de página",
                 "vars": ["total_reads", "disk_read_per_sec",
                          "page_reads", "wait_io_count", "cpu_usr"]},
    "fault3":   {"sospecha": "Carga de trabajo pesada sobre la API: CPU alta "
                             "y latencia del endpoint elevada",
                 "vars": ["cpu_usr", "api_latency_ms", "load1",
                          "active_sessions", "query_count"]},
    "fault5":   {"sospecha": "Commits altamente concurrentes: confirmaciones "
                             "de log simultáneas",
                 "vars": ["transactions_per_sec", "total_writes",
                          "disk_write_per_sec", "wait_log_count"]},
    "lockwait": {"sospecha": "Retención de lock con sesiones bloqueadas: "
                             "contención de concurrencia",
                 "vars": ["lock_waits", "wait_lck_count", "total_locks",
                          "active_requests", "long_queries"]},
}

EPS = 1e-9


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------
# 1. GROUND TRUTH: etiquetar cada muestra de la corrida de anomalias
# ---------------------------------------------------------------------

def etiquetar_muestras(df, timeline, corrida):
    """Devuelve df de la corrida de anomalias con columna 'fase'."""
    c5 = df[df["run_name"] == corrida].copy()
    c5["timestamp"] = pd.to_datetime(c5["timestamp"])

    c5["fase"] = "normal"
    for _, row in timeline.iterrows():
        mask = (
            (c5["timestamp"] >= pd.to_datetime(row["inicio"]))
            & (c5["timestamp"] <= pd.to_datetime(row["fin"]))
        )
        c5.loc[mask, "fase"] = row["tipo"]
    return c5


# ---------------------------------------------------------------------
# 2. VENTANAS DE TEST ETIQUETADAS
# ---------------------------------------------------------------------

def etiquetar_windows(test_pkl, scores, timeline):
    """Une ventanas de test con su fase real y su predicción."""
    feats = test_pkl["features"]
    n_var = len(feats)
    rows = []
    for i, (run, vent) in enumerate(zip(test_pkl["runs"],
                                        test_pkl["ventanas"])):
        inicio = pd.to_datetime(vent["inicio"])
        fin = pd.to_datetime(vent["fin"])
        r = {"idx": i, "run": run, "inicio": inicio, "fin": fin,
             "n": vent["n"]}
        fase = "normal"
        for _, tl in timeline.iterrows():
            if (inicio <= pd.to_datetime(tl["fin"])
                    and fin >= pd.to_datetime(tl["inicio"])):
                fase = tl["tipo"]
                break
        r["fase"] = fase
        if run == CORRIDA:
            r["es_anomalia"] = True
        rows.append(r)

    w = pd.DataFrame(rows)
    sc = scores[["idx", "score", "prediccion"]].copy()
    sc.columns = ["idx", "score", "prediccion"]
    w = w.merge(sc, on="idx", how="left")
    # 'prediccion': 1 = normal, -1 = anómalo (IsolationForest)
    w["alerta"] = (w["prediccion"].fillna(1) == -1).astype(int)
    return w, feats


# ---------------------------------------------------------------------
# 3. ATRIBUCIÓN DE VARIABLES (estilo DBPA create_models)
# ---------------------------------------------------------------------

def desviacion_robusta(anormal, normal):
    """|Δmediana| normalizada por la dispersión robusta del baseline."""
    med_n = float(normal.median()) if len(normal) else np.nan
    mad_n = float(np.median(np.abs(normal - med_n))) if len(normal) else np.nan
    escala = 1.4826 * mad_n + EPS
    if not np.isfinite(med_n):
        return 0.0
    return abs(float(anormal.median()) - med_n) / escala


def atribuir_variables(c5, features, timeline):
    """Por fault: top variables desviadas vs baseline normal de la
    corrida de anomalias."""
    normal = c5[c5["fase"] == "normal"]
    resultado = {}
    for _, tl in timeline.iterrows():
        fault = tl["tipo"]
        anomalo = c5[c5["fase"] == fault]
        if anomalo.empty:
            resultado[fault] = []
            continue
        punt = []
        for var in features:
            if var not in c5.columns:
                continue
            z = desviacion_robusta(anomalo[var], normal[var])
            if z > 0:
                punt.append({"variable": var, "desviacion": round(z, 3)})
        punt.sort(key=lambda x: x["desviacion"], reverse=True)
        resultado[fault] = punt[:10]
    return resultado


# ---------------------------------------------------------------------
# 4. REGLAS DISPARADAS POR VENTANA DE FAULT
# ---------------------------------------------------------------------

def reglas_por_fault(reglas, diagnostico, timeline):
    reglas_c5 = reglas[reglas["run_name"] == CORRIDA].copy()
    reglas_c5["timestamp"] = pd.to_datetime(reglas_c5["timestamp"])
    
    print(f"DEBUG: Total reglas para corrida {CORRIDA}: {len(reglas_c5)}")
    if not reglas_c5.empty:
        print(f"DEBUG: Rango reglas -> Min: {reglas_c5['timestamp'].min()} | Max: {reglas_c5['timestamp'].max()}")

    catalogo = diagnostico.get("reglas", {})
    out = {}
    for _, tl in timeline.iterrows():
        fault = tl["tipo"]
        ini = pd.to_datetime(tl["inicio"])
        fin = pd.to_datetime(tl["fin"])
        print(f"DEBUG: Buscando {fault} entre {ini} y {fin}")
        
        lineas = reglas_c5[
            (reglas_c5["timestamp"] >= ini)
            & (reglas_c5["timestamp"] <= fin)
        ]
        print(f"DEBUG: Encontradas {len(lineas)} reglas para {fault}")
        # ... resto de la función
        det = "normal"
        if not lineas.empty:
            det = "-".join(sorted(set(lineas["regla"])))
        texto = []
        for r_, v in sorted(catalogo.items()):
            if r_ in (det.split("-") if det != "normal" else []):
                texto.append(f"{r_}: {v.get('diagnostico', '')}")
        out[fault] = {
            "detecciones_reglas": int(len(lineas)),
            "reglas_disparadas": det,
            "conteo_por_regla": (
                lineas["regla"].value_counts().to_dict()),
            "diagnostico": " ".join(texto) or None,
        }
    return out


# ---------------------------------------------------------------------
# 5. MÉTRICAS DE DETECCIÓN (ground truth vs modelo) POR FAULT
# ---------------------------------------------------------------------

def metricas_deteccion(w):
    """Confusión ventana a ventana sobre la corrida de anomalias (test)."""
    c5 = w[w["es_anomalia"] == True].copy()  # noqa: E712
    total_fault = (c5["fase"] != "normal").sum()
    total_normal = (c5["fase"] == "normal").sum()
    alertas_fault = int(((c5["fase"] != "normal") & (c5["alerta"] == 1)).sum())
    alertas_normal = int(((c5["fase"] == "normal") & (c5["alerta"] == 1)).sum())
    reporte = {
        "ventanas_corrida_anomalia_test": int(len(c5)),
        "ventanas_fault": int(total_fault),
        "ventanas_normal": int(total_normal),
        "alertas_en_fault": alertas_fault,
        "alertas_en_normal_fp": alertas_normal,
        "recall": round(alertas_fault / total_fault, 3) if total_fault else None,
        "fpr": round(alertas_normal / total_normal, 3) if total_normal else None,
    }
    por_fault = {}
    for fase in c5[c5["fase"] != "normal"]["fase"].unique():
        sub = c5[c5["fase"] == fase]
        a = int(sub["alerta"].sum())
        por_fault[fase] = {
            "ventanas_total": int(len(sub)),
            "ventanas_alertadas": a,
            "tpr": round(a / len(sub), 3) if len(sub) else None,
        }
    return reporte, por_fault


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():
    os.makedirs(DIR_DIAG, exist_ok=True)

    # Ground truth
    timeline = pd.read_csv(RUTA_TIMELINE, encoding="utf-8-sig")

    # Dataset integrado
    df = pd.read_csv(RUTA_DATASET, encoding="utf-8-sig")
    c5 = etiquetar_muestras(df, timeline, CORRIDA)

    # Deteccion.
    # Nota: se usa alertas_test.csv (ventanas de TEST que 03 indexa desde 0).
    # scores_muestras.csv es el score de TRAIN y NO comparte idx: cruzarla
    # contra las ventanas de test por idx desalineaba la realidad (bug original).
    scores = pd.read_csv(RUTA_ALERTAS, encoding="utf-8-sig")
    test = pd.read_pickle(RUTA_TEST_PKL)
    w, features = etiquetar_windows(test, scores, timeline)

    # Reglas
    reglas = pd.read_csv(RUTA_REGLAS, encoding="utf-8-sig")
    diag_r = json.load(open(RUTA_DIAG_REGLAS, encoding="utf-8"))

    # ---- Análisis ------------------------------------------------
    atribucion = atribuir_variables(c5, features, timeline)
    reglas_fault = reglas_por_fault(reglas, diag_r, timeline)
    deteccion, deteccion_fault = metricas_deteccion(w)

    # Detalle por fault
    por_fault = {}
    for _, tl in timeline.iterrows():
        fault = tl["tipo"]
        fp = FOOTPRINT_ESPERADO.get(fault, {})
        vars_causantes = atribucion.get(fault, [])
        coinciden = [
            v["variable"] for v in vars_causantes[:6]
            if v["variable"] in fp.get("vars", [])
        ]
        por_fault[fault] = {
            "ventana": f"{tl['inicio']} → {tl['fin']}",
            "sospecha_esperada": fp.get("sospecha", ""),
            "variables_causantes_top": vars_causantes[:6],
            "coincidencia_con_huella": coinciden,
            "reglas": reglas_fault.get(fault, {}),
            "deteccion": deteccion_fault.get(fault, {}),
        }

    informe = {
        "corrida": CORRIDA,
        "ruta_corrida": RUTA_CORRIDA,
        "fecha": pd.Timestamp(
            os.path.getmtime(RUTA_TIMELINE), unit="s"
        ).strftime("%Y-%m-%d"),
        "resumen_deteccion": deteccion,
        "por_fault": por_fault,
        "conclusion": {
            "es_anomalo": deteccion["alertas_en_fault"] > 0,
            "faults_inyectados": len(timeline),
            "faults_con_reglas": int(sum(
                1 for f in por_fault.values() if f["reglas"].get("detecciones_reglas", 0) > 0)),
        },
    }

    # ---- Guardar ------------------------------------------------
    os.makedirs(DIR_DIAG, exist_ok=True)
    ruta_json = os.path.join(DIR_DIAG, "informe_deteccion.json")
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=2)

    # ---- Reporte de consola --------------------------------------
    log("==========================================================")
    log("EL DIAGNÓSTICO FINAL DEL DIAGNÓSTICO (RESULTADO)")
    log("==========================================================")
    log(f"Corrida de anomalias diagnosticada: {CORRIDA} ({RUTA_CORRIDA})")
    log(f"Detección (ventanas de test): {deteccion}")
    log("")
    for fault, info in por_fault.items():
        log(f"● {fault.upper()}  [{info['ventana']}]")
        log(f"   Detección: {info['deteccion']}")
        log(f"   Reglas:    {info['reglas']['reglas_disparadas'] or '-'} "
            f"({info['reglas']['detecciones_reglas']} casos)")
        top = ", ".join(f"{v['variable']}(Δ{ v['desviacion']})"
                        for v in info['variables_causantes_top'][:5])
        log(f"   Variables causantes (top): {top}")
        log(f"   Coinciden con la huella esperada: {info['coincidencia_con_huella']}")
        if info['variables_causantes_top']:
            bloqueadas = info['reglas']['diagnostico']
            log(f"   Diagnóstico: {bloqueadas or 'sin reglas'}")
        log("")
    log("==========================================================")
    log(f"Informe completo: {ruta_json}")


if __name__ == "__main__":
    main()