"""
03_diagnostico.py
=================
Informe de detección por corrida: modelo + reglas + ground truth.

Entrada : output/modelado/artefactos_modelo.pkl
          output/modelado/reglas.json
          output/preparado/dataset_steelnort.parquet
          output/anomalias/<corrida>/anomalias_timeline.csv
Salida  : output/modelado/diagnostico.json
"""

import datetime
import json
import os
import pickle

import numpy as np
import pandas as pd

from modelado_config import (
    DIR_MODELADO, DATASET_PRINCIPALES, COLUMNAS_CONTEXTO,
    corridas_anomalia, log,
)

RUTA_ARTEFACTOS = os.path.join(DIR_MODELADO, "artefactos_modelo.pkl")
RUTA_REGLAS     = os.path.join(DIR_MODELADO, "reglas.json")
RUTA_DIAG       = os.path.join(DIR_MODELADO, "diagnostico.json")

MAX_VENTANAS_ALERTADAS = 40
EPS = 1e-9

# Huella esperada por tipo de fallo (para validar atribución)
FOOTPRINT = {
    "fault1":   {"sospecha": "Escrituras al log por INSERTs concurrentes",
                 "vars": ["total_writes", "disk_write_per_sec",
                          "transactions_per_sec", "wait_log_count"]},
    "fault2":   {"sospecha": "Full scan por falta de índice",
                 "vars": ["total_reads", "disk_read_per_sec",
                          "page_reads", "wait_io_count", "cpu_usr"]},
    "fault3":   {"sospecha": "Carga pesada sobre la API",
                 "vars": ["cpu_usr", "api_latency_ms", "load1",
                          "active_sessions", "query_count"]},
    "fault5":   {"sospecha": "Commits concurrentes",
                 "vars": ["transactions_per_sec", "total_writes",
                          "disk_write_per_sec", "wait_log_count"]},
    "lockwait": {"sospecha": "Retención de lock entre sesiones",
                 "vars": ["lock_waits", "wait_lck_count", "total_locks",
                          "active_requests", "long_queries"]},
}


# ==========================================
# Carga de artefactos
# ==========================================
def cargar_artefactos():
    """Lee el pkl con train/test/scores/umbral."""
    with open(RUTA_ARTEFACTOS, "rb") as f:
        art = pickle.load(f)
    return art


def cargar_reglas():
    """Lee reglas.json (catálogo + detecciones)."""
    if not os.path.isfile(RUTA_REGLAS):
        log("Aviso: no existe reglas.json, se continúa sin reglas.")
        return pd.DataFrame(), {}
    with open(RUTA_REGLAS, encoding="utf-8") as f:
        data = json.load(f)
    return pd.DataFrame(data.get("detecciones", [])), data.get("catalogo", {})


def construir_ventanas_alertadas(art):
    """Junta train + test con score y marca de alerta (score < q10)."""
    s_train = art["scores_train"]
    umbral_q10 = float(np.quantile(s_train, 0.10))

    filas = []
    for split, X_runs, ventanas, scores in (
        ("train", art["runs_train"], art["ventanas_train"], art["scores_train"]),
        ("test",  art["runs_test"],  art["ventanas_test"],  art["scores_test"]),
    ):
        for run, vent, score in zip(X_runs, ventanas, scores):
            filas.append({
                "split": split,
                "run": run,
                "inicio": pd.to_datetime(vent["inicio"]),
                "fin": pd.to_datetime(vent["fin"]),
                "score": float(score),
                "alerta": int(score < umbral_q10),
            })
    return pd.DataFrame(filas), umbral_q10


# ==========================================
# Ground truth desde timeline
# ==========================================
def ruta_timeline(corrida):
    """Ruta del anomalias_timeline.csv de una corrida."""
    for sub in ("anomalias", "baseline"):
        p = os.path.join(DIR_MODELADO, "..", sub, corrida,
                         "anomalias_timeline.csv")
        p = os.path.normpath(p)
        if os.path.isfile(p):
            return p
    # fallback: raíz de output
    p = os.path.normpath(os.path.join(DIR_MODELADO, "..", corrida,
                                      "anomalias_timeline.csv"))
    return p if os.path.isfile(p) else None


def etiquetar_fases(w, corrida, timeline):
    """Marca la fase real (del timeline) de cada ventana de la corrida."""
    for i in w[w["run"] == corrida].index:
        ini, fin = w.at[i, "inicio"], w.at[i, "fin"]
        fase = "normal"
        for _, tl in timeline.iterrows():
            if (ini <= pd.to_datetime(tl["fin"])
                    and fin >= pd.to_datetime(tl["inicio"])):
                fase = tl["tipo"]
                break
        w.at[i, "fase"] = fase
    return w


