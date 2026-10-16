"""06_evaluacion.py - Arnes de evaluacion de las 3 pruebas de tesis.

Prueba 1 (Impacto)     : sistema vs umbral estatico (cobertura, MTTD, falsas alarmas).
Prueba 2 (Deteccion)   : precision/recall/F1/AUC + demora operativa por fallo.
Prueba 3 (Diagnostico) : regla R1-R7 que el sistema muestra (variables desviadas)
                         vs el footprint esperado de cada fallo.

Lee los artefactos del pipeline CRISP-DM en training/output y escribe:
    training/output/evaluacion/evaluacion.json
    training/output/evaluacion/EVALUACION.md
"""
import collections
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[3]          # backend/
sys.path.insert(0, str(RAIZ))

from app.ml import reglas as motor_reglas  # noqa: E402
from app.ml.detector import get_detector  # noqa: E402
from app.v2.services.anomalia_v2 import (  # noqa: E402
    REGLAS_PROBABLES,
    _regla_probable,
    _variables_desviadas,
)

OUT = RAIZ / "training" / "output"
ANOM = OUT / "anomalias"
NORMAL = OUT / "baseline"
MODELADO = OUT / "modelado"
EVAL = OUT / "evaluacion"
INFORME = MODELADO / "diagnostico" / "informe_deteccion.json"
RESUMEN = MODELADO / "deteccion" / "validacion" / "resumen_modelos.csv"
AUCS = MODELADO / "deteccion" / "validacion" / "aucs.csv"

UMBRAL_CPU = 90.0
UMBRAL_MEM = 95.0

# footprint esperado de cada fallo (backend/training/nucleo/modeling/05_diagnostico_resultados.py)
FOOTPRINT = {
    "fault1": ["total_writes", "disk_write_per_sec", "transactions_per_sec", "wait_log_count"],
    "fault2": ["total_reads", "disk_read_per_sec", "page_reads", "wait_io_count", "cpu_usr"],
    "fault3": ["cpu_usr", "api_latency_ms", "load1", "active_sessions", "query_count"],
    "fault5": ["transactions_per_sec", "total_writes", "disk_write_per_sec", "wait_log_count"],
    "lockwait": ["lock_waits", "wait_lck_count", "total_locks", "active_requests", "long_queries"],
}

# variable -> regla R1-R7 segun los disparadores de REGLAS_PROBABLES
_REGLAS = {cod: set(trig) for cod, _, trig, _ in REGLAS_PROBABLES}
ESPERADO = {
    f: {cod for cod, trig in _REGLAS.items() if trig & set(vars_)}
    for f, vars_ in FOOTPRINT.items()
}


def leer_metricas(ruta):
    ts, met, val = [], [], []
    for linea in Path(ruta).read_text(encoding="utf-8", errors="ignore").splitlines():
        partes = re.split(r"\s{2,}", linea.strip())
        if len(partes) < 3:
            continue
        try:
            val.append(float(partes[2].strip()))
            met.append(partes[1].strip())
            ts.append(partes[0].strip())
        except ValueError:
            continue
    df = pd.DataFrame({"timestamp": ts, "metric": met, "value": val})
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df.dropna(subset=["timestamp"]).pivot_table(
        index="timestamp", columns="metric", values="value", aggfunc="first"
    )


def corridas_con_timeline():
    for d in sorted(ANOM.iterdir()):
        if d.is_dir() and (d / "anomalias_timeline.csv").is_file() and (d / "metrics.log").is_file():
            yield d


def corridas_normales():
    for d in sorted(NORMAL.iterdir()):
        if d.is_dir() and (d / "metrics.log").is_file():
            yield d


