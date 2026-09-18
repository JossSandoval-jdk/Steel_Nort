"""
05_diagnostico_resultados.py
============================

Etapa RESULTADO del flujo entrada → preparación → modelo → resultado.

Genera el informe de detección de anomalías para CUALQUIER corrida:
recorre TODAS las corridas presentes en el dataset/modelo (baseline/ y
anomalias/) y reporta en informe_deteccion.json cuáles presentan
anomalías detectadas, con la evidencia de cada una:

1. MODELO      : ventanas que el IsolationForest califica por debajo del
                 umbral q10 (score < percentil 10 de los scores de
                 entrenamiento). Se evalúa sobre TODAS las corridas.
2. REGLAS R1-R7: detecciones_reglas.csv + diagnostico_reglas.json
                 (qué regla se disparó y su diagnóstico textual).
3. GROUND TRUTH: anomalias_timeline.csv de las corridas de anomalias/
                 (TPR/FPR y desglose por fault donde el timeline cruza
                 con las ventanas reales).
4. VARIABLES   : atribución estilo DBPA sobre las ventanas alertadas.

Salidas:
    output/modelado/diagnostico/informe_deteccion.json
    output/modelado/diagnostico/resumen_consola.txt
"""

import datetime
import json
import os

import numpy as np
import pandas as pd

import config

# ---------------------------------------------------------------------
# RUTAS
# ---------------------------------------------------------------------
DIR_DIAG = os.path.join(config.DIR_MODELADO, "diagnostico")

RUTA_DATASET = config.DATASET_PRINCIPALES
RUTA_TRAIN_PKL = os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl")
RUTA_TEST_PKL = os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl")
RUTA_SCORES = os.path.join(config.DIR_DETECCION, "scores_muestras.csv")
RUTA_ALERTAS = os.path.join(config.DIR_DETECCION, "alertas_test.csv")
RUTA_REGLAS = os.path.join(config.DIR_REGLAS, "detecciones_reglas.csv")
RUTA_DIAG_REGLAS = os.path.join(config.DIR_REGLAS, "diagnostico_reglas.json")

# Máxima cantidad de ventanas/reglas que se listan en el informe por corrida.
MAX_VENTANAS_ALERTADAS = 40
MAX_TIMESTAMPS_REGLAS = 30


def corridas_anomalia_diagnosticables():
    """Todas las corridas de anomalías con su ruta de timeline.

    Usa la definición canónica de config.corridas_anomalia() (todas las
    subcarpetas de anomalies/ con metrics.log) y localiza el
    anomalias_timeline.csv de cada una. Devuelve {corrida: ruta_timeline}.
    """
    raiz = config.DIR_CORRIDAS
    rutas = {}
    for corrida in config.corridas_anomalia(raiz):
        for candidata in (
            os.path.join(raiz, "anomalias", corrida, "anomalias_timeline.csv"),
            os.path.join(raiz, corrida, "anomalias_timeline.csv"),
        ):
            if os.path.isfile(candidata):
                rutas[corrida] = candidata
                break
    return rutas


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
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        # Consolas Windows (cp1252): degrada los caracteres no imprimibles.
        print(msg.encode("cp1252", errors="replace").decode("cp1252"),
              flush=True)


# ---------------------------------------------------------------------
# CARGA UNIFICADA DE VENTANAS (train + test) CON ALERTA MODELO
# ---------------------------------------------------------------------

def cargar_ventanas():
    """Todas las ventanas (train + test) con su score del modelo.

    La alerta del modelo es uniforme para todas las corridas:
        alerta = score < q10  (q10 = percentil 10 de los scores de
        entrenamiento, igual que el umbral que usa 03_deteccion.py).
    """
    train = pd.read_pickle(RUTA_TRAIN_PKL)
    scores_train = pd.read_csv(RUTA_SCORES, encoding="utf-8-sig")
    test = pd.read_pickle(RUTA_TEST_PKL)
    alertas_test = pd.read_csv(RUTA_ALERTAS, encoding="utf-8-sig")

    umbral_q10 = float(np.quantile(scores_train["score"], 0.10))

    filas = []
    for pkl, scores in ((train, scores_train), (test, alertas_test)):
        for i, (run, vent) in enumerate(zip(pkl["runs"], pkl["ventanas"])):
            try:
                score = float(scores.iloc[i]["score"])
            except (KeyError, IndexError, TypeError):
                score = float("nan")
            filas.append({
                "run": run,
                "inicio": pd.to_datetime(vent["inicio"]),
                "fin": pd.to_datetime(vent["fin"]),
                "score": score,
                "alerta": int(0 if np.isnan(score) else score < umbral_q10),
            })
    w = pd.DataFrame(filas)
    return w, umbral_q10


