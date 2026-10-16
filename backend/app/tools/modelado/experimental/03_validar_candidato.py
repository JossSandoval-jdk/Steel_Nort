"""
03_validar_candidato.py
=======================
Validación integral de candidatos (ISO, COPOD, LOF, OCSVM, ELLIPTIC y ensambles).

OJO con las etiquetas: este harness marca fallo SOLO con `marcar_fault`, que
mira `anomalias_timeline.csv`. Eso subcuenta las anomalías: las corridas live
declaradas anomalía (origen.json `es_carga_normal = false`) no tienen timeline
y quedan contadas como normales. El resultado son métricas infladas.

La evaluación válida es `indicadores/01_validar_honesto.py`, que usa la etiqueta nativa
(`modelado/etiquetas.py`) y un protocolo dejar-una-corrida-fuera. Este script
se mantiene para comparar contra v1, no como fuente de verdad.

Stages (uno por `--stage`):
    metrics     Tabla por umbral + AUC de todos los esquemas.
    seeds       Estabilidad con N semillas (media ± desv).
    vars        Sensibilidad 15/17/19 variables.
    freeze      Congela el candidato + registro.
    oper        Detección y tiempo hasta 1ª alerta (por candidato y por fault).
    diagnostico % de faults diagnosticados (modelo + reglas + atribución).
    calidad     Auditoría de ceros y NaN por variable.
    errores     FN/FP por tipo + contribución PCA por variable.
    robustez    Ruido, NaN, cambio de escala.
    latencia    Micro-benchmark de inferencia.

Entrada : output/modelado/artefactos_modelo.pkl
Salida  : output/modelado/validacion/<stage>.json

Uso:
    python experimental/03_validar_candidato.py --stage metrics
    python experimental/03_validar_candidato.py --stage todo
"""

import argparse
import glob
import json
import os
import pickle
import sys
import time
import warnings
from pathlib import Path

# Suprimir advertencias numéricas esperadas en benchmarking (covarianza singular y metric warnings)
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.covariance import EllipticEnvelope
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM
from pyod.models.copod import COPOD

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelado_config import (                       # noqa: E402
    COLUMNAS_CONTEXTO, DATASET_PRINCIPALES, DIR_MODELADO, OUTPUT_BASE,
    VENTANA, SEED, VARIABLES_MODELO, log,
)

QQ = {"q10": 0.10, "q05": 0.05, "q01": 0.01}
ESQUEMAS = ["ISOLATION_FOREST", "COPOD", "LOF", "OCSVM", "ELLIPTIC"]
TARGET_FPR = 0.0174
N_SEEDS = 20

DIR_VAL = os.path.join(DIR_MODELADO, "validacion")

# Máscara de ventanas de test que cruzan un fault del timeline (se fija en main()).
MASK_FAULT = None


# ==========================================
# Carga y helpers
# ==========================================
def cargar_artefactos():
    ruta = os.path.join(DIR_MODELADO, "artefactos_modelo.pkl")
    if not os.path.exists(ruta):
        log(f"Falta {ruta}. Ejecuta modelado/01_entrenamiento.py.")
        return None
    with open(ruta, "rb") as f:
        return pickle.load(f)


def indices_modelo(features):
    presentes = [c for c in VARIABLES_MODELO if c in features]
    return [features.index(c) for c in presentes]


def aplanar(X, indice):
    return X[:, :, indice].reshape(X.shape[0], -1)


def marcar_fault(art):
    """Ventanas de test que cruzan un fault del timeline (regla de v1)."""
    rutas = glob.glob(os.path.join(OUTPUT_BASE, "anomalias", "*",
                                   "anomalias_timeline.csv"))
    if rutas:
        tl = pd.concat([pd.read_csv(r, encoding="utf-8-sig")
                        .assign(run_name=os.path.basename(os.path.dirname(r)))
                        for r in rutas], ignore_index=True)
        tl["inicio"] = pd.to_datetime(tl["inicio"])
        tl["fin"] = pd.to_datetime(tl["fin"])
    else:
        tl = pd.DataFrame(columns=["run_name", "inicio", "fin"])

    mask = np.zeros(len(art["ventanas_test"]), dtype=bool)
    for i, w in enumerate(art["ventanas_test"]):
        g = tl[tl["run_name"] == w["run"]]
        if g.empty:
            continue
        ini, fin = pd.Timestamp(w["inicio"]), pd.Timestamp(w["fin"])
        mask[i] = bool(((ini <= g["fin"]) & (fin >= g["inicio"])).any())
    return mask


def cargar_timelines():
    """Timelines de las corridas de anomalías: run_name, tipo, inicio, fin."""
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


def crear_modelo(nombre, seed=SEED):
    if nombre == "ISOLATION_FOREST":
        return IsolationForest(random_state=seed, contamination="auto", n_jobs=-1)
    if nombre == "COPOD":
        return COPOD(contamination=0.05)
    if nombre == "LOF":
        return LocalOutlierFactor(n_neighbors=20, novelty=True, contamination=0.05)
    if nombre == "OCSVM":
        return OneClassSVM(nu=0.05, kernel="rbf", gamma="scale")
    if nombre == "ELLIPTIC":
        return EllipticEnvelope(contamination=0.05, random_state=seed)
    raise ValueError(nombre)