def metricas_deteccion(sub):
    """Confusión ventana a ventana + TPR/FPR por fault."""
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
    for fase in sub.loc[sub["fase"] != "normal", "fase"].unique():
        s = sub[sub["fase"] == fase]
        a = int(s["alerta"].sum())
        por_fault[fase] = {
            "ventanas_total": int(len(s)),
            "ventanas_alertadas": a,
            "tpr": round(a / len(s), 3) if len(s) else None,
        }
    return reporte, por_fault


# ==========================================
# Reglas por corrida / fault
# ==========================================
def reglas_por_corrida(reglas):
    out = {}
    if reglas.empty:
        return out
    for run, g in reglas.groupby("run_name"):
        out[str(run)] = {
            "detecciones": int(len(g)),
            "por_regla": g["regla"].value_counts().to_dict(),
            "reglas": sorted(set(g["regla"])),
        }
    return out


def reglas_por_fault(reglas, corrida, timeline):
    reglas_run = reglas[reglas["run_name"] == corrida].copy()
    if not reglas_run.empty:
        reglas_run["timestamp"] = pd.to_datetime(reglas_run["timestamp"])
    out = {}
    for _, tl in timeline.iterrows():
        lineas = reglas_run[
            (reglas_run["timestamp"] >= pd.to_datetime(tl["inicio"]))
            & (reglas_run["timestamp"] <= pd.to_datetime(tl["fin"]))
        ]
        out[tl["tipo"]] = {
            "detecciones_reglas": int(len(lineas)),
            "reglas_disparadas": ("normal" if lineas.empty
                                  else "-".join(sorted(set(lineas["regla"])))),
            "conteo_por_regla": lineas["regla"].value_counts().to_dict(),
        }
    return out


# ==========================================
# Atribución de variables (estilo DBPA)
# ==========================================
def desviacion_robusta(anormal, normal):
    """|Δmediana| normalizada por MAD del baseline."""
    med = float(normal.median()) if len(normal) else np.nan
    mad = float(np.median(np.abs(normal - med))) if len(normal) else np.nan
    escala = 1.4826 * mad + EPS
    if not np.isfinite(med):
        return 0.0
    return abs(float(anormal.median()) - med) / escala


def top_variables(anomalo, normal, features, maximo=10):
    punt = []
    for var in features:
        if var not in anomalo.columns:
            continue
        z = desviacion_robusta(anomalo[var], normal[var])
        if z > 0:
            punt.append({"variable": var, "desviacion": round(z, 3)})
    punt.sort(key=lambda x: x["desviacion"], reverse=True)
    return punt[:maximo]


def atribuir_variables(c_run, features, timeline):
    """Top variables desviadas por fault vs el tramo normal de la corrida."""
    normal = c_run[c_run["fase"] == "normal"]
    out = {}
    for _, tl in timeline.iterrows():
        anom = c_run[c_run["fase"] == tl["tipo"]]
        out[tl["tipo"]] = ([] if anom.empty else
                           top_variables(anom, normal, features))
    return out