def etiquetar_fases_windows(w, corrida, timeline):
    """Marca la fase real de cada ventana de 'corrida' con su timeline."""
    for i in w[w["run"] == corrida].index.tolist():
        inicio = w.at[i, "inicio"]
        fin = w.at[i, "fin"]
        fase = "normal"
        for _, tl in timeline.iterrows():
            if (inicio <= pd.to_datetime(tl["fin"])
                    and fin >= pd.to_datetime(tl["inicio"])):
                fase = tl["tipo"]
                break
        w.at[i, "fase"] = fase
    return w


# ---------------------------------------------------------------------
# 1. GROUND TRUTH: etiquetar muestras de una corrida de anomalías
# ---------------------------------------------------------------------

def etiquetar_muestras(df, corrida, timeline):
    """Devuelve df_run (solo la corrida de anomalías) con columna 'fase'."""
    c_run = df[df["run_name"] == corrida].copy()
    c_run["timestamp"] = pd.to_datetime(c_run["timestamp"])

    c_run["fase"] = "normal"
    for _, row in timeline.iterrows():
        mask = (
            (c_run["timestamp"] >= pd.to_datetime(row["inicio"]))
            & (c_run["timestamp"] <= pd.to_datetime(row["fin"]))
        )
        c_run.loc[mask, "fase"] = row["tipo"]
    return c_run


# ---------------------------------------------------------------------
# 2. MÉTRICAS DE DETECCIÓN CON GROUND TRUTH (por corrida con timeline)
# ---------------------------------------------------------------------

def metricas_deteccion(sub):
    """Confusión ventana a ventana sobre una corrida con timeline."""
    total_fault = int((sub["fase"] != "normal").sum())
    total_normal = int((sub["fase"] == "normal").sum())
    alertas_fault = int(((sub["fase"] != "normal") & (sub["alerta"] == 1)).sum())
    alertas_normal = int(((sub["fase"] == "normal") & (sub["alerta"] == 1)).sum())
    reporte = {
        "ventanas_test": int(len(sub)),
        "ventanas_fault": total_fault,
        "ventanas_normal": total_normal,
        "alertas_en_fault": alertas_fault,
        "alertas_en_normal_fp": alertas_normal,
        "recall": round(alertas_fault / total_fault, 3) if total_fault else None,
        "fpr": round(alertas_normal / total_normal, 3) if total_normal else None,
    }
    por_fault = {}
    for fase in sub[sub["fase"] != "normal"]["fase"].unique():
        s = sub[sub["fase"] == fase]
        a = int(s["alerta"].sum())
        por_fault[fase] = {
            "ventanas_total": int(len(s)),
            "ventanas_alertadas": a,
            "tpr": round(a / len(s), 3) if len(s) else None,
        }
    return reporte, por_fault


# ---------------------------------------------------------------------
# 3. RECONSTRUCCIÓN POR FAULT DE REGLAS R1-R7 (con timeline)
# ---------------------------------------------------------------------

def reglas_por_fault(reglas, corrida, timeline):
    reglas_run = reglas[reglas["run_name"] == corrida].copy()
    if reglas_run.empty:
        reglas_run["timestamp"] = pd.to_datetime([])
    else:
        reglas_run["timestamp"] = pd.to_datetime(reglas_run["timestamp"])
    out = {}
    for _, tl in timeline.iterrows():
        fault = tl["tipo"]
        ini = pd.to_datetime(tl["inicio"])
        fin = pd.to_datetime(tl["fin"])
        lineas = reglas_run[
            (reglas_run["timestamp"] >= ini)
            & (reglas_run["timestamp"] <= fin)
        ]
        det = "normal"
        if not lineas.empty:
            det = "-".join(sorted(set(lineas["regla"])))
        out[fault] = {
            "detecciones_reglas": int(len(lineas)),
            "reglas_disparadas": det,
            "conteo_por_regla": lineas["regla"].value_counts().to_dict(),
        }
    return out


# ---------------------------------------------------------------------
# 4. REGLAS POR CORRIDA (todas las corridas, con o sin timeline)
# ---------------------------------------------------------------------