def scores(modelo, nombre, X):
    """Convención: menor = más anómalo (solo COPOD invierte)."""
    s = modelo.decision_function(X)
    return -s if nombre == "COPOD" else s


def copod_test(cop, X_test):
    """Score de test de COPOD puntuando SOLO el lote evaluado (mask).

    COPOD reajusta la ECDF con train+batch: el score depende del lote. Se
    puntúa solo el lote evaluado para reproducir a v1 (menor = más anómalo);
    las ventanas fuera del lote quedan en +inf (nunca anómalas).
    """
    if MASK_FAULT is None:
        return -cop.decision_function(X_test)
    s = np.full(len(X_test), np.inf)
    s[MASK_FAULT] = -cop.decision_function(X_test[MASK_FAULT])
    return s


def scores_full(nombre, X_train, X_test, seed=SEED, mask_batch=True):
    """Scores train/test ajustando el modelo en TODO el train (sin LOO).

    Con mask_batch=True, COPOD se puntúa solo sobre el lote evaluado
    (ventanas que cruzan un fault), como en v1.
    """
    if nombre == "ENSEMBLE_Z":
        iso = IsolationForest(random_state=seed, contamination="auto",
                              n_jobs=-1).fit(X_train)
        cop = COPOD(contamination=0.05).fit(X_train)
        s_i = iso.decision_function(X_train)
        s_c = -cop.decision_function(X_train)
        mu_i, sd_i = s_i.mean(), s_i.std() + 1e-9
        mu_c, sd_c = s_c.mean(), s_c.std() + 1e-9
        s_i_te = iso.decision_function(X_test)
        s_c_te = (copod_test(cop, X_test) if mask_batch
                  else -cop.decision_function(X_test))
        z_train = ((s_i - mu_i) / sd_i + (s_c - mu_c) / sd_c) / 2
        z_test = ((s_i_te - mu_i) / sd_i + (s_c_te - mu_c) / sd_c) / 2
        return z_train, z_test
    if nombre == "ENSEMBLE_LOF_ELL":
        ma = crear_modelo("LOF", seed).fit(X_train)
        mb = crear_modelo("ELLIPTIC", seed).fit(X_train)
        a_tr, b_tr = scores(ma, "LOF", X_train), scores(mb, "ELLIPTIC", X_train)
        a_te, b_te = scores(ma, "LOF", X_test), scores(mb, "ELLIPTIC", X_test)
        z_tr = ((a_tr - a_tr.mean()) / (a_tr.std() + 1e-9)
                + (b_tr - b_tr.mean()) / (b_tr.std() + 1e-9)) / 2
        z_te = ((a_te - a_tr.mean()) / (a_tr.std() + 1e-9)
                + (b_te - b_tr.mean()) / (b_tr.std() + 1e-9)) / 2
        return z_tr, z_te
    m = crear_modelo(nombre, seed).fit(X_train)
    s_test = (copod_test(m, X_test) if (nombre == "COPOD" and mask_batch)
              else scores(m, nombre, X_test))
    return scores(m, nombre, X_train), s_test


def metricas(tp, fn, fp, tn):
    n_fault, n_norm = tp + fn, fp + tn
    tpr = tp / n_fault if n_fault else 0.0
    fpr = fp / n_norm if n_norm else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = (2 * prec * tpr / (prec + tpr)) if (prec + tpr) else 0.0
    return {"tp": int(tp), "fn": int(fn), "fp": int(fp), "tn": int(tn),
            "tpr": round(tpr, 4), "fpr": round(fpr, 4),
            "precision": round(prec, 4), "f1": round(f1, 4)}


