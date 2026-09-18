"""
scoring_automatico.py
=====================

Scoring y DIAGNÓSTICO AUTOMÁTICO de una corrida nueva contra un
modelo IsolationForest ya entrenado.

Flujo:
    1. Carga el dataset final de la corrida (dataset_carga_principales.csv)
       del directorio de diagnóstico.
    2. Normalización RELATIVA por corrida (mediana/MAD robusta).
    3. Construcción de ventanas de VENTANA muestras consecutivas.
    4. Escalado con el StandardScaler guardado (orden de train).
    5. Selección de las features del modelo (features_modelo.csv).
    6. Score por ventana con modelo.decision_function.
    7. Umbrales recomputados sobre las muestras de entrenamiento
       (q10/q05/q01) con el mismo modelo → si score < umbral => ALERTA.
    8. Cruce de cada ventana alertada con las REGLAS DE MOTOR
       (detecciones_reglas.csv): si en ese intervalo temporal se
       disparó alguna regla R1-R7, se adjunta su diagnóstico.

Salidas (en <OUTPUT>/modelado/deteccion/):
    scoring_corrida.csv        scores + alertas por ventana
    informe_deteccion.json     respuesta automática (alerta -> regla -> causa)
"""

import json
import os
import pickle

import joblib
import numpy as np
import pandas as pd

import util_normalizacion

OUTPUT_BASE = os.getenv("STEELNORT_OUTPUT_DIR", r"D:\Steel_Nort\output")
MODELO_DIR = os.getenv("STEELNORT_MODELO_DIR", r"D:\Steel_Nort\modelo_final\modelado")

DATASET_CORRIDA = os.path.join(
    OUTPUT_BASE, "integrado", "dataset_carga_principales.csv"
)
RUTA_TRAIN = os.path.join(MODELO_DIR, "dataset_muestras_train.pkl")
RUTA_SCALER = os.path.join(MODELO_DIR, "deteccion", "scaler.joblib")
RUTA_MODELO = os.path.join(MODELO_DIR, "deteccion", "modelo_isolation_forest.joblib")
RUTA_FEATURES_MODELO = os.path.join(MODELO_DIR, "correlacion", "features_modelo.csv")
RUTA_REGLAS = os.path.join(OUTPUT_BASE, "modelado", "reglas_motor", "detecciones_reglas.csv")
RUTA_TIMELINE_GLOB = os.path.join(OUTPUT_BASE, "*", "anomalias_timeline.csv")
RUTA_SCORING = os.path.join(OUTPUT_BASE, "modelado", "deteccion", "scoring_corrida.csv")
RUTA_INFORME = os.path.join(OUTPUT_BASE, "modelado", "deteccion", "informe_deteccion.json")

VENTANA = 10
COLUMNAS_CONTEXTO = ["timestamp", "run_name", "experiment_id"]
UMBRAL_OPERACION = os.getenv("STEELNORT_UMBRAL", "q05")


def log(msg):
    print(f"[SCORING-DIAG] {msg}", flush=True)


