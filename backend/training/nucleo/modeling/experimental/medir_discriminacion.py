"""
medir_discriminacion.py
=======================

Medición INTEGRADA de discriminación (TPR + FPR + Precisión + F1 + matriz
de confusión) sobre un set etiquetado que mezcla NORMAL y FALLO.

Corrige el hueco de la suite (06): el test del pipeline solo contiene
ventanas de fallo (108), por lo que la tabla comparativa reporta FPR vacío
y un TPR 100% que no demuestra discriminación.

Diseño (todo out-of-sample):
    - NORMALES: las 230 ventanas de train, evaluadas leave-one-corrida-out
      (cada corrida es puntuada por un modelo entrenado con el resto; sus
      umbrales salen de ese fold-train). Etiqueta = 0.
    - FALLOS: las 108 ventanas del test (todas cruzan un fault del
      timeline). Modelo y umbrales entrenados con TODO el normal.
      Etiqueta = 1. Jamás entran a ningún train.

Esquemas (mismas condiciones: 17 variables, mismo scaler, mismos
percentiles, convención "score < umbral = alerta"):
    ISOLATION_FOREST, COPOD, ENSEMBLE_Z (media de scores z),
    AND_COPOD_ISOF, OR_COPOD_ISOF

Métricas por umbral q10/q05/q01:
    TPR = alertas / fallos ; FPR = alertas / normales
    Precisión = TP/(TP+FP) ; F1 = armónica(Precisión, TPR)
    Matriz de confusión en el umbral operativo.

Salidas (deteccion/):
    informe_discriminacion.csv
    informe_discriminacion.json
"""

import json
import os
import pickle
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

# UNICA fuente del ENSEMBLE_Z (z-score de componentes) -> app/ml/ensamble_z.py
from app.ml.ensamble_z import estadisticas, z_score  # noqa: E402

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from pyod.models.copod import COPOD

import config

_QQ = {"q10": 0.10, "q05": 0.05, "q01": 0.01}
COMBOS = ["ISOLATION_FOREST", "COPOD", "ENSEMBLE_Z",
          "AND_COPOD_ISOF", "OR_COPOD_ISOF"]


def cargar(r):
    with open(r, "rb") as f:
        return pickle.load(f)


def seleccionar(ruta_csv, features):
    preferidas = list(config.VARIABLES_MODELO)
    if os.path.exists(ruta_csv):
        cols = pd.read_csv(ruta_csv, encoding="utf-8-sig").iloc[:, 0]
        cols = cols.astype(str).str.strip().tolist()
        if cols:
            preferidas = cols
    inter = [c for c in preferidas if c in features]
    return [features.index(c) for c in inter]


def marcar_fault(test):
    try:
        rutas = []
        for grupo in ("anomalias",):
            import glob
            rutas += glob.glob(os.path.join(
                config.DIR_CORRIDAS, grupo, "*", "anomalias_timeline.csv"))
        frames = []
        for r in rutas:
            run = os.path.basename(os.path.dirname(r))
            t = pd.read_csv(r, encoding="utf-8-sig")
            t["run_name"] = run
            frames.append(t)
        tl = pd.concat(frames, ignore_index=True)
        tl["inicio"] = pd.to_datetime(tl["inicio"])
        tl["fin"] = pd.to_datetime(tl["fin"])
        ef = np.zeros(len(test["runs"]), dtype=bool)
        for i, w in enumerate(test["ventanas"]):
            g = tl[tl["run_name"] == test["runs"][i]]
            if g.empty:
                continue
            ini = pd.Timestamp(w["inicio"])
            fin = pd.Timestamp(w["fin"])
            ef[i] = bool(((ini <= g["fin"]) & (fin >= g["inicio"])).any())
        return ef
    except Exception as e:
        print(f"[AVISO] timeline no disponible ({e}); asumo todas fault")
        return np.ones(len(test["runs"]), dtype=bool)


def scores_x(modelo, nombre, X):
    s = modelo.decision_function(X)
    return -s if nombre == "COPOD" else s