def reglas_por_corrida(reglas):
    out = {}
    if reglas.empty:
        return out
    for run, g in reglas.groupby("run_name"):
        t = [str(x) for x in g["timestamp"].tolist()]
        out[str(run)] = {
            "detecciones": int(len(g)),
            "por_regla": g["regla"].value_counts().to_dict(),
            "reglas": sorted(set(g["regla"])),
            "timestamps": t[:MAX_TIMESTAMPS_REGLAS],
        }
    return out


# ---------------------------------------------------------------------
# 5. ATRIBUCIÓN DE VARIABLES (DBPA) Y TOP VARIABLES DE VENTANAS ALERTADAS
# ---------------------------------------------------------------------

def desviacion_robusta(anormal, normal):
    """|Δmediana| normalizada por la dispersión robusta del baseline."""
    med_n = float(normal.median()) if len(normal) else np.nan
    mad_n = float(np.median(np.abs(normal - med_n))) if len(normal) else np.nan
    escala = 1.4826 * mad_n + EPS
    if not np.isfinite(med_n):
        return 0.0
    return abs(float(anormal.median()) - med_n) / escala


def atribuir_variables(c_run, features, timeline):
    """Por fault: top variables desviadas vs baseline normal de la corrida."""
    normal = c_run[c_run["fase"] == "normal"]
    resultado = {}
    for _, tl in timeline.iterrows():
        fault = tl["tipo"]
        anomalo = c_run[c_run["fase"] == fault]
        if anomalo.empty:
            resultado[fault] = []
            continue
        punt = []
        for var in features:
            if var not in c_run.columns:
                continue
            z = desviacion_robusta(anomalo[var], normal[var])
            if z > 0:
                punt.append({"variable": var, "desviacion": round(z, 3)})
        punt.sort(key=lambda x: x["desviacion"], reverse=True)
        resultado[fault] = punt[:10]
    return resultado