def _cargar_informe():
    return json.loads(INFORME.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# PRUEBA 1 - IMPACTO (sistema vs umbral estatico)
# ----------------------------------------------------------------------
def prueba_impacto():
    dur_normal_h = 0.0
    muestras_normal = 0
    alarmas_base_normal = 0
    for d in corridas_normales():
        df = leer_metricas(d / "metrics.log")
        if df.empty:
            continue
        dur_normal_h += (df.index.max() - df.index.min()).total_seconds() / 3600.0
        muestras_normal += len(df)
        disp = pd.Series(False, index=df.index)
        if "cpu_usr" in df:
            disp |= df["cpu_usr"].fillna(0) >= UMBRAL_CPU
        if "memory_percent" in df:
            disp |= df["memory_percent"].fillna(0) >= UMBRAL_MEM
        alarmas_base_normal += int(disp.sum())

    fault_total = fault_det_base = 0
    mttd_base = []
    for d in corridas_con_timeline():
        df = leer_metricas(d / "metrics.log")
        if df.empty:
            continue
        for _, f in pd.read_csv(d / "anomalias_timeline.csv").iterrows():
            ini = pd.to_datetime(f["inicio"])
            fin = pd.to_datetime(f["fin"])
            bloque = df.loc[(df.index >= ini) & (df.index <= fin)]
            if bloque.empty:
                continue
            fault_total += 1
            disp = pd.Series(False, index=bloque.index)
            if "cpu_usr" in bloque:
                disp |= bloque["cpu_usr"].fillna(0) >= UMBRAL_CPU
            if "memory_percent" in bloque:
                disp |= bloque["memory_percent"].fillna(0) >= UMBRAL_MEM
            if disp.any():
                fault_det_base += 1
                mttd_base.append((bloque.index[disp.values][0] - ini).total_seconds())

    det = prueba_deteccion()

    return {
        "umbral_base": {"cpu_usr": UMBRAL_CPU, "memory_percent": UMBRAL_MEM},
        "horas_normales": round(dur_normal_h, 3),
        "muestras_normales": muestras_normal,
        "sistema": {
            "cobertura": det["tpr_recall"],
            "mttd_s": det["mttd_s_global"],
            "fpr": det["fpr"],
        },
        "umbral_estatico": {
            "cobertura": round(fault_det_base / fault_total, 4) if fault_total else None,
            "mttd_s": round(float(np.mean(mttd_base)), 2) if mttd_base else None,
            "fpr": round(alarmas_base_normal / muestras_normal, 4) if muestras_normal else None,
            "faults_detectados": fault_det_base,
            "faults_total": fault_total,
        },
    }


# ----------------------------------------------------------------------
# PRUEBA 2 - DETECCION (precision + demora)
# ----------------------------------------------------------------------
def prueba_deteccion():
    res = pd.read_csv(RESUMEN)
    fila = res[(res.esquema == "ENSEMBLE_Z") & (res.umbral == "q01")].iloc[0]
    aud = pd.read_csv(AUCS)
    afila = aud[aud["Unnamed: 0"] == "ENSEMBLE_Z"].iloc[0]

    inf = _cargar_informe()
    por_fault = {}
    delays = []
    for _run, info in inf["por_corrida"].items():
        alertas = info.get("ventanas_alertadas") or []
        for fault, fd in (info.get("por_fault") or {}).items():
            if not fd.get("ventana"):
                continue
            ini_s, fin_s = [p.strip() for p in fd["ventana"].split("->")]
            ini, fin = pd.to_datetime(ini_s), pd.to_datetime(fin_s)
            best = None
            for a in alertas:
                if pd.to_datetime(a["inicio"]) <= fin and pd.to_datetime(a["fin"]) >= ini:
                    a_fin = pd.to_datetime(a["fin"])
                    if best is None or a_fin < best:
                        best = a_fin
            if best is not None:
                d = max(0.0, (best - ini).total_seconds())
                delays.append(d)
                por_fault.setdefault(fault, []).append(d)

    return {
        "modelo": "ENSEMBLE_Z",
        "umbral": "q01",
        "matriz": {"tp": int(fila.tp), "fn": int(fila.fn), "fp": int(fila.fp), "tn": int(fila.tn)},
        "tpr_recall": round(float(fila.tpr), 4),
        "fpr": round(float(fila.fpr), 4),
        "precision": round(float(fila.precision), 4),
        "f1": round(float(fila.f1), 4),
        "accuracy": round(float(fila.accuracy), 4),
        "roc_auc": round(float(afila.roc_auc), 4),
        "pr_auc": round(float(afila.pr_auc), 4),
        "mttd_s_global": round(float(np.mean(delays)), 2) if delays else None,
        "mttd_s_por_fault": {k: round(float(np.mean(v)), 2) for k, v in sorted(por_fault.items())},
        "n_faults_con_alerta": len(delays),
    }


# ----------------------------------------------------------------------
# PRUEBA 3 - DIAGNOSTICO
# ----------------------------------------------------------------------
def prueba_diagnostico():
    det = get_detector()
    feats = list(det._features_modelo)

    filas = []
    conf = collections.Counter()
    aciertos = total = 0
    for d in corridas_con_timeline():
        df = leer_metricas(d / "metrics.log")
        for _, f in pd.read_csv(d / "anomalias_timeline.csv").iterrows():
            tipo = str(f["tipo"]).strip()
            ini, fin = pd.to_datetime(f["inicio"]), pd.to_datetime(f["fin"])
            bloque = df.loc[(df.index >= ini) & (df.index <= fin)]
            if bloque.empty:
                continue
            valores = {n: float(bloque[n].astype(float).median()) for n in feats if n in bloque.columns}
            cod, _, _ = _regla_probable({"features": valores})
            top = _variables_desviadas({"features": valores})
            var, zz = (top[0][0], top[0][2]) if top else ("-", 0.0)
            exp = ESPERADO.get(tipo, set())
            total += 1
            ok = cod in exp
            aciertos += 1 if ok else 0
            conf[(tipo, cod)] += 1
            filas.append({
                "corrida": d.name, "fault": tipo, "regla_sistema": cod,
                "esperado": sorted(exp), "variable_top": var,
                "z": round(float(zz), 1), "acierto": bool(ok),
            })

    # evidencias complementarias
    eventos_rules = collections.Counter()
    for d in corridas_con_timeline():
        for nombre in ("events_xe.log", "events.log"):
            p = d / nombre
            if not p.is_file():
                continue
            eventos = []
            for linea in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    eventos.append(json.loads(linea))
                except ValueError:
                    continue
            if any(e.get("duration") is not None or e.get("cpu_time") is not None for e in eventos):
                for x in motor_reglas.evaluar(eventos):
                    eventos_rules[x["regla"]] += 1
                break

    # coincidencia con huella (info ya calculada en informe_deteccion)
    inf = _cargar_informe()
    huella_ok = huella_total = 0
    for info in inf["por_corrida"].values():
        for fd in (info.get("por_fault") or {}).values():
            huella_total += 1
            if fd.get("coincidencia_con_huella"):
                huella_ok += 1

    return {
        "metodo": "regla por variable mas desviada (lo que muestra el sistema)",
        "intervalos": total,
        "aciertos": aciertos,
        "precision_diagnostico": round(aciertos / total, 4) if total else None,
        "esperado_por_fault": {k: sorted(v) for k, v in ESPERADO.items()},
        "matriz_confusion": {
            f"{k[0]}->{k[1]}": v
            for k, v in sorted(conf.items(), key=lambda kv: (kv[0][0], kv[0][1]))
        },
        "reglas_por_eventos": dict(eventos_rules),
        "coincidencia_huella": {
            "faults_con_variable_esperada": huella_ok,
            "faults_total": huella_total,
            "tasa": round(huella_ok / huella_total, 4) if huella_total else None,
        },
        "detalle": filas,
    }


def escribir_markdown(r):
    imp, det, dia = r["impacto"], r["deteccion"], r["diagnostico"]

    def fila_conf(clave):
        tipo, pred = clave.split("->")
        exp = dia["esperado_por_fault"].get(tipo, [])
        return f"| {tipo} | {pred} | {', '.join(exp)} | {dia['matriz_confusion'][clave]} |"

    lineas = [
        "# Evaluacion del sistema (SteelNort_web)",
        "",
        "Generado por `backend/training/nucleo/modeling/06_evaluacion.py`.",
        "",
        "## Prueba 1 - Impacto (sistema vs umbral estatico)",
        "",
        f"- Umbral estatico: `cpu_usr >= {imp['umbral_base']['cpu_usr']}%` o "
        f"`memory_percent >= {imp['umbral_base']['memory_percent']}%`.",
        f"- Corridas normales: {imp['horas_normales']} h ({imp['muestras_normales']} muestras de ~5 s).",
        "",
        "| Metrica | Sistema (ENSEMBLE_Z) | Umbral estatico |",
        "| --- | --- | --- |",
        f"| Cobertura de fallos | {imp['sistema']['cobertura']} | {imp['umbral_estatico']['cobertura']} |",
        f"| MTTD (s) | {imp['sistema']['mttd_s']} | {imp['umbral_estatico']['mttd_s']} |",
        f"| Falsos positivos (FPR) | {imp['sistema']['fpr']} | {imp['umbral_estatico']['fpr']} |",
        "",
        f"El umbral estatico solo cubre {imp['umbral_estatico']['faults_detectados']}/"
        f"{imp['umbral_estatico']['faults_total']} fallos.",
        "",
        "## Prueba 2 - Deteccion (precision + demora)",
        "",
        f"- Matriz: tp={det['matriz']['tp']}, fn={det['matriz']['fn']}, "
        f"fp={det['matriz']['fp']}, tn={det['matriz']['tn']}",
        f"- Precision={det['precision']} · Recall={det['tpr_recall']} · "
        f"F1={det['f1']} · Accuracy={det['accuracy']}",
        f"- FPR={det['fpr']} · ROC-AUC={det['roc_auc']} · PR-AUC={det['pr_auc']}",
        f"- MTTD operativo global: {det['mttd_s_global']} s",
        "",
        "| Fallo | MTTD (s) |",
        "| --- | --- |",
    ]
    for k, v in det["mttd_s_por_fault"].items():
        lineas.append(f"| {k} | {v} |")

    lineas += [
        "",
        "## Prueba 3 - Diagnostico (regla mostrada por el sistema)",
        "",
        f"Metodo: {dia['metodo']}.",
        f"- Aciertos: {dia['aciertos']}/{dia['intervalos']} -> "
        f"precision de diagnostico = **{dia['precision_diagnostico']}**",
        f"- Coincidencia con la variable esperada (footprint): "
        f"{dia['coincidencia_huella']['faults_con_variable_esperada']}/"
        f"{dia['coincidencia_huella']['faults_total']} ({dia['coincidencia_huella']['tasa']})",
        f"- Reglas disparadas por el motor de eventos: {dia['reglas_por_eventos']}",
        "",
        "| Fallo | Regla del sistema | Esperado | Veces |",
        "| --- | --- | --- | --- |",
    ]
    for clave in dia["matriz_confusion"]:
        lineas.append(fila_conf(clave))

    lineas += [
        "",
        "### Limitaciones del diagnostico",
        "",
        "1. `deadlocks_per_sec` (escala ~1) y `total_locks` se disparan en casi todos los fallos,",
        "   y `_regla_probable` evalua R2 primero, por lo que domina la salida.",
        "2. El motor de reglas por eventos necesita `wait_type`, que no esta en las capturas",
        "   (excepto `carga3`), asi que solo puede disparar R3.",
        "3. El ground truth de reglas se deriva del footprint `FOOTPRINT_ESPERADO`;",
        "   es una correspondencia esperada, no una etiqueta observada.",
        "",
        "## Archivos de datos",
        "",
        "- `training/output/modelado/diagnostico/informe_deteccion.json`",
        "- `training/output/modelado/deteccion/validacion/resumen_modelos.csv`",
        "- `training/output/modelado/deteccion/validacion/aucs.csv`",
        "- `training/output/anomalias/<corrida>/anomalias_timeline.csv`",
        "- `training/output/baseline/<corrida>/metrics.log`",
        "",
    ]
    (EVAL / "EVALUACION.md").write_text("\n".join(lineas), encoding="utf-8")


def main():
    EVAL.mkdir(parents=True, exist_ok=True)
    resultado = {
        "impacto": prueba_impacto(),
        "deteccion": prueba_deteccion(),
        "diagnostico": prueba_diagnostico(),
    }
    (EVAL / "evaluacion.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    escribir_markdown(resultado)
    print(f"OK -> {EVAL / 'evaluacion.json'} y {EVAL / 'EVALUACION.md'}")


if __name__ == "__main__":
    main()