def umbral(combo, s_iso_tr, s_cop_tr, ens, qq):
    if combo == "ISOLATION_FOREST":
        return np.quantile(s_iso_tr, qq)
    if combo == "COPOD":
        return np.quantile(s_cop_tr, qq)
    if combo == "ENSEMBLE_Z":
        z = z_score(s_iso_tr, s_cop_tr, ens)
        return np.quantile(z, qq)
    if combo == "AND_COPOD_ISOF":
        return (np.quantile(s_iso_tr, qq), np.quantile(s_cop_tr, qq))
    if combo == "OR_COPOD_ISOF":
        return (np.quantile(s_iso_tr, qq), np.quantile(s_cop_tr, qq))
    raise ValueError(combo)


def alerta(combo, s_iso, s_cop, ens, thr):
    if combo == "ISOLATION_FOREST":
        return s_iso < thr
    if combo == "COPOD":
        return s_cop < thr
    if combo == "ENSEMBLE_Z":
        z = z_score(s_iso, s_cop, ens)
        return z < thr
    if combo in ("AND_COPOD_ISOF", "OR_COPOD_ISOF"):
        a = s_iso < thr[0]
        b = s_cop < thr[1]
        return (a & b) if combo == "AND_COPOD_ISOF" else (a | b)
    raise ValueError(combo)