def atribuir_variables_ventanas(c_run, w_al, features):
    """Top variables de las ventanas ALERTADAS vs el resto de la corrida."""
    if c_run.empty or w_al.empty:
        return []
    ts = pd.to_datetime(c_run["timestamp"])

    def en_alerta(t):
        return bool(((t >= w_al["inicio"]) & (t <= w_al["fin"])).any())

    mask = ts.map(en_alerta)
    anom = c_run[mask]
    normal = c_run[~mask]
    if anom.empty or normal.empty:
        return []
    punt = []
    for var in features:
        if var not in c_run.columns:
            continue
        z = desviacion_robusta(anom[var], normal[var])
        if z > 0:
            punt.append({"variable": var, "desviacion": round(z, 3)})
    punt.sort(key=lambda x: x["desviacion"], reverse=True)
    return punt[:5]


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():
    os.makedirs(DIR_DIAG, exist_ok=True)

    for r in (RUTA_DATASET, RUTA_TRAIN_PKL, RUTA_TEST_PKL, RUTA_SCORES):
        if not os.path.isfile(r):
            log(f"Falta {r}. Ejecuta antes los pasos 3 y 4 (00-03).")
            return

    anom = corridas_anomalia_diagnosticables()
    log(f"Corridas de anomalies/ ({len(anom)}): {', '.join(sorted(anom))}")

    # ---- Carga ----
    df = pd.read_csv(RUTA_DATASET, encoding="utf-8-sig")
    w, umbral_q10 = cargar_ventanas()

    if os.path.isfile(RUTA_REGLAS):
        reglas = pd.read_csv(RUTA_REGLAS, encoding="utf-8-sig")
    else:
        log(f"Aviso: no existe {RUTA_REGLAS}; se continúa sin reglas R1-R7.")
        reglas = pd.DataFrame(
            columns=["run_name", "timestamp", "regla", "diagnostico"])
    if os.path.isfile(RUTA_DIAG_REGLAS):
        diag_r = json.load(open(RUTA_DIAG_REGLAS, encoding="utf-8"))
    else:
        diag_r = {}
    catalogo = diag_r.get("reglas", {})
    reglas_x_corrida = reglas_por_corrida(reglas)

    features = [
        c for c in df.columns
        if c not in config.COLUMNAS_CONTEXTO
    ]

    # Corridas a evaluar = unión de corridas con ventanas + con reglas.
    corridas_evaluadas = sorted(
        set(w["run"].tolist()) | set(reglas_x_corrida) | set(anom))

    por_corrida = {}
    total_ventanas = len(w)
    total_alertas = int(w["alerta"].sum())
    total_reglas = int(len(reglas))

    for corrida in corridas_evaluadas:
        grupo = "anomalias" if corrida in anom else "baseline"
        w_run = w[w["run"] == corrida].copy()
        ventanas_alertadas = w_run[w_run["alerta"] == 1].sort_values("score")

        sec = {
            "grupo": grupo,
            "ventanas": int(len(w_run)),
            "alertas_modelo": int(len(ventanas_alertadas)),
        }
        sec["fraccion_alertas_modelo"] = round(
            sec["alertas_modelo"] / sec["ventanas"], 4) if sec["ventanas"] else 0.0

        rg = reglas_x_corrida.get(corrida, {})
        sec["reglas"] = {
            "detecciones": rg.get("detecciones", 0),
            "por_regla": rg.get("por_regla", {}),
            "reglas": rg.get("reglas", []),
        }

        # Detección consolidada: modelo y/o reglas
        sec["detectado"] = bool(
            (sec["alertas_modelo"] > 0) or (sec["reglas"]["detecciones"] > 0))

        # Ventanas alertadas (la evidencia temporal del modelo)
        sec["ventanas_alertadas"] = [
            {"inicio": str(r["inicio"]), "fin": str(r["fin"]),
             "score": round(float(r["score"]), 4)}
            for _, r in ventanas_alertadas.head(MAX_VENTANAS_ALERTADAS).iterrows()
        ]
        sec["total_ventanas_alertadas"] = sec["alertas_modelo"]

        # Timeline (solo corridas de anomalies/ con anomalias_timeline.csv)
        tiene_timeline = corrida in anom
        sec["tiene_timeline"] = tiene_timeline
        aviso = None
        if tiene_timeline:
            timeline = pd.read_csv(anom[corrida], encoding="utf-8-sig")
            w = etiquetar_fases_windows(w, corrida, timeline)
            w_run = w[w["run"] == corrida].copy()
            metricas, deteccion_fault = metricas_deteccion(w_run)
            sec["resumen_deteccion"] = metricas
            sec["por_fault"] = {}

            c_run = etiquetar_muestras(df, corrida, timeline)
            atribucion = atribuir_variables(c_run, features, timeline)
            reglas_fault = reglas_por_fault(reglas, corrida, timeline)

            if metricas["ventanas_fault"] == 0:
                aviso = ("El timeline de esta corrida no cruza con sus "
                         "ventanas reales: no se puede calcular TPR con "
                         "ground truth. La detección se informa por modelo "
                         "y reglas.")

            for _, tl in timeline.iterrows():
                fault = tl["tipo"]
                fp = FOOTPRINT_ESPERADO.get(fault, {})
                vars_causantes = atribucion.get(fault, [])
                coinciden = [
                    v["variable"] for v in vars_causantes[:6]
                    if v["variable"] in fp.get("vars", [])
                ]
                det = reglas_fault.get(fault, {})
                sec["por_fault"][fault] = {
                    "ventana": f"{tl['inicio']} -> {tl['fin']}",
                    "sospecha_esperada": fp.get("sospecha", ""),
                    "variables_causantes_top": vars_causantes[:6],
                    "coincidencia_con_huella": coinciden,
                    "reglas": det,
                    "deteccion": deteccion_fault.get(fault, {}),
                }
            if aviso:
                sec["aviso"] = aviso
                log(f"Aviso [{corrida}]: {aviso}")

        # Top variables causantes de las ventanas alertadas (con o sin timeline)
        if sec["alertas_modelo"] > 0 and not w_run.empty:
            c_run = df[df["run_name"] == corrida].copy()
            sec["top_variables_alertas"] = atribuir_variables_ventanas(
                c_run, w_run[w_run["alerta"] == 1], features)
        else:
            sec["top_variables_alertas"] = []

        por_corrida[corrida] = sec

    # ---- Acumulados globales ----
    corridas_detectadas = sorted(
        c for c, s in por_corrida.items() if s["detectado"])
    corridas_limpias = sorted(
        c for c, s in por_corrida.items() if not s["detectado"])

    # Métricas con ground truth (solo timeline)
    ttl_fault = sum(
        s["resumen_deteccion"]["ventanas_fault"]
        for s in por_corrida.values() if s.get("resumen_deteccion"))
    ttl_normal = sum(
        s["resumen_deteccion"]["ventanas_normal"]
        for s in por_corrida.values() if s.get("resumen_deteccion"))
    ttl_a_fault = sum(
        s["resumen_deteccion"]["alertas_en_fault"]
        for s in por_corrida.values() if s.get("resumen_deteccion"))
    ttl_a_normal = sum(
        s["resumen_deteccion"]["alertas_en_normal_fp"]
        for s in por_corrida.values() if s.get("resumen_deteccion"))

    resumen_global = {
        "corridas_evaluadas": int(len(por_corrida)),
        "corridas_con_anomalia": corridas_detectadas,
        "corridas_sin_anomalia": corridas_limpias,
        "umbral_modelo_q10": umbral_q10,
        "ventanas_evaluadas": total_ventanas,
        "ventanas_alertadas": total_alertas,
        "detecciones_reglas_total": int(reglas.shape[0]),
        "ventanas_test_anomalias": sum(
            s["resumen_deteccion"]["ventanas_test"]
            for s in por_corrida.values() if s.get("resumen_deteccion")),
        "ventanas_fault": ttl_fault,
        "ventanas_normal": ttl_normal,
        "alertas_en_fault": ttl_a_fault,
        "alertas_en_normal_fp": ttl_a_normal,
        "recall": round(ttl_a_fault / ttl_fault, 3) if ttl_fault else None,
        "fpr": round(ttl_a_normal / ttl_normal, 3) if ttl_normal else None,
    }

    informe = {
        "fecha": datetime.date.today().isoformat(),
        "corridas_anomalias": sorted(anom),
        "resumen_deteccion": resumen_global,
        "por_corrida": por_corrida,
        "conclusion": {
            "es_anomalo": bool(corridas_detectadas),
            "corridas_con_alertas": corridas_detectadas,
            "faults_inyectados": ttl_fault,
            "faults_con_reglas": int(sum(
                1 for s in por_corrida.values()
                if s["reglas"]["detecciones"] > 0)),
        },
    }

    # ---- Guardar ----
    ruta_json = os.path.join(DIR_DIAG, "informe_deteccion.json")
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=2)

    # ---- Reporte de consola ----
    log("==========================================================")
    log("DIAGNÓSTICO FINAL DEL DIAGNÓSTICO (RESULTADO)")
    log("==========================================================")
    log(f"Umbral del modelo (q10 scores train): {umbral_q10:.4f}")
    log(f"Corridas evaluadas: {corridas_evaluadas}")
    log(f"Detectadas como anómalas: {corridas_detectadas or '-'}")
    log(f"Sin anomalías: {corridas_limpias or '-'}")
    log(f"Ventanas evaluadas: {total_ventanas} | alertadas: {total_alertas}")
    log(f"Reglas disparadas (total): {total_reglas}")
    for corrida in sorted(por_corrida):
        s = por_corrida[corrida]
        marca = "<<< ANOMALIA DETECTADA" if s["detectado"] else "(sin anomalias)"
        linea = (f"[{s['grupo']}] {corrida}: ventanas={s['ventanas']} "
                 f"alertas_modelo={s['alertas_modelo']} "
                 f"reglas={s['reglas']['detecciones']} {marca}")
        log(linea)
        if s["detectado"]:
            if s["ventanas_alertadas"]:
                log(f"   ventanas alertadas: "
                    f"{s['alertas_modelo']} "
                    f"(ej. {s['ventanas_alertadas'][0]['inicio']} -> "
                    f"{s['ventanas_alertadas'][0]['fin']}, "
                    f"score {s['ventanas_alertadas'][0]['score']})")
            if s["top_variables_alertas"]:
                top = ", ".join(
                    f"{v['variable']}(desv={v['desviacion']})"
                    for v in s["top_variables_alertas"][:5])
                log(f"   variables top: {top}")
            if s["reglas"]["reglas"]:
                log(f"   reglas R1-R7: {s['reglas']['reglas']} "
                    f"({s['reglas']['detecciones']} casos)")
        if s.get("tiene_timeline") and s.get("resumen_deteccion"):
            log(f"   ground truth: {s['resumen_deteccion']}")
            for fault, info in s["por_fault"].items():
                log(f"   - {fault.upper()} [{info['ventana']}]")
                log(f"      reglas: "
                    f"{info['reglas']['reglas_disparadas'] or '-'} "
                    f"({info['reglas']['detecciones_reglas']}) | "
                    f"detección: {info['deteccion']}")
        if s.get("aviso"):
            log(f"   AVISO: {s['aviso']}")
        log("")
    log("==========================================================")
    log(f"Informe completo: {ruta_json}")


if __name__ == "__main__":
    main()