# ==========================================
# Main
# ==========================================
def main():
    for r in (RUTA_ARTEFACTOS, DATASET_PRINCIPALES):
        if not os.path.isfile(r):
            log(f"Falta {r}. Ejecuta antes 01_entrenamiento.py.")
            return

    art = cargar_artefactos()
    w, umbral_q10 = construir_ventanas_alertadas(art)
    df = pd.read_parquet(DATASET_PRINCIPALES)
    features = [c for c in df.columns if c not in COLUMNAS_CONTEXTO]

    reglas, catalogo = cargar_reglas()
    reglas_por_run = reglas_por_corrida(reglas)

    anom = corridas_anomalia()
    presentes = set(w["run"])
    anom = {c: ruta_timeline(c) for c in anom if c in presentes}
    anom = {c: r for c, r in anom.items() if r}

    log(f"Corridas con timeline: {sorted(anom)}")

    corridas_eval = sorted(set(w["run"]) | set(reglas_por_run) | set(anom))

    por_corrida = {}
    for corrida in corridas_eval:
        grupo = "anomalias" if corrida in anom else "baseline"
        w_run = w[w["run"] == corrida].copy()
        alertas = w_run[w_run["alerta"] == 1].sort_values("score")

        sec = {
            "grupo": grupo,
            "ventanas": int(len(w_run)),
            "alertas_modelo": int(len(alertas)),
        }
        sec["fraccion_alertas_modelo"] = (
            round(sec["alertas_modelo"] / sec["ventanas"], 4)
            if sec["ventanas"] else 0.0)

        rg = reglas_por_run.get(corrida, {})
        sec["reglas"] = {
            "detecciones": rg.get("detecciones", 0),
            "por_regla": rg.get("por_regla", {}),
            "reglas": rg.get("reglas", []),
        }
        sec["detectado"] = bool(sec["alertas_modelo"] > 0
                                or sec["reglas"]["detecciones"] > 0)
        sec["ventanas_alertadas"] = [
            {"inicio": str(r["inicio"]), "fin": str(r["fin"]),
             "score": round(float(r["score"]), 4)}
            for _, r in alertas.head(MAX_VENTANAS_ALERTADAS).iterrows()
        ]

        # Ground truth (si hay timeline)
        sec["tiene_timeline"] = corrida in anom
        if corrida in anom:
            timeline = pd.read_csv(anom[corrida], encoding="utf-8-sig")
            w = etiquetar_fases(w, corrida, timeline)
            w_run = w[w["run"] == corrida]
            metricas, por_fault = metricas_deteccion(w_run)
            sec["resumen_deteccion"] = metricas

            # Atribución de variables por tramo
            c_run = df[df["run_name"] == corrida].copy()
            c_run["timestamp"] = pd.to_datetime(c_run["timestamp"])
            c_run["fase"] = "normal"
            for _, tl in timeline.iterrows():
                mask = ((c_run["timestamp"] >= pd.to_datetime(tl["inicio"]))
                        & (c_run["timestamp"] <= pd.to_datetime(tl["fin"])))
                c_run.loc[mask, "fase"] = tl["tipo"]
            atrib = atribuir_variables(c_run, features, timeline)

            reglas_fault = reglas_por_fault(reglas, corrida, timeline)

            sec["por_fault"] = {}
            for _, tl in timeline.iterrows():
                fault = tl["tipo"]
                fp = FOOTPRINT.get(fault, {})
                vars_top = atrib.get(fault, [])
                coinciden = [v["variable"] for v in vars_top[:6]
                             if v["variable"] in fp.get("vars", [])]
                sec["por_fault"][fault] = {
                    "ventana": f"{tl['inicio']} -> {tl['fin']}",
                    "sospecha_esperada": fp.get("sospecha", ""),
                    "variables_causantes_top": vars_top[:6],
                    "coincidencia_con_huella": coinciden,
                    "reglas": reglas_fault.get(fault, {}),
                    "deteccion": por_fault.get(fault, {}),
                }

            if metricas["ventanas_fault"] == 0:
                sec["aviso"] = ("Timeline no cruza las ventanas reales: "
                                "no se puede calcular TPR con ground truth.")

        por_corrida[corrida] = sec

    # --- Resumen global ---
    detectadas = sorted(c for c, s in por_corrida.items() if s["detectado"])
    limpias = sorted(c for c, s in por_corrida.items() if not s["detectado"])

    ttl_fault = sum(s["resumen_deteccion"]["ventanas_fault"]
                    for s in por_corrida.values() if s.get("resumen_deteccion"))
    ttl_normal = sum(s["resumen_deteccion"]["ventanas_normal"]
                     for s in por_corrida.values() if s.get("resumen_deteccion"))
    ttl_a_fault = sum(s["resumen_deteccion"]["alertas_en_fault"]
                      for s in por_corrida.values() if s.get("resumen_deteccion"))
    ttl_a_normal = sum(s["resumen_deteccion"]["alertas_en_normal_fp"]
                       for s in por_corrida.values() if s.get("resumen_deteccion"))

    resumen = {
        "corridas_evaluadas": int(len(por_corrida)),
        "corridas_con_anomalia": detectadas,
        "corridas_sin_anomalia": limpias,
        "umbral_modelo_q10": umbral_q10,
        "ventanas_evaluadas": int(len(w)),
        "ventanas_alertadas": int(w["alerta"].sum()),
        "detecciones_reglas_total": int(len(reglas)),
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
        "catalogo_reglas": catalogo,
        "resumen_deteccion": resumen,
        "por_corrida": por_corrida,
        "conclusion": {
            "es_anomalo": bool(detectadas),
            "corridas_con_alertas": detectadas,
            "faults_inyectados": ttl_fault,
            "faults_con_reglas": int(sum(
                1 for s in por_corrida.values()
                if s["reglas"]["detecciones"] > 0)),
        },
    }

    with open(RUTA_DIAG, "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=2)
    log(f"Informe: {RUTA_DIAG}")
    log(f"Umbral q10={umbral_q10:.4f} | "
        f"detectadas={detectadas or '-'} | limpias={limpias or '-'} | "
        f"alertas={resumen['ventanas_alertadas']}/{resumen['ventanas_evaluadas']} | "
        f"reglas R1-R7={resumen['detecciones_reglas_total']}")


if __name__ == "__main__":
    main()