def main():
    ruta_train = os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl")
    ruta_test = os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl")
    if not (os.path.exists(ruta_train) and os.path.exists(ruta_test)):
        print("[DISC] Faltan pkl. Ejecuta 01_muestras.py.")
        return

    train = cargar(ruta_train)
    test = cargar(ruta_test)
    indice = seleccionar(os.path.join(config.DIR_CORRELACION, "features_modelo.csv"),
                         train["features"])
    F_sel = len(indice)
    V = train["ventana"]

    def flat(raw, n):
        return raw.reshape(n, V * F_sel)

    raw_tr = (train["X"] * train["scaler"].scale_ + train["scaler"].mean_)[:, :, indice]
    raw_te = (test["X"] * test["scaler"].scale_ + test["scaler"].mean_)[:, :, indice]
    es_fault = marcar_fault(test)
    corridas = sorted(set(train["runs"]))

    n_fault = int(es_fault.sum())
    n_norm = len(train["runs"])
    print(f"[DISC] Normales: {n_norm} (LOO) | Fallos: {n_fault} | "
          f"features {F_sel} | ventana {V}")

    # alertas NORMALES: leave-one-corrida-out
    alert_norm = {combo: {q: np.zeros(n_norm, dtype=bool)
                          for q in _QQ} for combo in COMBOS}
    for c in corridas:
        idx_c = [i for i, r in enumerate(train["runs"]) if r == c]
        idx_tr = [i for i in range(len(train["runs"])) if i not in idx_c]
        sc = StandardScaler()
        sc.fit(raw_tr[idx_tr].reshape(-1, F_sel))
        Xt = flat(sc.transform(raw_tr[idx_tr].reshape(-1, F_sel)).reshape(-1, V, F_sel), len(idx_tr))
        Xc = flat(sc.transform(raw_tr[idx_c].reshape(-1, F_sel)).reshape(-1, V, F_sel), len(idx_c))

        iso = IsolationForest(random_state=config.SEED, contamination="auto", n_jobs=-1).fit(Xt)
        cop = COPOD(contamination=0.05).fit(Xt)
        s_iso_t, s_cop_t = scores_x(iso, "ISOLATION_FOREST", Xt), scores_x(cop, "COPOD", Xt)
        s_iso_c, s_cop_c = scores_x(iso, "ISOLATION_FOREST", Xc), scores_x(cop, "COPOD", Xc)
        ens = estadisticas(s_iso_t, s_cop_t)

        for combo in COMBOS:
            for q, v in _QQ.items():
                thr = umbral(combo, s_iso_t, s_cop_t, ens, v)
                alert_norm[combo][q][idx_c] = alerta(combo, s_iso_c, s_cop_c, ens, thr)

    # alertas FALLO: modelo con TODO el normal
    sc = StandardScaler()
    sc.fit(raw_tr.reshape(-1, F_sel))
    Xt = flat(sc.transform(raw_tr.reshape(-1, F_sel)).reshape(-1, V, F_sel), n_norm)
    Xte = flat(sc.transform(raw_te.reshape(-1, F_sel)).reshape(-1, V, F_sel), len(raw_te))

    iso = IsolationForest(random_state=config.SEED, contamination="auto", n_jobs=-1).fit(Xt)
    cop = COPOD(contamination=0.05).fit(Xt)
    s_iso_t, s_cop_t = scores_x(iso, "ISOLATION_FOREST", Xt), scores_x(cop, "COPOD", Xt)
    s_iso_te, s_cop_te = scores_x(iso, "ISOLATION_FOREST", Xte), scores_x(cop, "COPOD", Xte)
    ens = estadisticas(s_iso_t, s_cop_t)

    alert_fault = {combo: {q: np.zeros(n_fault, dtype=bool)
                           for q in _QQ} for combo in COMBOS}
    for combo in COMBOS:
        for q, v in _QQ.items():
            thr = umbral(combo, s_iso_t, s_cop_t, ens, v)
            alert_fault[combo][q][:] = alerta(combo, s_iso_te, s_cop_te, ens, thr)

    # ---- informe integrado ----
    filas = []
    for combo in COMBOS:
        for q in _QQ:
            tp = int(alert_fault[combo][q].sum())
            fn = n_fault - tp
            fp = int(alert_norm[combo][q].sum())
            tn = n_norm - fp
            tpr = tp / n_fault
            fpr = fp / n_norm
            prec = tp / (tp + fp) if (tp + fp) else 0.0
            f1 = (2 * prec * tpr / (prec + tpr)) if (prec + tpr) else 0.0
            acc = (tp + tn) / (n_fault + n_norm)
            filas.append({
                "esquema": combo, "umbral": q,
                "tp": tp, "fn": fn, "fp": fp, "tn": tn,
                "tpr": round(tpr, 4), "fpr": round(fpr, 4),
                "precision": round(prec, 4), "f1": round(f1, 4),
                "accuracy": round(acc, 4),
            })

    df = pd.DataFrame(filas)
    print("\n=== INFORMME DE DISCRIMINACION (set mixto: normales LOO + fallos) ===")
    print(df[["esquema", "umbral", "tp", "fn", "fp", "tn",
              "tpr", "fpr", "precision", "f1", "accuracy"]].to_string(index=False))

    # ---- ranking por F1 ----
    mejor = df.loc[df[df["fpr"] <= config.FPR_MAX_OBJETIVO]["f1"].idxmax()]
    print(f"\n[GATE FPR <= {config.FPR_MAX_OBJETIVO:.0%}] Mejor por F1: "
          f"{mejor['esquema']} @ {mejor['umbral']}  ->  "
          f"TPR={mejor['tpr']:.1%} FPR={mejor['fpr']:.1%} "
          f"F1={mejor['f1']:.3f} (TP={mejor['tp']}, FP={mejor['fp']})")

    os.makedirs(config.DIR_DETECCION, exist_ok=True)
    df.to_csv(os.path.join(config.DIR_DETECCION, "informe_discriminacion.csv"),
              index=False, encoding="utf-8-sig")
    with open(os.path.join(config.DIR_DETECCION, "informe_discriminacion.json"),
              "w", encoding="utf-8") as f:
        json.dump({
            "n_normales": n_norm, "n_fallos": n_fault,
            "variables": len(indice), "ventana": V,
            "objetivo_fpr": config.FPR_MAX_OBJETIVO,
            "mejor_con_gate": mejor.to_dict() if not mejor.empty else None,
            "detalle": filas,
        }, f, ensure_ascii=False, indent=2)
    print(f"[DISC] Informe en deteccion/informe_discriminacion.csv/.json")


if __name__ == "__main__":
    main()