def guardar(nombre, data):
    os.makedirs(DIR_VAL, exist_ok=True)
    ruta = os.path.join(DIR_VAL, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    log(f"Guardado: {ruta}")


# ==========================================
# Evaluación LOO de un esquema
# ==========================================
def evaluar_esquema(nombre, X_train, runs_train, X_test, seed=SEED):
    """LOO sobre normales + test de fallos. Devuelve (filas, auc, scores)."""
    n_norm = len(X_train)
    mask = MASK_FAULT if MASK_FAULT is not None else np.ones(len(X_test), dtype=bool)
    n_fault = int(mask.sum())
    alertas_norm = {q: np.zeros(n_norm, dtype=bool) for q in QQ}

    for corrida in sorted(set(runs_train)):
        idx_c = [i for i, r in enumerate(runs_train) if r == corrida]
        idx_tr = [i for i in range(n_norm) if i not in idx_c]

        m = crear_modelo(nombre, seed).fit(X_train[idx_tr])
        s_fold = scores(m, nombre, X_train[idx_tr])
        s_c = scores(m, nombre, X_train[idx_c])
        for q, p in QQ.items():
            thr = np.quantile(s_fold, p)
            alertas_norm[q][idx_c] = s_c < thr

    m_full = crear_modelo(nombre, seed).fit(X_train)
    s_train = scores(m_full, nombre, X_train)
    # COPOD depende del lote -> solo se puntúa el lote evaluado (como v1).
    s_test = (copod_test(m_full, X_test) if nombre == "COPOD"
              else scores(m_full, nombre, X_test))

    filas = []
    for q, p in QQ.items():
        thr = float(np.quantile(s_train, p))
        tp = int((s_test[mask] < thr).sum())
        fp = int(alertas_norm[q].sum())
        filas.append({"esquema": nombre, "umbral": q,
                      **metricas(tp, n_fault - tp, fp, n_norm - fp)})

    auc = None
    if n_fault > 0:
        # AUC solo es válido si la máscara tiene las dos clases. Con una sola
        # clase, roc_auc_score devuelve NaN y average_precision_score 1.0
        # (no informativos): se emiten como null en vez de inventar 1.0.
        if len(np.unique(mask)) > 1:
            y = mask.astype(int)
            s = -s_test
            try:
                auc = {"esquema": nombre,
                       "roc_auc": round(float(roc_auc_score(y, s)), 4),
                       "pr_auc": round(float(average_precision_score(y, s)), 4)}
            except Exception:
                auc = {"esquema": nombre, "roc_auc": None, "pr_auc": None}
        else:
            auc = {"esquema": nombre, "roc_auc": None, "pr_auc": None}
    return filas, auc, (s_train, s_test)


def evaluar_ensamble(X_train, runs_train, X_test, seed=SEED, mask_batch=True):
    """ENSEMBLE_Z: media de z-scores de ISO y COPOD."""
    n_norm = len(X_train)
    mask = MASK_FAULT if MASK_FAULT is not None else np.ones(len(X_test), dtype=bool)
    n_fault = int(mask.sum())
    alertas_norm = {q: np.zeros(n_norm, dtype=bool) for q in QQ}

    for corrida in sorted(set(runs_train)):
        idx_c = [i for i, r in enumerate(runs_train) if r == corrida]
        idx_tr = [i for i in range(n_norm) if i not in idx_c]

        iso = IsolationForest(random_state=seed, contamination="auto",
                              n_jobs=-1).fit(X_train[idx_tr])
        cop = COPOD(contamination=0.05).fit(X_train[idx_tr])
        s_i_f = iso.decision_function(X_train[idx_tr])
        s_i_c = iso.decision_function(X_train[idx_c])
        s_c_f = -cop.decision_function(X_train[idx_tr])
        s_c_c = -cop.decision_function(X_train[idx_c])

        z_f = (s_i_f - s_i_f.mean()) / (s_i_f.std() + 1e-9) \
            + (s_c_f - s_c_f.mean()) / (s_c_f.std() + 1e-9)
        z_c = (s_i_c - s_i_f.mean()) / (s_i_f.std() + 1e-9) \
            + (s_c_c - s_c_f.mean()) / (s_c_f.std() + 1e-9)
        z_f, z_c = z_f / 2, z_c / 2

        for q, p in QQ.items():
            thr = np.quantile(z_f, p)
            alertas_norm[q][idx_c] = z_c < thr

    iso = IsolationForest(random_state=seed, contamination="auto",
                          n_jobs=-1).fit(X_train)
    cop = COPOD(contamination=0.05).fit(X_train)
    s_i = iso.decision_function(X_train)
    s_c = -cop.decision_function(X_train)
    z_train = ((s_i - s_i.mean()) / (s_i.std() + 1e-9)
               + (s_c - s_c.mean()) / (s_c.std() + 1e-9)) / 2

    s_i_te = iso.decision_function(X_test)
    s_c_te = (copod_test(cop, X_test) if mask_batch
              else -cop.decision_function(X_test))
    z_test = ((s_i_te - s_i.mean()) / (s_i.std() + 1e-9)
              + (s_c_te - s_c.mean()) / (s_c.std() + 1e-9)) / 2

    filas = []
    for q, p in QQ.items():
        thr = float(np.quantile(z_train, p))
        tp = int((z_test[mask] < thr).sum())
        fp = int(alertas_norm[q].sum())
        filas.append({"esquema": "ENSEMBLE_Z", "umbral": q,
                      **metricas(tp, n_fault - tp, fp, n_norm - fp)})

    auc = None
    if n_fault > 0:
        # Idem evaluar_esquema: null si la máscara tiene una sola clase.
        if len(np.unique(mask)) > 1:
            y = mask.astype(int)
            s = -z_test
            try:
                auc = {"esquema": "ENSEMBLE_Z",
                       "roc_auc": round(float(roc_auc_score(y, s)), 4),
                       "pr_auc": round(float(average_precision_score(y, s)), 4)}
            except Exception:
                auc = {"esquema": "ENSEMBLE_Z", "roc_auc": None, "pr_auc": None}
        else:
            auc = {"esquema": "ENSEMBLE_Z", "roc_auc": None, "pr_auc": None}
    return filas, auc, (z_train, z_test)


def evaluar_ensamble_par(nombre_a, nombre_b, X_train, runs_train, X_test,
                         seed=SEED):
    """Ensemble Z de dos modelos genéricos (media de z-scores).

    Igual protocolo que evaluar_ensamble: normales en LOO, fallos con el
    modelo entrenado en todo el train.
    """
    n_norm = len(X_train)
    mask = MASK_FAULT if MASK_FAULT is not None else np.ones(len(X_test), dtype=bool)
    n_fault = int(mask.sum())
    etiqueta = f"ENSEMBLE_{nombre_a[:3]}_{nombre_b[:3]}"
    alertas_norm = {q: np.zeros(n_norm, dtype=bool) for q in QQ}

    def z_par(s_a, s_b, mu_a, sd_a, mu_b, sd_b):
        return ((s_a - mu_a) / sd_a + (s_b - mu_b) / sd_b) / 2

    for corrida in sorted(set(runs_train)):
        idx_c = [i for i, r in enumerate(runs_train) if r == corrida]
        idx_tr = [i for i in range(n_norm) if i not in idx_c]
        ma = crear_modelo(nombre_a, seed).fit(X_train[idx_tr])
        mb = crear_modelo(nombre_b, seed).fit(X_train[idx_tr])
        a_f, a_c = scores(ma, nombre_a, X_train[idx_tr]), scores(ma, nombre_a, X_train[idx_c])
        b_f, b_c = scores(mb, nombre_b, X_train[idx_tr]), scores(mb, nombre_b, X_train[idx_c])
        z_f = z_par(a_f, b_f, a_f.mean(), a_f.std() + 1e-9, b_f.mean(), b_f.std() + 1e-9)
        z_c = z_par(a_c, b_c, a_f.mean(), a_f.std() + 1e-9, b_f.mean(), b_f.std() + 1e-9)
        for q, p in QQ.items():
            alertas_norm[q][idx_c] = z_c < np.quantile(z_f, p)

    ma = crear_modelo(nombre_a, seed).fit(X_train)
    mb = crear_modelo(nombre_b, seed).fit(X_train)
    a_t, b_t = scores(ma, nombre_a, X_train), scores(mb, nombre_b, X_train)
    z_train = z_par(a_t, b_t, a_t.mean(), a_t.std() + 1e-9, b_t.mean(), b_t.std() + 1e-9)
    z_test = z_par(scores(ma, nombre_a, X_test), scores(mb, nombre_b, X_test),
                   a_t.mean(), a_t.std() + 1e-9, b_t.mean(), b_t.std() + 1e-9)

    filas = []
    for q, p in QQ.items():
        thr = float(np.quantile(z_train, p))
        tp = int((z_test[mask] < thr).sum())
        fp = int(alertas_norm[q].sum())
        filas.append({"esquema": etiqueta, "umbral": q,
                      **metricas(tp, n_fault - tp, fp, n_norm - fp)})
    return filas


# ==========================================
# Stage: metrics
# ==========================================
def stage_metrics(art):
    indice = indices_modelo(art["features"])
    X_train = aplanar(art["X_train"], indice)
    X_test = aplanar(art["X_test"], indice)

    filas, aucs = [], []
    for nombre in ESQUEMAS:
        log(f"== {nombre}")
        f, a, _ = evaluar_esquema(nombre, X_train, art["runs_train"], X_test)
        filas.extend(f)
        aucs.append(a)

    log("== ENSEMBLE_Z")
    f, a, _ = evaluar_ensamble(X_train, art["runs_train"], X_test)
    filas.extend(f)
    aucs.append(a)

    log("== ENSEMBLE_LOF_ELL")
    filas.extend(evaluar_ensamble_par("LOF", "ELLIPTIC", X_train,
                                      art["runs_train"], X_test))

    guardar("metrics.json", {
        "_estado": "LEGACY — harness de comparación v1; fuente válida: indicadores/honesto.json",
        "n_train": len(X_train), "n_test": len(X_test),
        "ventana": VENTANA, "n_variables": len(indice),
        "metricas": filas, "aucs": aucs,
    })

    print("\n=== MÉTRICAS (q01) ===")
    for f in filas:
        if f["umbral"] == "q01":
            print(f"  {f['esquema']:<18} TPR={f['tpr']:.4f} "
                  f"FPR={f['fpr']:.4f} F1={f['f1']:.4f}")


# ==========================================
# Stage: seeds
# ==========================================
def stage_seeds(art):
    indice = indices_modelo(art["features"])
    X_train = aplanar(art["X_train"], indice)
    X_test = aplanar(art["X_test"], indice)

    filas = []
    for k in range(N_SEEDS):
        seed = SEED + k
        log(f"  seed {seed}")
        for nombre in ESQUEMAS:
            f, _, _ = evaluar_esquema(nombre, X_train, art["runs_train"],
                                      X_test, seed=seed)
            for fila in f:
                filas.append({**fila, "seed": seed})
        f, _, _ = evaluar_ensamble(X_train, art["runs_train"], X_test, seed=seed)
        for fila in f:
            filas.append({**fila, "seed": seed})
        f = evaluar_ensamble_par("LOF", "ELLIPTIC", X_train, art["runs_train"],
                                 X_test, seed=seed)
        for fila in f:
            filas.append({**fila, "seed": seed})

    df = pd.DataFrame(filas)
    grp = df.groupby(["esquema", "umbral"])[["tpr", "fpr", "f1"]].agg(["mean", "std"])
    resumen = []
    for (esq, umb), row in grp.iterrows():
        resumen.append({
            "esquema": esq, "umbral": umb,
            "tpr_mean": round(float(row[("tpr", "mean")]), 4),
            "tpr_std":  round(float(row[("tpr", "std")]), 4),
            "fpr_mean": round(float(row[("fpr", "mean")]), 4),
            "fpr_std":  round(float(row[("fpr", "std")]), 4),
            "f1_mean":  round(float(row[("f1", "mean")]), 4),
            "f1_std":   round(float(row[("f1", "std")]), 4),
        })
    guardar("seeds.json", {"n_seeds": N_SEEDS, "resumen": resumen})

    print(f"\n=== ESTABILIDAD ({N_SEEDS} semillas) ===")
    for r in resumen:
        if r["umbral"] == "q01":
            print(f"  {r['esquema']:<18} "
                  f"F1={r['f1_mean']:.4f}±{r['f1_std']:.4f}")


# ==========================================
# Stage: vars
# ==========================================
def stage_vars(art, features):
    """Sensibilidad con 15, 17 y 19 variables."""
    indice17 = indices_modelo(features)
    F17 = len(indice17)

    # Importancia con un ISO de referencia
    raw17 = art["X_train"][:, :, indice17]
    sc = StandardScaler().fit(raw17.reshape(-1, F17))
    X17 = sc.transform(raw17.reshape(-1, F17)).reshape(len(raw17), -1)
    iso = IsolationForest(random_state=SEED, contamination="auto",
                          n_jobs=-1).fit(X17)
    imp = np.mean([t.feature_importances_ for t in iso.estimators_], axis=0)
    agg = np.array([np.abs(imp[i * VENTANA:(i + 1) * VENTANA]).mean()
                    for i in range(F17)])
    orden = list(np.argsort(-agg))

    # Subconjuntos
    sub15 = sorted([indice17[j] for j in orden[:15]])
    sub17 = list(indice17)
    # 19 = 17 + 2 mejores fuera del set
    resto = [i for i in range(len(features)) if i not in set(indice17)]
    sub19 = sorted(sub17 + resto[:2])

    combos = {"15": sub15, "17": sub17, "19": sub19}
    filas = []
    for etiqueta, idx_var in combos.items():
        Xt = aplanar(art["X_train"], idx_var)
        Xe = aplanar(art["X_test"], idx_var)
        f, _, _ = evaluar_ensamble(Xt, art["runs_train"], Xe)
        for fila in f:
            filas.append({**fila, "subset_vars": etiqueta})

    guardar("vars.json", {
        "subconjuntos": {k: [features[i] for i in v] for k, v in combos.items()},
        "metricas": filas,
    })

    print("\n=== SENSIBILIDAD DE VARIABLES (ENSEMBLE_Z q01) ===")
    for f in filas:
        if f["umbral"] == "q01":
            print(f"  {f['subset_vars']} vars: "
                  f"TPR={f['tpr']:.4f} FPR={f['fpr']:.4f} F1={f['f1']:.4f}")


# ==========================================
# Stage: freeze
# ==========================================
def stage_freeze(art):
    import joblib
    indice = indices_modelo(art["features"])
    X_train = aplanar(art["X_train"], indice)

    iso = IsolationForest(random_state=SEED, contamination="auto",
                          n_jobs=-1).fit(X_train)
    cop = COPOD(contamination=0.05).fit(X_train)
    s_i = iso.decision_function(X_train)
    s_c = -cop.decision_function(X_train)
    z = ((s_i - s_i.mean()) / (s_i.std() + 1e-9)
         + (s_c - s_c.mean()) / (s_c.std() + 1e-9)) / 2
    umbrales = {q: float(np.quantile(z, p)) for q, p in QQ.items()}

    joblib.dump({"iso": iso, "copod": cop,
                 "iso_mean": float(s_i.mean()), "iso_std": float(s_i.std()),
                 "cop_mean": float(s_c.mean()), "cop_std": float(s_c.std()),
                 "features": [art["features"][i] for i in indice],
                 "ventana": VENTANA, "umbrales": umbrales},
                os.path.join(DIR_VAL, "modelo_candidato.joblib"))

    guardar("freeze.json", {
        "_estado": "LEGACY — candidato ENSEMBLE_Z; producción: ENSEMBLE_LOF_ELL (produccion/meta.json)",
        "modelo": "ENSEMBLE_Z", "ventana": VENTANA, "seed": SEED,
        "features": [art["features"][i] for i in indice],
        "umbrales": umbrales, "n_train": len(X_train),
    })


# ==========================================
# Stage: oper
# ==========================================
def stage_oper(art):
    indice = indices_modelo(art["features"])
    X_train = aplanar(art["X_train"], indice)
    X_test = aplanar(art["X_test"], indice)
    tl = cargar_timelines()

    # (1) ENSEMBLE_Z por corrida: 1ª alerta desde el inicio de la corrida
    #     (vista operativa de todas las corridas; lote completo).
    z_train, z_test = scores_full("ENSEMBLE_Z", X_train, X_test,
                                  mask_batch=False)
    thr_q01 = float(np.quantile(z_train, QQ["q01"]))
    alertas_z = z_test < thr_q01
    por_corrida = []
    for corrida in sorted(set(art["runs_test"])):
        idx = [i for i, r in enumerate(art["runs_test"]) if r == corrida]
        ventanas = [art["ventanas_test"][i] for i in idx]
        inicio = min(pd.to_datetime(v["inicio"]) for v in ventanas)
        idx_alert = [i for i in idx if alertas_z[i]]
        ttfa = None
        if idx_alert:
            primera = min(pd.to_datetime(art["ventanas_test"][i]["inicio"])
                          for i in idx_alert)
            ttfa = (primera - inicio).total_seconds()
        por_corrida.append({"run": corrida, "ventanas": len(idx),
                            "alertas_q01": int(alertas_z[idx].sum()),
                            "ttfa_desde_inicio_seg": ttfa})

    # (2) Por candidato: detección y TTFA por fault (lote evaluado, como v1).
    candidatos = []
    for nombre in ESQUEMAS + ["ENSEMBLE_Z", "ENSEMBLE_LOF_ELL"]:
        log(f"== {nombre}")
        s_tr, s_te = scores_full(nombre, X_train, X_test)
        thr = float(np.quantile(s_tr, QQ["q01"]))
        alertas = s_te < thr
        por_fault = []
        for _, f in tl.iterrows():
            idx = [i for i, w in enumerate(art["ventanas_test"])
                   if w["run"] == f["run_name"]
                   and pd.Timestamp(w["inicio"]) <= f["fin"]
                   and pd.Timestamp(w["fin"]) >= f["inicio"]]
            idx_alert = [i for i in idx if alertas[i]]
            ttfa = None
            if idx_alert:
                # El detector emite al cerrar la ventana -> se usa su fin.
                primera = min(pd.Timestamp(art["ventanas_test"][i]["fin"])
                              for i in idx_alert)
                ttfa = round((primera - f["inicio"]).total_seconds(), 1)
            por_fault.append({"run": f["run_name"], "fault": f["tipo"],
                              "ventanas": len(idx), "alertas": len(idx_alert),
                              "detectado": bool(idx_alert), "ttfa_seg": ttfa})

        detectados = [p for p in por_fault if p["detectado"]]
        ttfas = [p["ttfa_seg"] for p in detectados]
        candidatos.append({
            "esquema": nombre,
            "faults": len(por_fault),
            "detectados": len(detectados),
            "tasa_deteccion": round(len(detectados) / len(por_fault), 4)
                              if por_fault else 0.0,
            "ttfa_medio_seg": round(float(np.mean(ttfas)), 1) if ttfas else None,
            "ttfa_mediana_seg": round(float(np.median(ttfas)), 1) if ttfas else None,
            "por_fault": por_fault,
        })

    guardar("oper.json", {"umbral_q01": thr_q01, "faults": len(tl),
                          "por_corrida": por_corrida, "candidatos": candidatos})

    print("\n=== OPERATIVAS (ENSEMBLE_Z q01) ===")
    for f in por_corrida:
        print(f"  {f['run']:<20} ventanas={f['ventanas']:<4} "
              f"alertas={f['alertas_q01']:<4} ttfa={f['ttfa_desde_inicio_seg']}")
    print("\n=== DETECCIÓN POR CANDIDATO (q01, por fault) ===")
    for c in candidatos:
        print(f"  {c['esquema']:<18} detección={c['tasa_deteccion']:.2%} "
              f"TTFA medio={c['ttfa_medio_seg']}s")


# ==========================================
# Stage: diagnostico
# ==========================================
def cargar_reglas():
    """Detecciones del motor de reglas R1-R7 (reglas.json)."""
    ruta = os.path.join(DIR_MODELADO, "reglas.json")
    if not os.path.isfile(ruta):
        return pd.DataFrame()
    with open(ruta, encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data.get("detecciones", []))
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def cargar_diagnostico():
    """Informe por corrida con atribución de variables (diagnostico.json)."""
    ruta = os.path.join(DIR_MODELADO, "diagnostico.json")
    if not os.path.isfile(ruta):
        return {}
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def stage_diagnostico(art):
    indice = indices_modelo(art["features"])
    X_train = aplanar(art["X_train"], indice)
    X_test = aplanar(art["X_test"], indice)
    tl = cargar_timelines()

    z_train, z_test = scores_full("ENSEMBLE_Z", X_train, X_test)
    thr = float(np.quantile(z_train, QQ["q01"]))
    alertas = z_test < thr

    reglas = cargar_reglas()
    diag = cargar_diagnostico()

    por_fault = []
    for _, f in tl.iterrows():
        idx = [i for i, w in enumerate(art["ventanas_test"])
               if w["run"] == f["run_name"]
               and pd.Timestamp(w["inicio"]) <= f["fin"]
               and pd.Timestamp(w["fin"]) >= f["inicio"]]
        idx_alert = [i for i in idx if alertas[i]]
        ttfa = None
        if idx_alert:
            # El detector emite al cerrar la ventana -> se usa su fin.
            primera = min(pd.Timestamp(art["ventanas_test"][i]["fin"])
                          for i in idx_alert)
            ttfa = round((primera - f["inicio"]).total_seconds(), 1)

        # Reglas R1-R7 disparadas dentro de la ventana del fault.
        codigos = []
        if not reglas.empty:
            sel = reglas[(reglas["run_name"] == f["run_name"])
                         & (reglas["timestamp"] >= f["inicio"])
                         & (reglas["timestamp"] <= f["fin"])]
            codigos = sorted(set(sel["regla"]))

        # Atribución de variables del informe por corrida.
        info = (diag.get("por_corrida", {}).get(f["run_name"], {})
                    .get("por_fault", {}).get(f["tipo"], {}))
        vars_top = [v["variable"] for v in info.get("variables_causantes_top", [])]
        coincide = info.get("coincidencia_con_huella", [])

        detectado = bool(idx_alert)
        diagnosticado = detectado and (bool(codigos) or bool(coincide))
        por_fault.append({
            "run": f["run_name"], "fault": f["tipo"],
            "detectado_modelo": detectado,
            "ttfa_seg": ttfa,
            "reglas": len(codigos), "codigos_regla": codigos,
            "variables_causantes": vars_top[:3],
            "coincide_huella": coincide,
            "diagnosticado": diagnosticado,
        })

    n = len(por_fault)
    det = sum(p["detectado_modelo"] for p in por_fault)
    di = sum(p["diagnosticado"] for p in por_fault)
    ttfas = [p["ttfa_seg"] for p in por_fault if p["detectado_modelo"]]
    resumen = {
        "faults": n,
        "detectados_modelo": det,
        "tasa_deteccion": round(det / n, 4) if n else 0.0,
        "con_reglas": sum(p["reglas"] > 0 for p in por_fault),
        "con_coincidencia_huella": sum(bool(p["coincide_huella"])
                                       for p in por_fault),
        "diagnosticados": di,
        "tasa_diagnostico": round(di / n, 4) if n else 0.0,
        "ttfa_medio_seg": round(float(np.mean(ttfas)), 1) if ttfas else None,
        "ttfa_mediana_seg": round(float(np.median(ttfas)), 1) if ttfas else None,
    }
    guardar("diagnostico_eval.json", {"resumen": resumen, "por_fault": por_fault})

    print("\n=== DIAGNÓSTICO (ENSEMBLE_Z q01 + reglas + atribución) ===")
    print(f"  faults={n} detectados={det} ({resumen['tasa_deteccion']:.2%}) "
          f"diagnosticados={di} ({resumen['tasa_diagnostico']:.2%})")
    print(f"  con reglas={resumen['con_reglas']} "
          f"con huella={resumen['con_coincidencia_huella']} "
          f"TTFA medio={resumen['ttfa_medio_seg']}s")


# ==========================================
# Stage: calidad
# ==========================================
def stage_calidad(art):
    df = None
    if os.path.isfile(DATASET_PRINCIPALES):
        df = pd.read_parquet(DATASET_PRINCIPALES)
    else:
        log(f"Falta {DATASET_PRINCIPALES}. Se audita solo el pkl.")

    filas = []
    if df is not None:
        for c in [c for c in df.columns if c not in COLUMNAS_CONTEXTO]:
            s = pd.to_numeric(df[c], errors="coerce")
            filas.append({
                "variable": c,
                "en_modelo": c in VARIABLES_MODELO,
                "pct_nan": round(float(s.isna().mean()) * 100, 2),
                "pct_ceros": round(float((s == 0).mean()) * 100, 2),
                "n_unicos": int(s.dropna().nunique()),
                "constante": bool(s.dropna().nunique() <= 1),
            })

    # NaN/inf en las ventanas estandarizadas que ve el modelo.
    indice = indices_modelo(art["features"])
    X_train = art["X_train"][:, :, indice]
    X_test = art["X_test"][:, :, indice]
    ventanas = {
        "train_nan": int(np.isnan(X_train).sum()),
        "test_nan": int(np.isnan(X_test).sum()),
        "train_inf": int(np.isinf(X_train).sum()),
        "test_inf": int(np.isinf(X_test).sum()),
    }

    guardar("calidad.json", {"por_variable": filas, "ventanas_modelo": ventanas})

    print("\n=== CALIDAD (ceros y NaN) ===")
    for f in filas:
        if f["pct_nan"] > 0 or f["constante"]:
            print(f"  {f['variable']:<28} NaN={f['pct_nan']}% "
                  f"ceros={f['pct_ceros']}% unicos={f['n_unicos']} "
                  f"en_modelo={f['en_modelo']}")
    print(f"  NaN/inf en ventanas del modelo: {ventanas}")


# ==========================================
# Stage: errores
# ==========================================
def stage_errores(art):
    indice = indices_modelo(art["features"])
    X_train = aplanar(art["X_train"], indice)
    X_test = aplanar(art["X_test"], indice)

    _, _, (z_train, z_test) = evaluar_ensamble(
        X_train, art["runs_train"], X_test)
    thr_q01 = float(np.quantile(z_train, QQ["q01"]))
    alertas = z_test < thr_q01

    # Solo cuentan las ventanas evaluadas (las que cruzan un fault).
    mask = MASK_FAULT if MASK_FAULT is not None else np.ones(len(z_test), dtype=bool)
    tp = int(alertas[mask].sum())
    fn = int((~alertas[mask]).sum())

    # Contribución SPE con PCA sobre normales
    sc = StandardScaler().fit(X_train)
    Xt_sc = sc.transform(X_train)
    pca = PCA(n_components=min(8, len(X_train) - 1)).fit(Xt_sc)

    contribuciones = []
    for i, es_alert in enumerate(alertas):
        if not mask[i] or es_alert:
            continue  # solo FN dentro del lote evaluado
        xw = sc.transform(X_test[i:i + 1])
        t = pca.transform(xw)
        res = xw - pca.inverse_transform(t)
        contrib = (res ** 2).sum(axis=0)
        por_var = contrib.reshape(VENTANA, len(indice)).sum(axis=0)
        orden = np.argsort(-por_var)[:3]
        contribuciones.append({
            "run": art["runs_test"][i],
            "inicio": art["ventanas_test"][i]["inicio"],
            "top1": art["features"][indice[orden[0]]],
            "top2": art["features"][indice[orden[1]]],
            "top3": art["features"][indice[orden[2]]],
        })

    guardar("errores.json", {
        "umbral_q01": thr_q01,
        "tp": tp, "fn": fn,
        "fns": contribuciones,
    })

    print(f"\n=== ERRORES (ENSEMBLE_Z q01) ===")
    print(f"  TP={tp} FN={fn} ({fn/int(mask.sum()):.2%})")


# ==========================================
# Stage: robustez
# ==========================================
def stage_robustez(art):
    indice = indices_modelo(art["features"])
    X_train = aplanar(art["X_train"], indice)
    X_test = aplanar(art["X_test"], indice)

    _, _, (z_train, z_test) = evaluar_ensamble(
        X_train, art["runs_train"], X_test)
    thr = float(np.quantile(z_train, QQ["q01"]))
    base = z_test < thr
    rng = np.random.default_rng(SEED)

    resultados = {}

    # 1. Ruido gaussiano
    Xp = X_test + rng.normal(0, 0.05, X_test.shape)
    _, _, (_, z_p) = evaluar_ensamble(X_train, art["runs_train"], Xp)
    flips = int(((z_p < thr) != base).sum())
    resultados["ruido_z005"] = {"n": len(X_test), "flips": flips,
                                "tasa": round(flips / len(X_test), 4)}

    # 2. NaN en una variable de una ventana
    X_nan = X_test.copy()
    X_nan[0, 0] = np.nan
    try:
        _, _, (_, z_nan) = evaluar_ensamble(X_train, art["runs_train"], X_nan)
        resultados["nan_una_var"] = {"score": float(z_nan[0]),
                                     "alerta": bool(z_nan[0] < thr)}
    except Exception as e:
        resultados["nan_una_var"] = {"error": str(e)}

    # 3. Escala x5 en una variable
    X_esc = X_test.copy()
    X_esc[:, 0] *= 5.0
    _, _, (_, z_esc) = evaluar_ensamble(X_train, art["runs_train"], X_esc)
    flips = int(((z_esc < thr) != base).sum())
    resultados["escala_x5"] = {"n": len(X_test), "flips": flips,
                               "tasa": round(flips / len(X_test), 4)}

    guardar("robustez.json", {"umbral_q01": thr, "resultados": resultados})


# ==========================================
# Stage: latencia
# ==========================================
def stage_latencia(art):
    indice = indices_modelo(art["features"])
    X_train = aplanar(art["X_train"], indice)
    X_test = aplanar(art["X_test"], indice)

    iso = IsolationForest(random_state=SEED, contamination="auto",
                          n_jobs=-1).fit(X_train)
    cop = COPOD(contamination=0.05).fit(X_train)

    n_lote = min(2000, len(X_test))
    X = X_test[:n_lote]

    t0 = time.perf_counter()
    _ = iso.decision_function(X)
    _ = cop.decision_function(X)
    dt = time.perf_counter() - t0

    guardar("latencia.json", {
        "n": n_lote,
        "seg_total": round(dt, 4),
        "us_por_ventana": round(dt / n_lote * 1e6, 2),
    })

    print(f"\n=== LATENCIA ===")
    print(f"  {n_lote} ventanas en {dt:.3f}s "
          f"({dt / n_lote * 1e6:.1f} µs/ventana)")


# ==========================================
# Main
# ==========================================
STAGES = ["metrics", "seeds", "vars", "freeze", "oper",
          "diagnostico", "calidad", "errores", "robustez", "latencia", "todo"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=STAGES, default="metrics")
    args = ap.parse_args()

    art = cargar_artefactos()
    if art is None:
        return

    global MASK_FAULT
    MASK_FAULT = marcar_fault(art)
    log(f"Ventanas de test que cruzan fault: {int(MASK_FAULT.sum())} "
        f"de {len(MASK_FAULT)}")

    os.makedirs(DIR_VAL, exist_ok=True)

    def correr(nombre):
        log(f"--- STAGE {nombre} ---")
        if nombre == "metrics":
            stage_metrics(art)
        elif nombre == "seeds":
            stage_seeds(art)
        elif nombre == "vars":
            stage_vars(art, art["features"])
        elif nombre == "freeze":
            stage_freeze(art)
        elif nombre == "oper":
            stage_oper(art)
        elif nombre == "diagnostico":
            stage_diagnostico(art)
        elif nombre == "calidad":
            stage_calidad(art)
        elif nombre == "errores":
            stage_errores(art)
        elif nombre == "robustez":
            stage_robustez(art)
        elif nombre == "latencia":
            stage_latencia(art)

    if args.stage == "todo":
        for s in STAGES[:-1]:
            correr(s)
    else:
        correr(args.stage)


if __name__ == "__main__":
    main()