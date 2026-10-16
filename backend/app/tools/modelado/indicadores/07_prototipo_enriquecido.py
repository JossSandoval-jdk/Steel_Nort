"""
07_prototipo_enriquecido.py
===========================
PROTOTIPO — solo medicion, NO toca produccion.

Prueba si AGREGAR al espacio del modelo las variables que definen cada fallo
(lecturas/escrituras, page_reads, planes, locks por tabla, esperas, errores)
mejora I-3.1 (tipo) y I-3.3 (diagnostico) SIN degradar la deteccion.

Truco: `artefactos_modelo.pkl` ya trae X_train/X_test con las 69 features
escaladas; solo cambia la lista de indices seleccionados. NO reentrena el
scaler, NO escribe en produccion.

Mediciones:
  - Deteccion : protocolo honesto (dejar-una-corrida-fuera) base vs enriquecido.
  - Tipo      : RandomForest LORO sobre las ventanas de los artefactos.

Salida: output/modelado/indicadores/prototipo_enriquecido.json
"""

import importlib.util
import json
import os
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier

_AQUI = Path(__file__).resolve().parent


def _cargar(nombre, archivo):
    spec = importlib.util.spec_from_file_location(nombre, _AQUI / archivo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# El harness de candidatos sigue en experimental/; se reusa por ruta.
vc = _cargar("vc", "../experimental/03_validar_candidato.py")
hon = _cargar("hon", "01_validar_honesto.py")     # protocolo honesto (no corre main)
import etiquetas  # noqa: E402

DIR_VAL = os.path.join(vc.DIR_MODELADO, "indicadores")

# Variables que definen cada fallo y hoy NO estan en VARIABLES_MODELO.
EXTRAS = [
    "total_reads", "total_writes", "page_reads_per_sec", "page_writes_per_sec",
    "rollbacks_per_sec", "sql_compilations_per_sec",
    "cpu_idl", "cpu_stl", "load5", "load15",
    "memory_available_mb", "idle_sessions",
    "auditoria_locks", "caja_locks", "detalle_venta_locks", "inventario_locks",
    "kardex_locks", "movimiento_caja_locks", "venta_locks",
    "events_lock_acquired_count", "events_lock_released_count",
    "events_login_count", "events_logout_count",
    "batch_requests_per_sec",
]
# log_error_count / log_fatal_count fuera: ~10% de NaN en el dataset.
COMBOS_DETECCION = ["ENSEMBLE_LOF_ELL", "ISO_LOF_ELL"]


def indices_de(features, cols):
    return [features.index(c) for c in cols if c in features]


def vector(X3, idx):
    """Media y desviacion por variable a lo largo de la ventana (2k features)."""
    sub = X3[:, :, idx]
    return np.nan_to_num(np.concatenate([sub.mean(axis=1), sub.std(axis=1)],
                                        axis=1))


def etiquetar(art, tl):
    """Ventanas normales (train) y de fallo (test que cruzan un timeline)."""
    normales = [{"vec_i": i, "run": w["run"], "label": "normal"}
                for i, w in enumerate(art["ventanas_train"])]
    fallos = []
    for i, w in enumerate(art["ventanas_test"]):
        g = tl[tl["run_name"] == w["run"]]
        if g.empty:
            continue
        ini, fin = np.datetime64(w["inicio"]), np.datetime64(w["fin"])
        cruces = g[(ini <= g["fin"].values) & (fin >= g["inicio"].values)]
        if not cruces.empty:
            fallos.append({"vec_i": i, "run": w["run"],
                           "label": cruces.iloc[0]["tipo"]})
    return normales, fallos


def tipo_loro(Xtr3, Xte3, idx, normales, fallos, runs_anom):
    Xn = vector(Xtr3, idx)
    Xf = vector(Xte3, idx)
    aciertos = {"top1": 0, "top2": 0, "top3": 0}
    total = 0
    conf = {}
    for run in runs_anom:
        train = [(Xn[p["vec_i"]], "normal") for p in normales] + \
                [(Xf[p["vec_i"]], p["label"]) for p in fallos if p["run"] != run]
        test = [(Xf[p["vec_i"]], p["label"], p["run"]) for p in fallos
                if p["run"] == run]
        if not test or len({lab for _, lab in train}) < 2:
            continue
        clf = RandomForestClassifier(n_estimators=300, random_state=0,
                                     class_weight="balanced")
        clf.fit(np.array([v for v, _ in train]), [lab for _, lab in train])
        clases = clf.classes_
        for vec, lab, _ in test:
            proba = clf.predict_proba(vec.reshape(1, -1))[0]
            orden = np.argsort(-proba)
            total += 1
            aciertos["top1"] += int(clases[orden[0]] == lab)
            aciertos["top2"] += int(lab in set(clases[orden[:2]]))
            aciertos["top3"] += int(lab in set(clases[orden[:3]]))
            conf.setdefault(lab, {}).setdefault(clases[orden[0]], 0)
            conf[lab][clases[orden[0]]] += 1
    return ({k: round(v / total, 4) for k, v in aciertos.items()} if total
            else None), total, conf


def main():
    art = vc.cargar_artefactos()
    if art is None:
        return
    features = art["features"]
    cols_base = [c for c in vc.VARIABLES_MODELO if c in features]
    extras_ok = [c for c in EXTRAS if c in features]
    cols_enr = cols_base + [c for c in extras_ok if c not in cols_base]
    idx_base = indices_de(features, cols_base)
    idx_enr = indices_de(features, cols_enr)
    vc.log(f"base={len(cols_base)} | enriquecido={len(cols_enr)} "
           f"(+{len(cols_enr) - len(cols_base)})")

    etq = etiquetas.etiquetas_corridas()
    resumen = etiquetas.resumen(art)
    normales_runs = resumen["normales"]
    runs_tr = np.asarray(art["runs_train"], dtype=object)
    runs_te = np.asarray(art["runs_test"], dtype=object)
    anomalas = [r for r in dict.fromkeys(runs_te.tolist())
                if etq.get(r) == "anomalia"]

    tl = vc.cargar_timelines()
    normales, fallos = etiquetar(art, tl)
    runs_anom = sorted({p["run"] for p in fallos})
    vc.log(f"ventanas normales={len(normales)} fallo={len(fallos)} | "
           f"corridas anomalas={len(runs_anom)}")

    salida = {"base": cols_base, "extras": extras_ok, "enriquecido": cols_enr,
              "deteccion": {}, "tipo": {}}

    # ---- Deteccion honesta: base vs enriquecido (crudo y normalizado) ----
    Xtr3 = {"base": art["X_train"][:, :, idx_base],
            "enriquecido": art["X_train"][:, :, idx_enr]}
    Xte3 = {"base": art["X_test"][:, :, idx_base],
            "enriquecido": art["X_test"][:, :, idx_enr]}
    for variante in ("crudo", "normalizado"):
        for rep in ("base", "enriquecido"):
            A3, B3 = Xtr3[rep], Xte3[rep]
            if variante == "normalizado":
                A3 = hon.normalizar(A3, runs_tr)
                B3 = hon.normalizar(B3, runs_te)
            A = np.nan_to_num(A3.reshape(len(A3), -1))
            B = np.nan_to_num(B3.reshape(len(B3), -1))
            for nombre, comps in hon.COMBOS.items():
                if nombre not in COMBOS_DETECCION:
                    continue
                res = hon.evaluar(comps, A, runs_tr, normales_runs, B, runs_te,
                                  anomalas)
                salida["deteccion"].setdefault(variante, {}).setdefault(
                    rep, {})[nombre] = {
                    "f1_q01": res["q01"]["f1"],
                    "tpr_corrida": res["q01"]["tpr_corrida"],
                    "fpr_corrida": res["q01"]["fpr_corrida"],
                    "tpr_ventana": res["q01"]["tpr_ventana"],
                    "precision": res["q01"]["precision"],
                }
                vc.log(f"deteccion {variante}/{rep} {nombre}: F1={res['q01']['f1']} "
                       f"TPR_c={res['q01']['tpr_corrida']} "
                       f"FPR_c={res['q01']['fpr_corrida']}")

    # ---- Tipo supervisado LORO: base vs enriquecido ----
    for rep, idx in {"base": idx_base, "enriquecido": idx_enr}.items():
        acc, total, conf = tipo_loro(art["X_train"], art["X_test"], idx,
                                     normales, fallos, runs_anom)
        salida["tipo"][rep] = {"accuracy": acc, "ventanas": total,
                               "matriz_confusion": conf}
        vc.log(f"tipo LORO {rep}: {acc} sobre {total} ventanas")

    os.makedirs(DIR_VAL, exist_ok=True)
    ruta = os.path.join(DIR_VAL, "prototipo_enriquecido.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=2, default=str)

    print("\n=== PROTOTIPO ENRIQUECIDO (artefactos, sin reentrenar scaler) ===")
    print(f"  base={len(cols_base)} features | enriquecido={len(cols_enr)}")
    print("  Deteccion honesta (q01):")
    for variante in ("crudo", "normalizado"):
        for rep in ("base", "enriquecido"):
            for nombre, m in salida["deteccion"].get(variante, {}).get(rep, {}).items():
                print(f"    {variante:<12} {rep:<11} {nombre:<18} "
                      f"F1={m['f1_q01']} TPR_c={m['tpr_corrida']} "
                      f"FPR_c={m['fpr_corrida']}")
    print("  Tipo supervisado LORO:")
    for rep in ("base", "enriquecido"):
        m = salida["tipo"][rep]
        print(f"    {rep:<11} top1={m['accuracy']['top1']} "
              f"top2={m['accuracy']['top2']} top3={m['accuracy']['top3']} "
              f"({m['ventanas']} ventanas)")
    print(f"\nInforme: {ruta}")


if __name__ == "__main__":
    main()
