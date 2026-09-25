"""
validar_candidato.py
====================
Validación integral del modelo candidato (ENSEMBLE_Z: IsolationForest + COPOD)
con experimento unificado HOLD-OUT POR CORRIDA (TPR y FPR salen del MISMO test):
  1. --metrics   Tabla comparativa por umbral (q10/q05/q01) ISO/COPOD/LOF/OCSVM/
                 Elliptic/ENSEMBLE_Z + ROC-AUC/PR-AUC con el score continuo.
  2. --seeds     Estabilidad con N semillas (media/dev) para ISO y ENSEMBLE_Z.
  3. --vars      Sensibilidad de variables: 15 / 17 / 19.
  4. --freeze    Congela y registra el candidato (joblib + JSON) entrenado con
                 TODAS las corridas normales (config de despliegue).
  5. --oper      Operativas: tiempo hasta la primera alerta por falla y
                 alertas/hora en carga normal.
  6. --errores   Análisis de errores: FN/FP, ventanas de borde y contribución
                 por variable (T² y SPE vía PCA).
  7. --robustez  Ruido, valores faltantes, cambio de escala y variable ausente.
  8. --latencia  Micro-benchmark de inferencia del ensamble.
  9. --integ     Verifica el flujo Detector (producción) sobre una muestra real.
 10. --todo      Ejecuta todos los pasos.

ES HERRAMIENTA DE VALIDACIÓN: no modifica 03 ni artefactos de producción.
Todo lo nuevo se escribe en deteccion/validacion/.
"""

import argparse
import json
import os
import statistics
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
from pyod.models.copod import COPOD
from pyod.models.lof import LOF
from pyod.models.ocsvm import OCSVM
from sklearn.covariance import EllipticEnvelope

import config

# UNICA fuente del ENSEMBLE_Z (z-score de componentes) -> app/ml/ensamble_z.py
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))))
from app.ml.ensamble_z import estadisticas, z_score  # noqa: E402


# ---------------------------------------------------------------------------
# Configuración del experimento (extensible por env)
# ---------------------------------------------------------------------------
SEED_BASE = int(os.getenv("STEELNORT_VAL_SEED", "42"))
N_SEEDS = int(os.getenv("STEELNORT_VAL_SEEDS", "20"))
GRID_Q = ("q10", "q05", "q01")
QQ = {"q10": 0.10, "q05": 0.05, "q01": 0.01}
TRAIN_NORM = os.getenv("STEELNORT_VAL_TRAIN_NORM",
                       "normal_baja_02,normal_media_02,normal_alta_01").split(",")
TEST_NORM = os.getenv("STEELNORT_VAL_TEST_NORM",
                      "normal_larga_01,normal_prueba_01").split(",")
DIR_VAL = os.path.join(config.DIR_DETECCION, "validacion")
for extra in ("copod", "lof", "ocsvm", "elliptic"):
    os.environ.setdefault(f"STEELNORT_VAL_{extra.upper()}", "1")


def log(msg):
    print(f"[VALIDAR] {msg}", flush=True)


def cargar(ruta):
    with open(ruta, "rb") as f:
        import pickle
        return pickle.load(f)


def seleccionar(ruta_features_csv, features):
    df = pd.read_csv(ruta_features_csv, encoding="utf-8-sig")
    modelo = [c for c in df["columna"] if c in features]
    return [features.index(c) for c in modelo]


def marcar_fault(ventanas):
    """True si la ventana cruza con algún fault del timeline (same que medir)."""
    import glob
    rutas = sorted(set(
        glob.glob(os.path.join(config.DIR_CORRIDAS, "anomalias", "*", "anomalias_timeline.csv"))
        + glob.glob(os.path.join(config.DIR_CORRIDAS, "*", "anomalias_timeline.csv"))
    ))
    if not rutas:
        return np.zeros(len(ventanas), dtype=bool)
    es_fault = np.zeros(len(ventanas), dtype=bool)
    for r in rutas:
        run = os.path.basename(os.path.dirname(r))
        tl = pd.read_csv(r, encoding="utf-8-sig")
        tl["inicio"] = pd.to_datetime(tl["inicio"])
        tl["fin"] = pd.to_datetime(tl["fin"])
        for i, w in enumerate(ventanas):
            if w["run"] != run:
                continue
            ini = pd.to_datetime(w["inicio"])
            fin = pd.to_datetime(w["fin"])
            for _, f in tl.iterrows():
                if (ini <= f["fin"]) & (fin >= f["inicio"]):
                    es_fault[i] = True
    return es_fault


def preparar_muestra(archivo):
    """Carga pkl y devuelve estructuras per-run y matrices raw (per 17 features)."""
    with open(archivo, "rb") as f:
        import pickle
        d = pickle.load(f)
    return d


def raw_matrix(d):
    """Raw completo (22 features) desescalado; cada experimento corta su indice."""
    return d["X"] * d["scaler"].scale_ + d["scaler"].mean_


