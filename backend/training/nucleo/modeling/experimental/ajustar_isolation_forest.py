"""
ajustar_isolation_forest.py
===========================

Estudio OFF LINE de afinamiento de IsolationForest SOLO (no toca 03,
ni artefactos, ni la produccion).

Reproduce el protocolo EXACTO de medir_discriminacion.py para que las
metricas sean comparables con informe_discriminacion.csv:

  - NORMALES: leave-one-corrida-out sobre las ventanas de train (cada
    corrida puntuada por un modelo entrenado con el resto; umbrales del
    fold-train).
  - FALLOS: las ventanas de test (las que cruzan un fault del timeline),
    modelo con TODO el normal.

Por cada configuracion de grilla reporta DOS esquemas al mismo tiempo:

  - ISOLATION_FOREST (el modelo tunado en solitario)
  - ENSEMBLE_Z (ISO tunado + componente COPOD fija contamination=0.05)

Fase 1 (principal): grilla hiperparametrica con preprocesado standard y
las 17 features actuales -> 135 configs.
Fase 2 (exploracion): las top-N configs de la fase 1 (por F1 con gate de
FPR) re-evaluadas bajo preprocesados {standard, robust, pca-whitening} y
subespacios {17, 12, 10} (las k mejores por importancia de referencia).

Criterio de aceptacion (objetivo = nivel ENSEMBLE_Z q01 de produccion):
  FPR_LOO <= TARGET_FPR (default 0.0174) Y TPR_test >= TARGET_TPR (0.95).

Salidas (en deteccion/grilla_iso/):
  grilla_iso.csv            todas las filas evaluadas
  grilla_iso_ranking.csv    top-10 por F1 bajo el gate estricto
  importancia_referencia.csv  importancia del ISO de referencia

Uso:
  python experimental/ajustar_isolation_forest.py [--top N] [--no-extra]
      [--max-configs N]
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

# UNICA fuente del ENSEMBLE_Z (z-score de componentes) -> app/ml/ensamble_z.py
from app.ml.ensamble_z import estadisticas, z_score  # noqa: E402

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler, StandardScaler
from pyod.models.copod import COPOD

import config

_QQ = {"q10": 0.10, "q05": 0.05, "q01": 0.01}

TARGET_FPR = float(os.getenv("STEELNORT_TUNING_FPR_MAX", "0.0174"))
TARGET_TPR = float(os.getenv("STEELNORT_TUNING_TPR_MIN", "0.95"))

GRID = {
    "contamination": [0.001, 0.005, 0.01, 0.02, 0.05],
    "n_estimators": [100, 300, 500],
    "max_samples": [64, 128, "auto"],
    "max_features": [0.5, 0.7, 1.0],
}

PREP_LIST = ["standard", "robust", "pca"]
SUBSET_LIST = [17, 12, 10]
PCA_COMPONENTES = 12

PROMOCION = {
    "standard": "directo",
    "robust": "requiere-robust",
    "pca": "requiere-pca",
}


def cargar(ruta):
    with open(ruta, "rb") as f:
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
        import glob

        rutas = []
        rutas += glob.glob(os.path.join(
            config.DIR_CORRIDAS, "anomalias", "*", "anomalias_timeline.csv"))
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
    except Exception as exc:
        print(f"[AVISO] timeline no disponible ({exc}); asumo todas fault")
        return np.ones(len(test["runs"]), dtype=bool)


def raw_subset(X_escalado, scaler, indice):
    return (X_escalado * scaler.scale_ + scaler.mean_)[:, :, indice]


def hacer_prep(prep, n_feats):
    if prep == "standard":
        return StandardScaler()
    if prep == "robust":
        return RobustScaler()
    return Pipeline([
        ("sc", StandardScaler()),
        ("pca", PCA(n_components=min(PCA_COMPONENTES, n_feats), whiten=True)),
    ])


def fit_iso(Xt, conf):
    kw = {"random_state": config.SEED, "n_jobs": -1}
    kw.update(conf)
    return IsolationForest(**kw).fit(Xt)


def metricas(tp, fn, fp, tn):
    n_fault = tp + fn
    n_norm = fp + tn
    tpr = tp / n_fault if n_fault else 0.0
    fpr = fp / n_norm if n_norm else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = (2 * prec * tpr / (prec + tpr)) if (prec + tpr) else 0.0
    acc = (tp + tn) / (n_fault + n_norm) if (n_fault + n_norm) else 0.0
    return dict(tpr=tpr, fpr=fpr, precision=prec, f1=f1, accuracy=acc)


def importancia_referencia(raw_tr, indice, V):
    F = len(indice)
    sc = StandardScaler().fit(raw_tr.reshape(-1, F))
    Xt = sc.transform(raw_tr.reshape(-1, F)).reshape(-1, V, F).reshape(-1, V * F)
    iso = fit_iso(Xt, {"contamination": "auto"})
    imp = np.mean([t.feature_importances_ for t in iso.estimators_], axis=0)
    agg = {c: float(np.abs(imp[i * V:(i + 1) * V]).mean())
           for i, c in enumerate(range(F))}
    orden = sorted(range(F), key=lambda i: agg[i], reverse=True)
    return orden, iso


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=4,
                    help="top-N configs de la fase 1 para la fase 2")
    ap.add_argument("--max-configs", type=int, default=0,
                    help="cap para la grilla base (0 = completa)")
    ap.add_argument("--no-extra", action="store_true",
                    help="omitir la fase 2 (prep/subconjuntos)")
    args = ap.parse_args()

    ruta_train = os.path.join(config.DIR_MODELADO, "dataset_muestras_train.pkl")
    ruta_test = os.path.join(config.DIR_MODELADO, "dataset_muestras_test.pkl")
    if not (os.path.exists(ruta_train) and os.path.exists(ruta_test)):
        print("[AJUSTE] Faltan pkl. Ejecuta 01_muestras.py.")
        return

    train = cargar(ruta_train)
    test = cargar(ruta_test)
    indice17 = seleccionar(
        os.path.join(config.DIR_CORRELACION, "features_modelo.csv"),
        train["features"])
    F_sel = len(indice17)
    V = train["ventana"]

    raw_tr = raw_subset(train["X"], train["scaler"], indice17)
    raw_te = raw_subset(test["X"], train["scaler"], indice17)
    es_fault = marcar_fault(test)
    corridas = sorted(set(train["runs"]))

    n_norm = len(train["runs"])
    n_fault = int(es_fault.sum())

    print(f"[AJUSTE] Normales LOO: {n_norm} | Fallos: {n_fault} | "
          f"features {F_sel} | ventana {V}")
    print(f"[AJUSTE] Gate estricto: FPR<={TARGET_FPR:.4f} TPR>={TARGET_TPR:.2f}")
    print("ESTA HERRAMIENTA NO MODIFICA 03 NI ARTEFACTOS DE PRODUCCION\n")

    nombres = [train["features"][i] for i in indice17]
    orden_imp, _ = importancia_referencia(raw_tr, indice17, V)
    subs = {}
    for k in SUBSET_LIST:
        kk = min(k, len(orden_imp))
        subs[k] = list(orden_imp[:kk])

    def aplanar(raw3d):
        n = raw3d.shape[0]
        v = raw3d.shape[1]
        f = raw3d.shape[2]
        return raw3d.reshape(n, v * f)

    def transformar(p, X2d, v):
        t = p.transform(X2d)
        w = t.shape[1]
        return t.reshape(-1, v, w)

    def preproc(prep, feats, X2d):
        p = hacer_prep(prep, len(feats))
        return p.fit(X2d)

    cache_copod = {}

    def copod_scores(prep, feats, clave, Xt, Xe):
        key = (prep, tuple(feats), clave)
        if key not in cache_copod:
            cop = COPOD(contamination=0.05).fit(Xt)
            cache_copod[key] = (
                -cop.decision_function(Xt),
                -cop.decision_function(Xe),
            )
        return cache_copod[key]

    filas = []

    def evaluar(fase, conf, prep, feats, etiqueta):
        F = len(feats)
        alert_norm = {u: {"iso": np.zeros(n_norm, dtype=bool),
                          "ens": np.zeros(n_norm, dtype=bool)}
                      for u in _QQ}
        for c in corridas:
            idx_c = [i for i, r in enumerate(train["runs"]) if r == c]
            idx_tr = [i for i in range(len(train["runs"])) if i not in idx_c]
            p = preproc(prep, feats, raw_tr[idx_tr][:, :, feats].reshape(-1, F))
            Xt = aplanar(transformar(p, raw_tr[idx_tr][:, :, feats].reshape(-1, F), V))
            Xc = aplanar(transformar(p, raw_tr[idx_c][:, :, feats].reshape(-1, F), V))

            iso = fit_iso(Xt, conf)
            s_iso_t = iso.decision_function(Xt)
            s_iso_c = iso.decision_function(Xc)
            s_cop_t, s_cop_c = copod_scores(prep, feats, "f:" + c, Xt, Xc)
            ens = estadisticas(s_iso_t, s_cop_t)

            for q, v in _QQ.items():
                thr_iso = np.quantile(s_iso_t, v)
                alert_norm[q]["iso"][idx_c] = s_iso_c < thr_iso
                z_t = z_score(s_iso_t, s_cop_t, ens)
                z_c = z_score(s_iso_c, s_cop_c, ens)
                thr_ens = np.quantile(z_t, v)
                alert_norm[q]["ens"][idx_c] = z_c < thr_ens

        p = preproc(prep, feats, raw_tr[:, :, feats].reshape(-1, F))
        Xt = aplanar(transformar(p, raw_tr[:, :, feats].reshape(-1, F), V))
        Xte = aplanar(transformar(p, raw_te[:, :, feats].reshape(-1, F), V))

        iso = fit_iso(Xt, conf)
        s_iso_t = iso.decision_function(Xt)
        s_iso_te = iso.decision_function(Xte)
        s_cop_t, s_cop_te = copod_scores(prep, feats, "full", Xt, Xte)
        ens = estadisticas(s_iso_t, s_cop_t)

        base = {
            "fase": fase, "prep": prep, "n_feats": F,
            "subset": etiqueta,
            "promocionable": PROMOCION[prep],
            "contamination": conf["contamination"],
            "n_estimators": conf["n_estimators"],
            "max_samples": conf["max_samples"],
            "max_features": conf["max_features"],
        }
        for q, v in _QQ.items():
            thr_iso = np.quantile(s_iso_t, v)
            a_iso_f = s_iso_te < thr_iso
            tp_i = int(a_iso_f.sum())
            fp_i = int(alert_norm[q]["iso"].sum())
            m_i = metricas(tp_i, n_fault - tp_i, fp_i, n_norm - fp_i)

            z_t = z_score(s_iso_t, s_cop_t, ens)
            z_te = z_score(s_iso_te, s_cop_te, ens)
            thr_ens = np.quantile(z_t, v)
            tp_e = int((z_te < thr_ens).sum())
            fp_e = int(alert_norm[q]["ens"].sum())
            m_e = metricas(tp_e, n_fault - tp_e, fp_e, n_norm - fp_e)

            filas.append({
                **base, "umbral": q,
                "iso_tp": tp_i, "iso_fp": fp_i,
                "iso_tpr": round(m_i["tpr"], 4), "iso_fpr": round(m_i["fpr"], 4),
                "iso_precision": round(m_i["precision"], 4),
                "iso_f1": round(m_i["f1"], 4), "iso_accuracy": round(m_i["accuracy"], 4),
                "ens_tp": tp_e, "ens_fp": fp_e,
                "ens_tpr": round(m_e["tpr"], 4), "ens_fpr": round(m_e["fpr"], 4),
                "ens_precision": round(m_e["precision"], 4),
                "ens_f1": round(m_e["f1"], 4), "ens_accuracy": round(m_e["accuracy"], 4),
            })

    def configs_grilla():
        c = []
        for cont in GRID["contamination"]:
            for n_est in GRID["n_estimators"]:
                for ms in GRID["max_samples"]:
                    for mf in GRID["max_features"]:
                        c.append({"contamination": cont, "n_estimators": n_est,
                                  "max_samples": ms, "max_features": mf})
        return c

    base_configs = configs_grilla()
    base_configs.append({"contamination": "auto", "n_estimators": 100,
                         "max_samples": "auto", "max_features": 1.0})
    if args.max_configs and args.max_configs > 0:
        base_configs = base_configs[:args.max_configs]
    print(f"[AJUSTE] Fase 1: {len(base_configs)} configs "
          f"(standard/17 features, orden de produccion)...")
    for i, conf in enumerate(base_configs, 1):
        # Usar el orden de COLUMNAS de produccion (indice17), NO subs[17]
        # (orden por importancia): ISO con seed fija y max_features<1.0 NO es
        # invariante a permutar columnas y cambiaba el recuento de FP.
        evaluar("fase1", conf, "standard", indice17, "17")
        if i % 20 == 0 or i == len(base_configs):
            print(f"  fase1 {i}/{len(base_configs)} evaluadas")

    if not args.no_extra:
        df_tmp = pd.DataFrame(filas)
        mask = df_tmp["iso_fpr"] <= TARGET_FPR
        base_f1_q01 = df_tmp[df_tmp["umbral"] == "q01"]
        if not mask.any():
            mejores = (base_f1_q01
                       .sort_values("iso_f1", ascending=False)
                       .drop_duplicates(subset=["contamination", "n_estimators",
                                                "max_samples", "max_features"])
                       .head(args.top))
        else:
            mejores = (df_tmp[mask]
                       .sort_values("iso_f1", ascending=False)
                       .drop_duplicates(subset=["contamination", "n_estimators",
                                                "max_samples", "max_features"])
                       .head(args.top))
        top_configs = mejores[["contamination", "n_estimators",
                               "max_samples", "max_features"]].to_dict("records")
        combos_extra = [(p, s) for p in PREP_LIST for s in SUBSET_LIST
                        if not (p == "standard" and s == 17)]
        print(f"[AJUSTE] Fase 2: {len(top_configs)} configs x "
              f"{len(combos_extra)} (prep,subset)...")
        for conf in top_configs:
            for prep, s in combos_extra:
                evaluar("fase2", conf, prep, subs[s], str(s))
        print("  fase2 completa")

    df = pd.DataFrame(filas)
    basel = df[(df["contamination"] == "auto") & (df["n_estimators"] == 100)
               & (df["max_samples"] == "auto") & (df["max_features"] == 1.0)
               & (df["prep"] == "standard") & (df["subset"] == "17")
               & (df["umbral"] == "q01")]
    if not basel.empty:
        b = basel.iloc[0]
        print("\n=== SANIDAD: config baseline (auto/100/auto/1.0) ===")
        print(f"  ISO solo   -> TPR={b['iso_tpr']:.2%} FPR={b['iso_fpr']:.2%} "
              f"F1={b['iso_f1']:.3f} (esperado FPR 27.0% F1 0.777)")
        print(f"  ENSEMBLE_Z -> TPR={b['ens_tpr']:.2%} FPR={b['ens_fpr']:.2%} "
              f"F1={b['ens_f1']:.3f} (esperado FPR 1.74% F1 0.9818)")

    dir_out = os.path.join(config.DIR_DETECCION, "grilla_iso")
    os.makedirs(dir_out, exist_ok=True)

    cols = ["fase", "contamination", "n_estimators", "max_samples",
            "max_features", "prep", "n_feats", "subset", "promocionable",
            "umbral",
            "iso_tp", "iso_fp", "iso_tpr", "iso_fpr", "iso_precision",
            "iso_f1", "iso_accuracy",
            "ens_tp", "ens_fp", "ens_tpr", "ens_fpr", "ens_precision",
            "ens_f1", "ens_accuracy"]
    df.to_csv(os.path.join(dir_out, "grilla_iso.csv"), index=False,
              encoding="utf-8-sig", columns=cols)

    for esquema in ("iso", "ens"):
        base = df[df["umbral"] == "q01"].copy()
        con_gate = base[base[f"{esquema}_fpr"] <= TARGET_FPR]
        ranking = con_gate.sort_values(f"{esquema}_f1", ascending=False)
        if ranking.empty:
            ranking = base.sort_values(f"{esquema}_f1", ascending=False).head(10)
        ranking.head(10).to_csv(
            os.path.join(dir_out, f"grilla_iso_ranking_{esquema}.csv"),
            index=False, encoding="utf-8-sig")

    orden_ref = pd.DataFrame([{"columna": nombres[i], "pos_importancia": i + 1}
                              for i in orden_imp])
    orden_ref.to_csv(os.path.join(dir_out, "importancia_referencia.csv"),
                     index=False, encoding="utf-8-sig")

    print("\n=== RESUMEN (umbral q01) ===")
    print("--- ISO SOLO ---")
    mejor_iso = df[df["umbral"] == "q01"].sort_values("iso_f1", ascending=False)
    for _, r in mejor_iso.head(6).iterrows():
        print(f"  cont={r['contamination']:<5} ne={r['n_estimators']:<3} "
              f"ms={str(r['max_samples']):<4} mf={r['max_features']:<4} "
              f"prep={r['prep']:<8} k={r['subset']:<3} "
              f"TPR={r['iso_tpr']:.2%} FPR={r['iso_fpr']:.2%} "
              f"F1={r['iso_f1']:.3f} [{r['promocionable']}]")
    print("--- ISO + COPOD (ENSEMBLE_Z) ---")
    mejor_ens = df[df["umbral"] == "q01"].sort_values("ens_f1", ascending=False)
    for _, r in mejor_ens.head(6).iterrows():
        print(f"  cont={r['contamination']:<5} ne={r['n_estimators']:<3} "
              f"ms={str(r['max_samples']):<4} mf={r['max_features']:<4} "
              f"prep={r['prep']:<8} k={r['subset']:<3} "
              f"TPR={r['ens_tpr']:.2%} FPR={r['ens_fpr']:.2%} "
              f"F1={r['ens_f1']:.3f}")

    def resumen_gate(esquema, base_f1):
        sel = df[df["umbral"] == "q01"]
        con = sel[sel[f"{esquema}_fpr"] <= TARGET_FPR]
        if con.empty:
            fila = sel.sort_values(f"{esquema}_f1", ascending=False).iloc[0]
            print(f"[GATE] {esquema.upper()}: sin config bajo FPR "
                  f"{TARGET_FPR:.3f}; mejor libre F1={fila[f'{esquema}_f1']:.3f}")
            return
        fila = con.sort_values(f"{esquema}_f1", ascending=False).iloc[0]
        ok_tpr = fila[f"{esquema}_tpr"] >= TARGET_TPR
        print(f"[GATE] {esquema.upper()} -> TPR={fila[f'{esquema}_tpr']:.2%} "
              f"FPR={fila[f'{esquema}_fpr']:.2%} F1={fila[f'{esquema}_f1']:.3f} "
              f"(baseline ENSEMBLE_Z q01 F1={base_f1:.3f}) | target TPR>= "
              f"{TARGET_TPR:.2%}: {'OK' if ok_tpr else 'FALTA'} "
              f"[conf: cont={fila['contamination']} ne={fila['n_estimators']} "
              f"ms={fila['max_samples']} mf={fila['max_features']} "
              f"prep={fila['prep']} k={fila['subset']}]")

    print("\n=== CRITERIO DE ACEPTACION ===")
    resumen_gate("iso", 0.9818)
    resumen_gate("ens", 0.9818)
    print(f"\n[OK] Detalle completo: {dir_out}/grilla_iso.csv")
    with open(os.path.join(dir_out, "resumen.json"), "w", encoding="utf-8") as f:
        json.dump({
            "target_fpr": TARGET_FPR, "target_tpr": TARGET_TPR,
            "n_fase1": len(base_configs),
            "n_filas": len(filas),
            "mejor_iso_q01": mejor_iso[mejor_iso["umbral"] == "q01"][
                ["contamination", "n_estimators", "max_samples",
                 "max_features", "prep", "subset", "iso_tpr", "iso_fpr",
                 "iso_f1"]].head(6).to_dict("records"),
            "mejor_ens_q01": mejor_ens[mejor_ens["umbral"] == "q01"][
                ["contamination", "n_estimators", "max_samples",
                 "max_features", "prep", "subset", "ens_tpr", "ens_fpr",
                 "ens_f1"]].head(6).to_dict("records"),
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