def ventanas_por_corrida(df_corrida, n=VENTANA):
    df_corrida = (
        df_corrida
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    if len(df_corrida) < n:
        return []
    ventanas = []
    for inicio in range(len(df_corrida) - n + 1):
        ventanas.append(df_corrida.iloc[inicio:inicio + n])
    return ventanas


def construir_muestras(datos, features):
    todas_x = []
    todos_run = []
    todas_ventanas = []
    for corrida in sorted(datos["run_name"].unique()):
        df_c = datos[datos["run_name"] == corrida]
        for w in ventanas_por_corrida(df_c):
            x = w[features].to_numpy(dtype="float64")
            todas_x.append(x)
            todos_run.append(corrida)
            todas_ventanas.append({
                "run": corrida,
                "inicio": str(w["timestamp"].iloc[0]),
                "fin": str(w["timestamp"].iloc[-1]),
                "n": len(w),
            })
    if not todas_x:
        return (np.empty((0, VENTANA, len(features))), [], [])
    return np.stack(todas_x), todos_run, todas_ventanas


def cargar_timeline():
    import glob
    rutas = glob.glob(RUTA_TIMELINE_GLOB)
    if not rutas:
        return None
    frames = []
    for r in rutas:
        run = os.path.basename(os.path.dirname(r))
        df = pd.read_csv(r, encoding="utf-8-sig")
        df["run_name"] = run
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def solapamiento(window, fault):
    inicio_w = pd.Timestamp(window["inicio"])
    fin_w = pd.Timestamp(window["fin"])
    inicio_f = pd.Timestamp(fault["inicio"])
    fin_f = pd.Timestamp(fault["fin"])
    return fin_w >= inicio_f and inicio_w <= fin_f


def main():

    if not os.path.exists(RUTA_TRAIN):
        log(f"Falta entrenamiento: {RUTA_TRAIN}")
        return

    with open(RUTA_TRAIN, "rb") as f:
        train = pickle.load(f)

    features_train = train["features"]

    datos = pd.read_csv(DATASET_CORRIDA, encoding="utf-8-sig")
    log(f"Dataset corrida nueva: {len(datos)} filas x {len(datos.columns)} cols")
    log(f"Corridas en dataset: {sorted(datos['run_name'].unique())}")

    datos = util_normalizacion.transformar_relativo(datos, features_train)

    X, runs, ventanas = construir_muestras(datos, features_train)

    if len(X) == 0:
        log("Sin ventanas generadas.")
        return

    scaler = joblib.load(RUTA_SCALER)
    modelo = joblib.load(RUTA_MODELO)

    n_dim, n_ventana, n_feat = X.shape
    X_n = (
        scaler.transform(X.reshape(-1, n_feat))
        .reshape(n_dim, n_ventana, n_feat)
    )

    mant = pd.read_csv(RUTA_FEATURES_MODELO, encoding="utf-8-sig")["columna"].tolist()
    indice = [features_train.index(m) for m in mant]

    flat = lambda x: x[:, :, indice].reshape(x.shape[0], -1)

    X_modelo = flat(X_n)

    scores = modelo.decision_function(X_modelo)

    scores_train = modelo.decision_function(flat(train["X"]))
    umbrales = {
        "q10": float(np.quantile(scores_train, 0.10)),
        "q05": float(np.quantile(scores_train, 0.05)),
        "q01": float(np.quantile(scores_train, 0.01)),
    }
    log(
        "Umbrales (score < umbral => alerta): "
        f"q10={umbrales['q10']:.4f} q05={umbrales['q05']:.4f} q01={umbrales['q01']:.4f}"
    )

    df = pd.DataFrame({
        "idx": range(len(ventanas)),
        "run": runs,
        "inicio": [w["inicio"] for w in ventanas],
        "fin": [w["fin"] for w in ventanas],
        "score": scores,
    })
    for nombre, umbral in umbrales.items():
        df[nombre] = (df["score"] < umbral).astype(int)

    os.makedirs(os.path.dirname(RUTA_SCORING), exist_ok=True)
    df.to_csv(RUTA_SCORING, index=False, encoding="utf-8-sig")

    reglas = None
    if os.path.exists(RUTA_REGLAS):
        reglas = pd.read_csv(RUTA_REGLAS, encoding="utf-8-sig")
        reglas["timestamp"] = pd.to_datetime(reglas["timestamp"])

    timeline = cargar_timeline()

    alertas = df[df[UMBRAL_OPERACION] == 1].copy()
    log(
        f"Ventanas alertadas con umbral {UMBRAL_OPERACION}: "
        f"{len(alertas)} / {len(df)}"
    )

    reglas_resumen = {}
    if reglas is not None:
        for _, r in reglas.iterrows():
            clave = r["regla"]
            reglas_resumen.setdefault(clave, 0)
            reglas_resumen[clave] += 1

    eventos = []
    for _, alerta in alertas.iterrows():

        fault_hit = None
        if timeline is not None:
            faults = timeline[
                timeline["run_name"] == alerta["run"]
            ]
            hits = [
                f["tipo"]
                for _, f in faults.iterrows()
                if solapamiento(alerta, f)
            ]
            fault_hit = ", ".join(sorted(set(hits))) or None

        reglas_de_ventana = []
        if reglas is not None:
            inicio_w = pd.Timestamp(alerta["inicio"])
            fin_w = pd.Timestamp(alerta["fin"])
            window_rules = reglas[
                (reglas["run_name"] == alerta["run"]) &
                (reglas["timestamp"] >= inicio_w) &
                (reglas["timestamp"] <= fin_w)
            ]
            vistos = set()
            for _, r in window_rules.iterrows():
                clave = (
                    r["regla"],
                    str(r["timestamp"]),
                    r.get("detonante", ""),
                    r.get("diagnostico", ""),
                )
                if clave in vistos:
                    continue
                vistos.add(clave)
                reglas_de_ventana.append({
                    "regla": r["regla"],
                    "timestamp": str(r["timestamp"]),
                    "detonante": r.get("detonante", ""),
                    "diagnostico": r.get("diagnostico", ""),
                    "corroborado": r.get("corroborado", ""),
                })

        eventos.append({
            "idx": int(alerta["idx"]),
            "run": alerta["run"],
            "inicio": alerta["inicio"],
            "fin": alerta["fin"],
            "score": round(float(alerta["score"]), 6),
            "umbral": round(umbrales[UMBRAL_OPERACION], 6),
            "fault_solapado": fault_hit,
            "reglas_disparadas": reglas_de_ventana,
            "respuesta": (
                " | ".join(
                    dict.fromkeys(
                        r["diagnostico"]
                        for r in reglas_de_ventana
                        if r["corroborado"] != "sin_pico"
                    ) or [
                        d["diagnostico"]
                        for d in reglas_de_ventana
                    ]
                )
                if reglas_de_ventana
                else "Sin regla disparada: revisar variables de mayor importancia."
            ),
        })

    informe = {
        "informe": "deteccion_automatica",
        "umbral_operacion": UMBRAL_OPERACION,
        "umbrales": umbrales,
        "corridas_evaluadas": sorted(datos["run_name"].unique()),
        "n_ventanas": int(len(df)),
        "n_alertas": int(len(alertas)),
        "reglas_disparadas_totales": reglas_resumen,
        "eventos_alertados": eventos,
    }

    with open(RUTA_INFORME, "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=2)

    print("\n=== DIAGNÓSTICO AUTOMÁTICO ===")
    print(f"Umbral de operación: {UMBRAL_OPERACION}")
    print(f"Alertas: {len(alertas)} de {len(df)} ventanas")

    if timeline is not None:
        tipos_hit = set()
        for e in eventos:
            if e["fault_solapado"]:
                for t in e["fault_solapado"].split(", "):
                    tipos_hit.add(t)
        tipos = sorted(set(timeline["tipo"]))
        print(
            f"Cobertura de fallas inyectadas: {len(tipos_hit)} / {len(tipos)}"
            f" ({', '.join(tipos)})"
        )
    else:
        print("Timeline no encontrado: evaluación sin ground truth.")

    print("\nResumen por ventana alertada (Umbral %s):" % UMBRAL_OPERACION)
    for e in eventos:
        fault = f" | fault={e['fault_solapado']}" if e["fault_solapado"] else ""
        reglas_txt = ", ".join(
            {
                r["regla"]
                + (">" + ("S" if r["corroborado"] == "confirmado" else "P"))
                for r in e["reglas_disparadas"]
            }
        ) or "-"
        print(
            f"  [{e['inicio']} -> {e['fin']}] score={e['score']:.4f}"
            + fault + f" | reglas: {reglas_txt}"
        )
        if e["reglas_disparadas"]:
            diag = e["respuesta"]
            print(f"      -> {diag}")

    log(f"Scoring en: {RUTA_SCORING}")
    log(f"Informe en: {RUTA_INFORME}")


if __name__ == "__main__":
    main()