def cargar_experimento():
    """Combina train+test pkl (raw completo) y define el hold-out por corrida."""
    train = preparar_muestra(os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl"))
    test = preparar_muestra(os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl"))
    raw_tr = raw_matrix(train)
    raw_te = raw_matrix(test)

    ventanas = list(train["ventanas"]) + list(test["ventanas"])
    y_true = marcar_fault(ventanas)
    runs = list(train["runs"]) + list(test["runs"])
    raw = np.concatenate([raw_tr, raw_te], axis=0)
    marcas = ["TRAIN"] * len(train["runs"]) + ["TEST"] * len(test["runs"])
    origen = list(train["ventanas"]) + list(test["ventanas"])

    n = len(runs)
    idx = np.arange(n)
    idx_train = np.array([i for i in range(n) if marcas[i] == "TRAIN" and runs[i] in TRAIN_NORM])
    idx_test_norm = np.array([i for i in range(n) if marcas[i] == "TRAIN" and runs[i] in TEST_NORM])
    idx_test_fault = np.array([i for i in range(n) if marcas[i] == "TEST"])
    idx_test = np.concatenate([idx_test_norm, idx_test_fault])
    return dict(idx=idx, idx_train=idx_train, idx_test_norm=idx_test_norm,
                idx_test_fault=idx_test_fault, idx_test=idx_test, raw=raw,
                y_true=y_true, runs=runs, origen=origen)


def flat(raw, n, V, F):
    return raw.reshape(n, V * F)


def modelo_por_nombre(nombre, seed):
    if nombre == "ISOLATION_FOREST":
        return IsolationForest(random_state=seed, contamination="auto", n_jobs=-1)
    if nombre == "COPOD":
        return COPOD(contamination=0.05)
    if nombre == "LOF":
        return LOF(contamination=0.05, n_neighbors=20, n_jobs=-1)
    if nombre == "OCSVM":
        return OCSVM(contamination=0.05)
    if nombre == "ELLIPTIC":
        return EllipticEnvelope(contamination=0.05, random_state=seed)
    raise ValueError(nombre)


def scores_modelo(modelo, nombre, Xt, Xe, seed):
    """Devuelve scores con convencion unica: MENOR = mas anomalo.
    PyOD suele dar mas alto = mas anomalo para LOF/OCSVM/Elliptic; se invierte."""
    s_tr = modelo.decision_function(Xt)
    s_te = modelo.decision_function(Xe)
    if nombre in ("LOF", "OCSVM", "ELLIPTIC"):
        neg_tr, neg_te = -s_tr, -s_te
        if abs(neg_tr.mean()) < abs(s_tr.mean()):  # entrenar con datos es irrelevante
            pass
        return neg_tr, neg_te
    return s_tr, s_te


def orientar_signo(s_tr, s_te, y_te):
    """Fija la orientacion (menor=anomalo) comparando medias en test real."""
    if y_te.sum() == 0 or (~y_te).sum() == 0:
        return s_tr, s_te
    if s_te[y_te].mean() > s_te[~y_te].mean():
        return -s_tr, -s_te
    return s_tr, s_te


def metricas(tp, fn, fp, tn):
    n_fault = tp + fn
    n_norm = fp + tn
    tpr = tp / n_fault if n_fault else 0.0
    fpr = fp / n_norm if n_norm else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = (2 * prec * tpr / (prec + tpr)) if (prec + tpr) else 0.0
    acc = (tp + tn) / (n_fault + n_norm) if (n_fault + n_norm) else 0.0
    return dict(tp=tp, fn=fn, fp=fp, tn=tn, tpr=tpr, fpr=fpr, precision=prec, f1=f1, accuracy=acc)


def run_experimento(indice, V, seed, extra_modelos=True):
    """Un experimento hold-out completo. Devuelve filas de métricas y scores."""
    E = cargar_experimento()
    rawv = E["raw"][:, :, indice]
    F = len(indice)
    sc = StandardScaler()
    sc.fit(rawv[E["idx_train"]].reshape(-1, F))
    Xt = flat(sc.transform(rawv[E["idx_train"]].reshape(-1, F)).reshape(-1, V, F), len(E["idx_train"]), V, F)
    Xe = flat(sc.transform(rawv[E["idx_test"]].reshape(-1, F)).reshape(-1, V, F), len(E["idx_test"]), V, F)
    y_te = E["y_true"][E["idx_test"]]

    modelos = [("ISOLATION_FOREST", seed), ("COPOD", seed)]
    if extra_modelos:
        modelos += [("LOF", seed), ("OCSVM", seed), ("ELLIPTIC", seed)]

    scores_s = {}
    filas = []
    for nombre, s in modelos:
        try:
            modelo = modelo_por_nombre(nombre, s).fit(Xt)
        except Exception as e:
            log(f"  {nombre} falló al entrenar: {e}")
            continue
        s_tr, s_te = scores_modelo(modelo, nombre, Xt, Xe, s)
        s_tr, s_te = orientar_signo(s_tr, s_te, y_te)
        scores_s[nombre] = (s_tr, s_te)
        for q, v in QQ.items():
            thr = np.quantile(s_tr, v)
            al = s_te < thr
            tp = int((al & y_te).sum()); fn = int((~al & y_te).sum())
            fp = int((al & ~y_te).sum()); tn = int((~al & ~y_te).sum())
            m = metricas(tp, fn, fp, tn)
            filas.append({"esquema": nombre, "umbral": q, "seed": seed, **m})

    # ENSEMBLE_Z = promedio de z(ISO)+z(COPOD)
    if "ISOLATION_FOREST" in scores_s and "COPOD" in scores_s:
        (s_iso_t, s_iso_e) = scores_s["ISOLATION_FOREST"]
        (s_cop_t, s_cop_e) = scores_s["COPOD"]
        ens = estadisticas(s_iso_t, s_cop_t)
        z_t = z_score(s_iso_t, s_cop_t, ens)
        z_e = z_score(s_iso_e, s_cop_e, ens)
        scores_s["ENSEMBLE_Z"] = (z_t, z_e)
        for q, v in QQ.items():
            thr = np.quantile(z_t, v)
            al = z_e < thr
            tp = int((al & y_te).sum()); fn = int((~al & y_te).sum())
            fp = int((al & ~y_te).sum()); tn = int((~al & ~y_te).sum())
            m = metricas(tp, fn, fp, tn)
            filas.append({"esquema": "ENSEMBLE_Z", "umbral": q, "seed": seed, **m})

    # AUC (independientes del umbral), score continuo: menor = anomalo => usar -score
    auc_rows = {}
    for nombre, (s_tr, s_te) in scores_s.items():
        s_ano = -s_te
        try:
            auc_rows[nombre] = {
                "roc_auc": float(roc_auc_score(y_te, s_ano)),
                "pr_auc": float(average_precision_score(y_te, s_ano)),
                "seed": seed,
            }
        except Exception:
            auc_rows[nombre] = {"roc_auc": None, "pr_auc": None, "seed": seed}

    return filas, auc_rows, scores_s, y_te, E


# ---------------------------------------------------------------------------
# Stage 1: tabla comparativa
# ---------------------------------------------------------------------------
def stage_metrics(indice, V):
    os.makedirs(DIR_VAL, exist_ok=True)
    filas, aucs, _, _, E = run_experimento(indice, V, SEED_BASE, extra_modelos=True)
    df = pd.DataFrame(filas)
    df.to_csv(os.path.join(DIR_VAL, "resumen_modelos.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(aucs).T.to_csv(os.path.join(DIR_VAL, "aucs.csv"), encoding="utf-8-sig")
    log(f"Test total: {len(E['idx_test'])} | normales {len(E['idx_test_norm'])} "
        f"| falla {len(E['idx_test_fault'])} (y_true={int(E['y_true'].sum())} fault windows)")
    piv = df.pivot_table(index="esquema", columns="umbral",
                         values=["tpr", "fpr", "f1"], aggfunc="first")
    print("\n=== METRICAS POR UMBRAL (hold-out uniforme) ===")
    print(piv.to_string())
    print("\n=== AUC (score continuo) ===")
    print(pd.DataFrame(aucs).T.to_string())


# ---------------------------------------------------------------------------
# Stage 2: estabilidad por semillas
# ---------------------------------------------------------------------------
def stage_seeds(indice, V):
    os.makedirs(DIR_VAL, exist_ok=True)
    rows = []
    for k in range(N_SEEDS):
        seed = SEED_BASE + k
        filas, aucs, _, _, _ = run_experimento(indice, V, seed, extra_modelos=False)
        for f in filas:
            rows.append({**f, "seed": seed})
    df = pd.DataFrame(rows)
    grp = df.groupby(["esquema", "umbral"])[["tpr", "fpr", "f1"]].agg(["mean", "std"])
    grp.to_csv(os.path.join(DIR_VAL, "estabilidad_semillas.csv"), encoding="utf-8-sig")
    print("\n=== ESTABILIDAD ({} semillas) media±dev ===".format(N_SEEDS))
    print(grp.to_string())


# ---------------------------------------------------------------------------
# Stage 3: sensibilidad de variables 15/17/19
# ---------------------------------------------------------------------------
def stage_vars(indice, V, features):
    os.makedirs(DIR_VAL, exist_ok=True)
    E = cargar_experimento()
    F17 = len(indice)

    # importancia con ISO de referencia (max_features=1.0) sobre el train-holder
    raw17 = E["raw"][E["idx_train"]][:, :, indice]
    ref_iso = IsolationForest(random_state=SEED_BASE, contamination="auto", n_jobs=-1)
    sc17 = StandardScaler().fit(raw17.reshape(-1, F17))
    X17 = sc17.transform(raw17.reshape(-1, F17)).reshape(-1, V, F17).reshape(len(E["idx_train"]), -1)
    ref_iso.fit(X17)
    imp = np.mean([t.feature_importances_ for t in ref_iso.estimators_], axis=0)
    agg17 = np.array([np.abs(imp[i * V:(i + 1) * V]).mean() for i in range(F17)])
    cols17 = [features[i] for i in indice]
    ord17 = [i for _, i in sorted(zip(agg17, range(F17)), key=lambda t: -t[0])]
    sub15 = sorted([indice[j] for j in ord17[:15]])
    sub17_full = list(indice)

    # 19: complemento de las 22 (las 5 excluidas) y las 2 más importantes al conjunto 17
    feat_all = features
    set17 = set(cols17)
    complemento = [c for c in feat_all if c not in set17]
    raw_all = E["raw"][E["idx_train"]][:, :, :]
    sc_all = StandardScaler().fit(raw_all.reshape(-1, len(feat_all)))
    Xall = sc_all.transform(raw_all.reshape(-1, len(feat_all))).reshape(-1, V, len(feat_all)).reshape(len(E["idx_train"]), -1)
    ref_all = IsolationForest(random_state=SEED_BASE, contamination="auto", n_jobs=-1)
    ref_all.fit(Xall)
    imp_all = np.mean([t.feature_importances_ for t in ref_all.estimators_], axis=0)
    agg_all = np.array([np.abs(imp_all[i * V:(i + 1) * V]).mean() for i in range(len(feat_all))])
    rank_all = sorted(range(len(feat_all)), key=lambda i: -agg_all[i])
    extra2 = [i for i in rank_all if features[i] in complemento][:2]
    sub19 = sorted(list(indice) + extra2)

    combos = {"15": sub15, "17": sub17_full, "19": sub19}
    filas = []
    for etiqueta, idx_var in combos.items():
        filas_c, aucs, _, _, _ = run_experimento_in_var(idx_var, V, SEED_BASE)
        for f in filas_c:
            filas.append({**f, "subset_vars": etiqueta})
    df = pd.DataFrame(filas)
    df.to_csv(os.path.join(DIR_VAL, "sensibilidad_vars.csv"), index=False, encoding="utf-8-sig")
    piv = df.pivot_table(index="subset_vars", columns="esquema", values="f1").round(4)
    print("\n=== SENSIBILIDAD DE VARIABLES (F1 q01) ===")
    pp = df[df["umbral"] == "q01"].pivot(index="subset_vars", columns="esquema",
                                         values=["tpr", "fpr", "f1"])
    print(pp.to_string())


def run_experimento_in_var(indice, V, seed, extra_modelos=False):
    E = cargar_experimento()
    rawv = E["raw"][:, :, indice]
    F = len(indice)
    sc = StandardScaler()
    sc.fit(rawv[E["idx_train"]].reshape(-1, F))
    Xt = flat(sc.transform(rawv[E["idx_train"]].reshape(-1, F)).reshape(-1, V, F), len(E["idx_train"]), V, F)
    Xe = flat(sc.transform(rawv[E["idx_test"]].reshape(-1, F)).reshape(-1, V, F), len(E["idx_test"]), V, F)
    y_te = E["y_true"][E["idx_test"]]
    scores_s = {}
    filas = []
    for nombre, s in [("ISOLATION_FOREST", seed), ("COPOD", seed)]:
        modelo = modelo_por_nombre(nombre, s).fit(Xt)
        s_tr, s_te = scores_modelo(modelo, nombre, Xt, Xe, s)
        s_tr, s_te = orientar_signo(s_tr, s_te, y_te)
        scores_s[nombre] = (s_tr, s_te)
        for q, v in QQ.items():
            thr = np.quantile(s_tr, v)
            al = s_te < thr
            tp = int((al & y_te).sum()); fn = int((~al & y_te).sum())
            fp = int((al & ~y_te).sum()); tn = int((~al & ~y_te).sum())
            filas.append({"esquema": nombre, "umbral": q, "seed": seed, **metricas(tp, fn, fp, tn)})
    s_iso_t, s_iso_e = scores_s["ISOLATION_FOREST"]
    s_cop_t, s_cop_e = scores_s["COPOD"]
    ens = estadisticas(s_iso_t, s_cop_t)
    z_t = z_score(s_iso_t, s_cop_t, ens)
    z_e = z_score(s_iso_e, s_cop_e, ens)
    scores_s["ENSEMBLE_Z"] = (z_t, z_e)
    for q, v in QQ.items():
        thr = np.quantile(z_t, v)
        al = z_e < thr
        tp = int((al & y_te).sum()); fn = int((~al & y_te).sum())
        fp = int((al & ~y_te).sum()); tn = int((~al & ~y_te).sum())
        filas.append({"esquema": "ENSEMBLE_Z", "umbral": q, "seed": seed, **metricas(tp, fn, fp, tn)})
    aucs = {}
    for nombre, (_, s_te) in scores_s.items():
        s_ano = -s_te
        aucs[nombre] = {
            "roc_auc": float(roc_auc_score(y_te, s_ano)),
            "pr_auc": float(average_precision_score(y_te, s_ano)),
            "seed": seed,
        }
    return filas, aucs, scores_s, y_te, E


def cargar_experimento_indice():
    # compat: cargar_experimento ya usa raw completo
    return cargar_experimento()


# ---------------------------------------------------------------------------
# Stage 4: congelar y registrar candidato
# ---------------------------------------------------------------------------
def stage_freeze(features, V):
    os.makedirs(DIR_VAL, exist_ok=True)
    train = preparar_muestra(os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl"))
    indice = [features.index(c) for c in config.VARIABLES_MODELO if c in features]
    F = len(indice)
    raw = (train["X"] * train["scaler"].scale_ + train["scaler"].mean_)[:, :, indice]
    sc = StandardScaler().fit(raw.reshape(-1, F))
    X = flat(sc.transform(raw.reshape(-1, F)).reshape(-1, V, F), len(train["runs"]), V, F)

    iso = modelo_por_nombre("ISOLATION_FOREST", SEED_BASE).fit(X)
    cop = modelo_por_nombre("COPOD", SEED_BASE).fit(X)
    s_iso = iso.decision_function(X)
    s_cop = -cop.decision_function(X)
    ens = estadisticas(s_iso, s_cop)
    z = z_score(s_iso, s_cop, ens)
    umbrales = {q: float(np.quantile(z, v)) for q, v in QQ.items()}

    bundle = {
        "modelo": "ENSEMBLE_Z", "ventana": V, "seed": SEED_BASE,
        "iso": iso, "copod": cop, "scaler": sc,
        "features": [train["features"][i] for i in indice],
        "indice_22": indice, "ens_stats": ens, "umbrales": umbrales,
        "hiperparametros": {
            "iso": {"contamination": "auto", "n_estimators": 100,
                    "max_samples": "auto", "max_features": 1.0},
            "copod": {"contamination": 0.05},
            "scaler": "standard", "n_train_windows": int(len(train["runs"])),
        },
    }
    joblib.dump(bundle, os.path.join(DIR_VAL, "modelo_candidato.joblib"))

    registro = {
        "modelo": "ENSEMBLE_Z", "fecha_validacion": pd.Timestamp.now().isoformat(),
        "seed": SEED_BASE, "ventana": V,
        "features": bundle["features"],
        "hiperparametros": bundle["hiperparametros"],
        "umbrales_ensamble_z": umbrales,
        "ens_stats": {k: round(v, 6) for k, v in ens.items()},
        "n_train_windows": int(len(train["runs"])),
        "experimento": {
            "train_norm": TRAIN_NORM, "test_norm": TEST_NORM,
            "test_fault": sorted(set([r for r, m in zip([], [])])) or None,
        },
        "artefacto": "validacion/modelo_candidato.joblib",
    }
    with open(os.path.join(DIR_VAL, "registro_modelo.json"), "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
    log(f"Candidato congelado: umbrales { {q: round(u, 4) for q, u in umbrales.items()} }")
    log(f"Registro -> {os.path.join(DIR_VAL, 'registro_modelo.json')}")


# ---------------------------------------------------------------------------
# Stage 5: operativas
# ---------------------------------------------------------------------------
def stage_oper(indice, V):
    os.makedirs(DIR_VAL, exist_ok=True)
    filas, aucs, scores_s, y_te, E = run_experimento(indice, V, SEED_BASE, extra_modelos=False)
    z_e = scores_s["ENSEMBLE_Z"][1]
    thr_q01 = np.quantile(scores_s["ENSEMBLE_Z"][0], QQ["q01"])
    al = z_e < thr_q01
    idx_test = E["idx_test"]
    runs = [E["runs"][i] for i in idx_test]
    origen = [E["origen"][i] for i in idx_test]
    yt = y_te

    # tiempo hasta la primera alerta (desde el inicio de la corrida)
    ops = []
    import glob
    timelines = {}
    for r in sorted(set(runs)):
        rutas = glob.glob(os.path.join(config.DIR_CORRIDAS, "anomalias", "*", "anomalias_timeline.csv")) + \
                glob.glob(os.path.join(config.DIR_CORRIDAS, "*", "anomalias_timeline.csv"))
        for rr in rutas:
            run_name = os.path.basename(os.path.dirname(rr))
            if run_name == r:
                tl = pd.read_csv(rr, encoding="utf-8-sig")
                timelines[r] = pd.to_datetime(tl["inicio"]).min()
    for r in sorted(set(runs)):
        idx_r = [k for k in range(len(runs)) if runs[k] == r]
        ini = [pd.to_datetime(origen[k]["inicio"]) for k in idx_r]
        orden = sorted(idx_r, key=lambda k: ini[idx_r.index(k)])
        first_i = ini[0]
        def _inicio(k):
            return pd.to_datetime(origen[k]["inicio"])
        alertados = [k for k in sorted(idx_r, key=lambda k: _inicio(k)) if al[k]]
        ttfa_corrida = None
        ttfa_falla = None
        if alertados:
            t_prim = _inicio(alertados[0])
            ttfa_corrida = (t_prim - first_i).total_seconds()
            if r in timelines:
                ttfa_falla = (t_prim - timelines[r]).total_seconds()
        ventanas = len(idx_r)
        ops.append({"run": r, "tipo": "falla" if yt[idx_r].any() else "normal",
                    "n_ventanas": ventanas, "alertas_q01": int(al[idx_r].sum()),
                    "ttfa_desde_inicio_seg": ttfa_corrida,
                    "ttfa_desde_falla_seg": ttfa_falla,
                    "inicio_falla_timeline": str(timelines.get(r))})
    df = pd.DataFrame(ops).sort_values(["tipo", "run"])
    df.to_csv(os.path.join(DIR_VAL, "operativas_runs.csv"), index=False, encoding="utf-8-sig")
    print("\n=== OPERATIVAS POR CORRIDA (ENSEMBLE_Z q01) ===")
    print(df.to_string(index=False))

    # alertas/hora en carga normal
    span = []
    alertas_n = 0
    for k in range(len(runs)):
        if not yt[k]:
            span.append((pd.to_datetime(origen[k]["inicio"]), pd.to_datetime(origen[k]["fin"])))
            if al[k]:
                alertas_n += 1
    horas = (max(f for _, f in span) - min(i for i, _ in span)).total_seconds() / 3600 if span else 0
    print(f"\nalertas/hora (carga normal, q01): {alertas_n:.0f} en {horas:.2f} h "
          f"= {alertas_n / horas:.3f}/h" if horas else "sin ventanas normales")
    with open(os.path.join(DIR_VAL, "operativas_resumen.json"), "w", encoding="utf-8") as f:
        json.dump({"alertas_normal_q01": int(alertas_n), "horas_normal": round(horas, 4),
                   "alertas_por_hora": round(alertas_n / horas, 5) if horas else None}, f, indent=2)


# ---------------------------------------------------------------------------
# Stage 6: errores
# ---------------------------------------------------------------------------
def stage_errores(indice, V, features):
    os.makedirs(DIR_VAL, exist_ok=True)
    filas, aucs, scores_s, y_te, E = run_experimento(indice, V, SEED_BASE, extra_modelos=False)
    z_e = scores_s["ENSEMBLE_Z"][1]
    thr_q01 = np.quantile(scores_s["ENSEMBLE_Z"][0], QQ["q01"])
    al = (z_e < thr_q01)
    idx_test = E["idx_test"]
    yt = y_te
    runs = [E["runs"][i] for i in idx_test]
    origen = [E["origen"][i] for i in idx_test]

    fn_rows, fp_rows = [], []
    for k in range(len(idx_test)):
        ov = "normal" if not yt[k] else ("borde" if es_borde(origen[k]) else "fault")
        if yt[k] and not al[k]:
            fn_rows.append(ov)
        elif not yt[k] and al[k]:
            fp_rows.append(ov)
    import collections
    print("FN (fault no alertado) por tipo:", collections.Counter(fn_rows))
    print("FP (normal alertado) por tipo:", collections.Counter(fp_rows))

    # contribución T²/SPE por variable para las ventanas con error (FP)
    if fp_rows:
        contrib = contribucion_spe(indice, V, E, al, yt, idx_test, origin=origen, features=features)
        contrib.to_csv(os.path.join(DIR_VAL, "errores_fp_contribucion.csv"), index=False, encoding="utf-8-sig")
        print("\nTop contribuyentes por FP (SPE por variable):")
        print(contrib.head(20).to_string())
    else:
        log("Sin FP en q01:")

    # scores de las ventanas FN (para explicar el umbral)
    fn_score = [float(z_e[k]) for k in range(len(idx_test)) if yt[k] and not al[k]]
    print(f"\nScore q01 de {len(fn_score)} ventanas fault-no-alertadas vs umbral {thr_q01:.4f}")
    if fn_score:
        arr = np.array(fn_score)
        print(f"  min={arr.min():.3f} mediana={np.median(arr):.3f} max={arr.max():.3f}")

    with open(os.path.join(DIR_VAL, "errores_resumen.json"), "w", encoding="utf-8") as f:
        json.dump({"fn": dict(collections.Counter(fn_rows)),
                    "fp": dict(collections.Counter(fp_rows))}, f, indent=2)


def es_borde(ventana, tl_margen=0.0):
    """Ventana que cruza el timeline con solapamiento parcial (borde)."""
    import glob
    run = ventana["run"]
    ini = pd.to_datetime(ventana["inicio"])
    fin = pd.to_datetime(ventana["fin"])
    inis, fins = [], []
    for rr in sorted(set(
            glob.glob(os.path.join(config.DIR_CORRIDAS, "anomalias", "*", "anomalias_timeline.csv"))
            + glob.glob(os.path.join(config.DIR_CORRIDAS, "*", "anomalias_timeline.csv")))):
        if os.path.basename(os.path.dirname(rr)) != run:
            continue
        tl = pd.read_csv(rr, encoding="utf-8-sig")
        inis += list(pd.to_datetime(tl["inicio"]))
        fins += list(pd.to_datetime(tl["fin"]))
    for a, b in zip(inis, fins):
        if ini > a and fin < b and fin > a and ini < b:
            if (fin - a).total_seconds() < (b - a).total_seconds() * 0.9:
                return True
    return False


def contribucion_spe(indice, V, E, al, yt, idx_test, origin, features):
    """PCA sobre normales de train; T² y SPE por ventana, contribución por variable."""
    F = len(indice)
    tr = E["raw"][E["idx_train"]][:, :, indice]
    sc = StandardScaler().fit(tr.reshape(-1, F))
    Xt = sc.transform(tr.reshape(-1, F)).reshape(-1, V, F).reshape(len(E["idx_train"]), -1)
    pca = PCA(n_components=min(8, len(E["idx_train"]) - 1)).fit(Xt)
    lam = pca.explained_variance_[:pca.n_components_]

    filas = []
    for k in range(len(idx_test)):
        if not (idx_test[k] in idx_test and (al[k] ^ yt[k])):  # len idx alignment
            pass
        if (not yt[k]) and al[k]:
            w = E["raw"][idx_test[k]][:, indice]
            Xw = sc.transform(w.reshape(-1, F)).reshape(1, -1)
            t = pca.transform(Xw)
            T2 = float(((t**2) / lam[np.newaxis, :]).sum(axis=1)[0])
            res = Xw - pca.inverse_transform(t)
            SPE = float((res**2).sum())
            resid2 = (res**2)[0].reshape(V, F)
            contr = resid2.sum(axis=0)
            orden = np.argsort(-contr)
            top = [(features[indice[j]], float(contr[j])) for j in orden[:3]]
            filas.append({"run": origin[k]["run"], "inicio": origin[k]["inicio"],
                          "T2": round(T2, 2), "SPE": round(SPE, 2),
                          "top1": top[0][0], "top2": top[1][0], "top3": top[2][0]
                          if len(top) > 2 else ""})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Stage 7: robustez
# ---------------------------------------------------------------------------
def stage_robustez(features, V):
    os.makedirs(DIR_VAL, exist_ok=True)
    bundle = joblib.load(os.path.join(DIR_VAL, "modelo_candidato.joblib"))
    sc = bundle["scaler"]; iso = bundle["iso"]; cop = bundle["copod"]
    ens = bundle["ens_stats"]; umb = bundle["umbrales"]["q01"]
    F = len(bundle["features"])
    feat_22 = preparar_muestra(os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl"))["features"]
    indice = [feat_22.index(c) for c in bundle["features"]]

    E = cargar_experimento()
    idx_norm = E["idx_test_norm"]; idx_fault = E["idx_test_fault"]
    i_sets = {"normal": idx_norm, "falla": idx_fault}

    def preparar(idx):
        rawv = E["raw"][idx][:, :, indice]
        n = len(idx)
        return sc.transform(rawv.reshape(-1, F)).reshape(-1, V, F).reshape(n, -1)

    def ens_score(Xe):
        si = iso.decision_function(Xe); scp = -cop.decision_function(Xe)
        return z_score(si, scp, ens)

    rng = np.random.default_rng(SEED_BASE)
    res = {}
    for clase, idx in i_sets.items():
        if len(idx) == 0:
            continue
        X = preparar(idx)
        base_dec = ens_score(X) < umb
        for nombre, perturb_fn in [
            ("ruido_z005", lambda v: v + rng.normal(0, 0.05, v.shape)),
            ("escala_x5_una_var", lambda v: aplicar_escala(v, rng, F, V)),
            ("nan_una_var", lambda v: aplicar_nan(v, V)),
        ]:
            det = []
            for i in range(len(idx)):
                pert = perturb_fn(X[i:i + 1].copy())
                with np.errstate(all="ignore"):
                    s = ens_score(pert)[0]
                flip = bool((s < umb) != base_dec[i])
                det.append({"clase": clase, "prueba": nombre, "ventana": i,
                            "base": bool(base_dec[i]), "flip": flip,
                            "score_pert": float(s)})
            df = pd.DataFrame(det)
            n_flip = int(df["flip"].sum())
            res[f"{clase}::{nombre}"] = {"n": len(idx), "flips": n_flip,
                                          "tasa_flips": round(n_flip / len(idx), 4)}
            print(f"  {clase} | {nombre}: {n_flip}/{len(idx)} cambios de decision "
                  f"({n_flip / len(idx):.2%})")

        # delta numerico (ruido) para referencia
        Xp = rng.normal(0, 0.05, X.shape)
        deltas = ens_score(X + Xp) - ens_score(X)
        res[f"{clase}::delta_ruido"] = {"delta_medio": round(float(deltas.mean()), 3),
                                        "max_abs": round(float(np.abs(deltas).max()), 3),
                                        "umbral_q01": float(umb)}
        print(f"  {clase} | delta score ruido: medio={deltas.mean():+.3f} max|.|={np.abs(deltas).max():.3f}")

    # NaN sobre la primera ventana normal (referencia)
    Xn = preparar(idx_norm)
    perturb = Xn[0:1].copy()
    perturb[0, :V] = np.nan
    nan_score = None
    with np.errstate(all="ignore"):
        try:
            nan_score = float(ens_score(perturb)[0])
        except Exception as e:
            nan_score = "ERROR: " + str(e)
    res["nan_referencia_normal"] = {"score": str(nan_score), "umbral_q01": float(umb)}
    print(f"  NaN en una variable -> score: {nan_score} (umbral {umb})")

    ausente = verificar_features(bundle)
    res["compat_features"] = ausente
    print(f"  variable ausente -> {ausente}")
    with open(os.path.join(DIR_VAL, "robustez_resumen.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)


def aplicar_escala(v, rng, F, V):
    j = int(rng.integers(0, F))
    v[0, j * V:(j + 1) * V] *= 5.0
    return v


def aplicar_nan(v, V):
    j = int(np.random.default_rng(1).integers(0, V))
    v[0, j] = np.nan
    return v


def verificar_features(bundle):
    """Comprueba que el bundle reporta las 17 variables correctas y ventana."""
    feat = bundle["features"]
    if len(feat) != 17:
        return f"OJO: {len(feat)} variables (esperadas 17)"
    ok = all(c in config.VARIABLES_MODELO for c in feat)
    return "OK: 17 variables = VARIABLES_MODELO" if ok else "DESVIACION contra VARIABLES_MODELO"


# ---------------------------------------------------------------------------
# Stage 8: latencia
# ---------------------------------------------------------------------------
def stage_latencia(features, V):
    bundle = joblib.load(os.path.join(DIR_VAL, "modelo_candidato.joblib"))
    sc = bundle["scaler"]; iso = bundle["iso"]; cop = bundle["copod"]
    ens = bundle["ens_stats"]
    F = len(bundle["features"])
    train = preparar_muestra(os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl"))
    indice = [train["features"].index(c) for c in bundle["features"]]
    raw = (train["X"] * train["scaler"].scale_ + train["scaler"].mean_)[:, :, indice]
    n = raw.shape[0]
    X = sc.transform(raw.reshape(-1, F)).reshape(-1, V, F).reshape(n, -1)

    def ens_score(Xe):
        si = iso.decision_function(Xe); scp = -cop.decision_function(Xe)
        return z_score(si, scp, ens)

    n_lote = 2000
    reps = int(np.ceil(n_lote / n)) if n < n_lote else 1
    rep = (np.repeat(raw, reps, axis=0)[:n_lote] if n < n_lote else raw[:n_lote])
    Xl = sc.transform(rep.reshape(-1, F)).reshape(-1, V, F).reshape(n_lote, -1)
    t0 = time.perf_counter()
    ens_score(Xl)
    tot = time.perf_counter() - t0
    us = tot / n_lote * 1e6
    print(f"\n=== LATENCIA (lote {n_lote}) ===")
    print(f"  {us:.1f} µs/ventana (media); {tot:.3f}s total ({us / 1e6:.6f}s)")
    with open(os.path.join(DIR_VAL, "latencia.json"), "w", encoding="utf-8") as f:
        json.dump({"n": n_lote, "seg_por_ventana": tot / n_lote,
                   "us_por_ventana": us}, f, indent=2)


# ---------------------------------------------------------------------------
# Stage 9: integración (Detector de producción)
# ---------------------------------------------------------------------------
def stage_integ(features, V):
    import sys
    try:
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        sys.path.insert(0, backend_root)
        from app.ml.detector import Detector
        det = Detector(
            ruta_modelo=os.path.join(config.DIR_DETECCION, "modelo_isolation_forest.joblib"),
            ruta_scaler=os.path.join(config.DIR_DETECCION, "scaler.joblib"),
            ruta_features=os.path.join(config.DIR_CORRELACION, "features_modelo.csv"),
            ruta_train_pkl=os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl"),
            ventana=V, umbral_nombre="q01",
            ruta_modelo_copod=os.path.join(config.DIR_DETECCION, "modelo_copod.joblib"),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        with open(os.path.join(DIR_VAL, "integracion.json"), "w", encoding="utf-8") as f:
            json.dump({"ok": False, "error": str(e)}, f, indent=2)
        return
    # muestra real: primer ventana del test pkl como V observaciones de 22 vars
    test = preparar_muestra(os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl"))
    muestras = [dict(zip(test["features"], [float(v) for v in row])) for row in test["X"][0]]
    try:
        res = det.evaluar_lote("nodo_test", muestras)
        with open(os.path.join(DIR_VAL, "integracion.json"), "w", encoding="utf-8") as f:
            json.dump({"ok": True, "respuestas": res}, f, indent=2, default=str)
        print("\n=== INTEGRACIÓN (Detector producción) ===")
        print(res[-2:])
    except Exception as e:
        import traceback
        traceback.print_exc()
        with open(os.path.join(DIR_VAL, "integracion.json"), "w", encoding="utf-8") as f:
            json.dump({"ok": False, "error": str(e)}, f, indent=2)


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["metrics", "seeds", "vars", "freeze",
                                        "oper", "errores", "robustez", "latencia",
                                        "integ", "todo"], default="todo")
    args = ap.parse_args()

    features = preparar_muestra(os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl"))["features"]
    indice = seleccionar(os.path.join(config.DIR_CORRELACION, "features_modelo.csv"), features)
    V = preparar_muestra(os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl"))["ventana"]

    stages = [("metrics", lambda: stage_metrics(indice, V)),
              ("seeds", lambda: stage_seeds(indice, V)),
              ("vars", lambda: stage_vars(indice, V, features)),
              ("freeze", lambda: stage_freeze(features, V)),
              ("oper", lambda: stage_oper(indice, V)),
              ("errores", lambda: stage_errores(indice, V, features)),
              ("robustez", lambda: stage_robustez(features, V)),
              ("latencia", lambda: stage_latencia(features, V)),
              ("integ", lambda: stage_integ(features, V))]
    if args.stage == "todo":
        for nombre, fn in stages:
            log(f"--- STAGE {nombre} ---")
            fn()
    else:
        for nombre, fn in stages:
            if nombre == args.stage:
                fn()
                break
    log("Validacion finalizada.")


if __name__ == "__main__":
    main()
