"""
03_evaluar_oe3.py
=================
Re-mide los indicadores de OE3 con el modelo FINAL desplegado (bundle
produccion = ENSEMBLE_LOF_ELL), no con el candidato viejo.

  I-3.1 clasificacion por tipo        -> regla R1-R7 emitida vs categoria esperada
  I-3.2 coincidencia de severidad     -> severidad emitida (sin ground truth: distribucion)
  I-3.3 efectividad del diagnostico   -> variables detectadas vs huella esperada

Metodo: alimenta el Detector REAL (mismo codigo del backend) con las muestras
crudas del dataset y reusa el diagnostico nuevo (`_variables_desviadas`,
`_regla_probable`, `_severidad`). La capa zonal se apaga para medir la
decision por ventana (criterio: score < umbral q01).

Entrada : output/preparado/dataset_steelnort.parquet
          output/anomalias/<run>/anomalias_timeline.csv
          output/modelado/produccion/*        (bundle desplegado)
Salida  : output/modelado/indicadores/diagnostico_final.json

Uso:
    python indicadores/03_evaluar_oe3.py
"""

import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Config del modelado (padres[1] = tools/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelado_config import (                       # noqa: E402
    DATASET_PRINCIPALES, DIR_MODELADO, OUTPUT_BASE, VARIABLES_MODELO, log,
)

# Backend en sys.path para importar el detector y el servicio de diagnostico.
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

DIR_PRODUCCION = os.path.join(DIR_MODELADO, "produccion")
DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")

# Huella esperada por tipo de fallo (la misma que 03_diagnostico.py).
FOOTPRINT = {
    "fault1":   {"vars": ["total_writes", "disk_write_per_sec",
                          "transactions_per_sec", "wait_log_count"]},
    "fault2":   {"vars": ["total_reads", "disk_read_per_sec",
                          "page_reads", "wait_io_count", "cpu_usr"]},
    "fault3":   {"vars": ["cpu_usr", "api_latency_ms", "load1",
                          "active_sessions", "query_count"]},
    "fault5":   {"vars": ["transactions_per_sec", "total_writes",
                          "disk_write_per_sec", "wait_log_count"]},
    "lockwait": {"vars": ["lock_waits", "wait_lck_count", "total_locks",
                          "active_requests", "long_queries"]},
}

# Categoria R1-R7 esperada por tipo de fallo (varias aceptables donde aplica).
# Es un mapeo de criterio, no una verdad dura: se documenta y se puede ajustar.
MAPA_TIPO = {
    "fault1":   {"I/O fisico"},
    "fault5":   {"I/O fisico"},
    "fault2":   {"I/O fisico", "plan/indices"},
    "fault3":   {"CPU", "cliente lento"},
    "lockwait": {"Bloqueos"},
}


# ==========================================
# Carga
# ==========================================
def cargar_timelines():
    """Timelines de anomalias: run_name, tipo, inicio, fin."""
    rutas = glob.glob(os.path.join(OUTPUT_BASE, "anomalias", "*",
                                   "anomalias_timeline.csv"))
    if not rutas:
        return pd.DataFrame(columns=["run_name", "tipo", "inicio", "fin"])
    tl = pd.concat([
        pd.read_csv(r, encoding="utf-8-sig").assign(
            run_name=os.path.basename(os.path.dirname(r)))
        for r in rutas], ignore_index=True)
    tl["inicio"] = pd.to_datetime(tl["inicio"])
    tl["fin"] = pd.to_datetime(tl["fin"])
    return tl


def construir_detector():
    """Detector real apuntado al bundle de produccion (LOF+ELLIPTIC)."""
    # Debe ir ANTES de importar el detector: lee el entorno al cargar el modulo.
    os.environ["STEELNORT_ZONAL"] = "0"       # decision por ventana, sin consenso
    os.environ["STEELNORT_ENSEMBLE"] = ""     # auto -> LOF+ELL (el bundle)
    os.environ["ML_ARTIFACTS_DIR"] = DIR_PRODUCCION
    os.environ["ML_TRAIN_PKL"] = os.path.join(DIR_PRODUCCION,
                                              "dataset_muestras_train.pkl")
    from app.tools.motor.detector import get_detector
    return get_detector()


def diagnosticar(det, pred):
    """Reusa el diagnostico nuevo del backend sobre una prediccion."""
    from app.v2.services.anomalia_v2 import (
        _regla_probable, _severidad, _variables_desviadas,
    )
    desviadas = _variables_desviadas(pred)
    codigo, etiqueta, _ = _regla_probable(pred)
    severidad = _severidad(det, pred["score"], eventos=None, regla=codigo)
    return desviadas, codigo, etiqueta, severidad


# ==========================================
# Main
# ==========================================
def main():
    for r in (DATASET_PRINCIPALES,
              os.path.join(DIR_PRODUCCION, "dataset_muestras_train.pkl")):
        if not os.path.isfile(r):
            log(f"Falta {r}.")
            return

    tl = cargar_timelines()
    if tl.empty:
        log("Sin timelines de anomalias.")
        return

    ds = pd.read_parquet(DATASET_PRINCIPALES)
    det = construir_detector()
    from app.v2.services.anomalia_v2 import _variables_desviadas
    q01 = det.umbrales.get("q01", 0.0)
    log(f"Detector: {det.modo} | ventana={det.ventana} | umbral q01={q01:.4f}")

    por_fault = []
    for run in sorted(tl["run_name"].unique()):
        sub = ds[ds["run_name"] == run].sort_values("timestamp")
        if sub.empty:
            log(f"Aviso: {run} no esta en el dataset.")
            continue

        muestras = []
        for _, fila in sub.iterrows():
            muestra = {v: (0.0 if pd.isna(fila[v]) else float(fila[v]))
                       for v in VARIABLES_MODELO}
            muestra["fecha_str"] = str(fila["timestamp"])
            muestras.append(muestra)

        resultados = det.evaluar_lote(run, muestras)
        ventanas = []
        for out in resultados:
            i = out["indice"]
            ventanas.append({
                "ini": pd.Timestamp(sub.iloc[i - det.ventana + 1]["timestamp"]),
                "fin": pd.Timestamp(sub.iloc[i]["timestamp"]),
                "pred": out,
            })

        for _, f in tl[tl["run_name"] == run].iterrows():
            idx = [w for w in ventanas
                   if w["ini"] <= f["fin"] and w["fin"] >= f["inicio"]]
            alertadas = sorted([w for w in idx if w["pred"]["es_anomalia"]],
                               key=lambda w: w["fin"])
            detectado = bool(alertadas)

            # Diagnostico del EVENTO: variables que el sistema reporta a lo
            # largo de TODAS las ventanas alertadas. La alerta se completa
            # mientras el evento sigue (ver v2/services/anomalia_v2.py,
            # ``_ampliar_alerta``), no solo en la primera ventana.
            # Se guarda tambien la version de la primera ventana por trazabilidad.
            vars_top, codigo, etiqueta, severidad = [], "RML", "Cambio general", None
            coincide, coincide_primera, ttfa = [], [], None
            if detectado:
                elegida = alertadas[0]
                pred = elegida["pred"]
                desviadas, codigo, etiqueta, severidad = diagnosticar(det, pred)
                vars_top = [v for v, _, _ in desviadas[:6]]
                esperadas = set(FOOTPRINT.get(f["tipo"], {}).get("vars", []))
                coincide_primera = [v for v in vars_top if v in esperadas]
                vars_evento = []
                for w in alertadas:
                    for v, _, _ in _variables_desviadas(w["pred"])[:6]:
                        if v not in vars_evento:
                            vars_evento.append(v)
                coincide = [v for v in vars_evento if v in esperadas]
                ttfa = round((elegida["fin"] - f["inicio"]).total_seconds(), 1)

            por_fault.append({
                "run": run, "fault": f["tipo"],
                "detectado_modelo": detectado,
                "ttfa_seg": ttfa,
                "regla": codigo, "categoria": etiqueta,
                "severidad": severidad,
                "variables_top": vars_top[:3],
                "coincide_huella": coincide,
                "coincide_huella_primera_ventana": coincide_primera,
            })

    # ---- Resumen ----
    n = len(por_fault)
    detectados = [p for p in por_fault if p["detectado_modelo"]]
    con_huella = [p for p in detectados if p["coincide_huella"]]
    con_huella_primera = [p for p in detectados
                          if p["coincide_huella_primera_ventana"]]
    con_tipo = [p for p in detectados if p["fault"] in MAPA_TIPO]
    tipo_ok = [p for p in con_tipo if p["categoria"] in MAPA_TIPO[p["fault"]]]
    ttfas = [p["ttfa_seg"] for p in detectados if p["ttfa_seg"] is not None]

    sev_dist = {}
    for p in detectados:
        sev_dist[p["severidad"]] = sev_dist.get(p["severidad"], 0) + 1

    resumen = {
        "modelo": det.modo,
        "umbral": "q01",
        "faults": n,
        "detectados_modelo": len(detectados),
        "tasa_deteccion": round(len(detectados) / n, 4) if n else 0.0,
        "ttfa_medio_seg": round(float(np.mean(ttfas)), 1) if ttfas else None,
        "ttfa_mediana_seg": round(float(np.median(ttfas)), 1) if ttfas else None,
        # I-3.3 efectividad del diagnostico (huella de variables). El valor
        # oficial es el del EVENTO (todas las ventanas alertadas); la primera
        # ventana se conserva como referencia de trazabilidad.
        "con_coincidencia_huella": len(con_huella),
        "efectividad_diagnostico": (round(len(con_huella) / len(detectados), 4)
                                    if detectados else 0.0),
        "meta_efectividad_diagnostico": 0.85,
        "cumple_efectividad_diagnostico": (
            bool(len(con_huella) / len(detectados) >= 0.85) if detectados else False),
        "con_coincidencia_huella_primera_ventana": len(con_huella_primera),
        "efectividad_diagnostico_primera_ventana": (
            round(len(con_huella_primera) / len(detectados), 4)
            if detectados else 0.0),
        # I-3.1 clasificacion por tipo (regla R1-R7 vs categoria esperada)
        "evaluados_tipo": len(con_tipo),
        "tipo_correcto": len(tipo_ok),
        "precision_tipo": (round(len(tipo_ok) / len(con_tipo), 4)
                           if con_tipo else None),
        # I-3.2 severidad: sin ground truth, solo distribucion de lo emitido
        "distribucion_severidad": sev_dist,
    }

    os.makedirs(DIR_VAL, exist_ok=True)
    ruta = os.path.join(DIR_VAL, "diagnostico_final.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"resumen": resumen, "por_fault": por_fault},
                  fh, ensure_ascii=False, indent=2, default=str)

    print("\n=== OE3 CON EL MODELO FINAL ===")
    print(f"  modelo={det.modo} q01 | faults={n} "
          f"detectados={len(detectados)} ({resumen['tasa_deteccion']:.2%})")
    print(f"  I-3.3 efectividad diagnostico (huella, evento): "
          f"{resumen['efectividad_diagnostico']:.2%} "
          f"({len(con_huella)}/{len(detectados)}) "
          f"{'CUMPLE' if resumen['cumple_efectividad_diagnostico'] else 'NO CUMPLE'} "
          f"meta >= 85 %")
    print(f"       (primera ventana: "
          f"{resumen['efectividad_diagnostico_primera_ventana']:.2%} "
          f"({len(con_huella_primera)}/{len(detectados)}))")
    print(f"  I-3.1 precision por tipo: "
          f"{resumen['precision_tipo']} ({len(tipo_ok)}/{len(con_tipo)})")
    print(f"  I-3.2 severidad emitida: {sev_dist}  "
          f"(sin ground truth: solo distribucion)")
    print(f"  TTFA medio={resumen['ttfa_medio_seg']}s "
          f"mediana={resumen['ttfa_mediana_seg']}s")
    print(f"\nInforme: {ruta}")


if __name__ == "__main__":
    main()
