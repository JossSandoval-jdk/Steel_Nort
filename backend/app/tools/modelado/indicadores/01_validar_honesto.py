"""
01_validar_honesto.py
=====================
Evaluación honesta del detector, sin mezclar corridas.

Por qué: la validación previa (`03_validar_candidato.py`) cuenta como "normales"
a ventanas de corridas que en realidad son anomalías declaradas (las live no
tienen `anomalias_timeline.csv`), y además compara corridas distintas entre sí.

Acá se usa la etiqueta NATIVA (`modelado/etiquetas.py`, que sale del propio
dataset: `etiqueta_manual`), y se separa el conjunto:

  normales : las 8 corridas sanas de entrenamiento.
  anomalias: corridas sintéticas (timeline) + corridas live (es_carga_normal
             = false). El test no tiene corridas sanas: TODAS sus ventanas son
             anomalía.

Protocolo:
  FPR : dejar-una-corrida-fuera entre las normales.
  TPR : modelos entrenados solo con normales, aplicados a cada anomalía.
Variantes: CRUDO y NORMALIZADO por corrida (resta la mediana del run).

También rankea varios ensambles (para rediseñar el ensamble de producción).
No modifica el flujo; es un script aparte.

Salidas:
  output/modelado/indicadores/etiquetas.json
  output/modelado/indicadores/honesto.json
"""

import importlib.util
import json
import os

import numpy as np

# El harness de candidatos sigue en experimental/; se reusa por ruta.
RUTA_VC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "experimental", "03_validar_candidato.py")

spec = importlib.util.spec_from_file_location("vc", RUTA_VC)
vc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vc)

import etiquetas  # noqa: E402  (módulo nuevo: fuente única de ground truth)

# Informes de validacion de indicadores (carpeta propia, separada del harness).
DIR_VAL = os.path.join(vc.DIR_MODELADO, "indicadores")

QQ = {"q01": 0.01, "q05": 0.05, "q10": 0.10}

# nombre -> componentes del ensamble (media de z-scores; menor = más anómalo)
COMBOS = {
    "ISOLATION_FOREST": ("ISOLATION_FOREST",),
    "COPOD": ("COPOD",),
    "LOF": ("LOF",),
    "OCSVM": ("OCSVM",),
    "ELLIPTIC": ("ELLIPTIC",),
    "ENSEMBLE_Z": ("ISOLATION_FOREST", "COPOD"),
    "ENSEMBLE_LOF_ELL": ("LOF", "ELLIPTIC"),
    "LOF_ELL_OCSVM": ("LOF", "ELLIPTIC", "OCSVM"),
    "ISO_LOF_ELL": ("ISOLATION_FOREST", "LOF", "ELLIPTIC"),
    "LOF_ELL_OCSVM_ISO": ("LOF", "ELLIPTIC", "OCSVM", "ISOLATION_FOREST"),
}


# ==========================================
# Scores
# ==========================================
def puntuar(comps, Xfit, Xlist):
    """Ajusta los componentes en Xfit y devuelve z de train y z de cada lote."""
    mods = {c: vc.crear_modelo(c, vc.SEED).fit(Xfit) for c in comps}
    sfit = {c: vc.scores(mods[c], c, Xfit) for c in comps}
    mu = {c: sfit[c].mean() for c in comps}
    sd = {c: sfit[c].std() + 1e-9 for c in comps}

    def z_de(X):
        z = np.zeros(len(X))
        for c in comps:
            z = z + (vc.scores(mods[c], c, X) - mu[c]) / sd[c]
        return z / len(comps)

    return z_de(Xfit), [z_de(X) for X in Xlist]


def metricas_q(z_pares, zpares_anom):
    """Para cada q: umbral sobre los z de fit y conteo tp/fp/fn/tn pooled.

    z_pares      : lista de (zfit, zalerta) por corrida normal (LOO).
    zpares_anom  : lista de (zfit_all, zalerta) por corrida anomalía.
    """
    res = {}
    n_anom = sum(len(z) for _, z in zpares_anom)
    for qn, q in QQ.items():
        fp = tn = 0
        fpr_run, detalle = [], []
        for zfit, z in z_pares:
            thr = np.quantile(zfit, q)
            alerta = float((z < thr).mean())
            fpr_run.append(alerta)
            detalle.append({"run_orden": None, "alerta": round(alerta, 4)})
            fp += int((z < thr).sum())
            tn += int((z >= thr).sum())
        tp = 0
        tpr_run = []
        for zfit, z in zpares_anom:
            thr = np.quantile(zfit, q)
            tpr_run.append(float((z < thr).mean()))
            tp += int((z < thr).sum())
        fn = n_anom - tp
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        tpr = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * tpr / (prec + tpr) if (prec + tpr) else 0.0
        res[qn] = {
            "fpr_ventana": round(float(np.mean(fpr_run)), 4),
            "fpr_corrida": round(float(np.mean([m > 0.5 for m in fpr_run])), 4),
            "tpr_ventana": round(float(np.mean(tpr_run)), 4),
            "tpr_corrida": round(float(np.mean([m > 0.5 for m in tpr_run])), 4),
            "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "precision": round(prec, 4), "f1": round(f1, 4),
            "detalle_normales": detalle,
        }
    return res


def evaluar(comps, Xtr, runs_tr, normales, Xte, runs_te, anomalas):
    # FPR: dejar-una-corrida-fuera entre las normales.
    z_pares = []
    for r in normales:
        zfit, (zb,) = puntuar(comps, Xtr[runs_tr != r], [Xtr[runs_tr == r]])
        z_pares.append((zfit, zb))

    # TPR: se entrena con TODAS las normales y se aplica a cada anomalía.
    zfit_all, _ = puntuar(comps, Xtr, [Xtr])
    zpares_anom = []
    for r in anomalas:
        _, (zb,) = puntuar(comps, Xtr, [Xte[runs_te == r]])
        zpares_anom.append((zfit_all, zb))

    return metricas_q(z_pares, zpares_anom)


def normalizar(X3, runs):
    """Resta a cada corrida su propia mediana (quita el nivel de la captura)."""
    Xn = X3.astype(float).copy()
    for r in dict.fromkeys(runs.tolist()):
        if isinstance(r, str):
            Xn[runs == r] -= np.median(X3[runs == r], axis=0)
    return Xn


# ==========================================
# Main
# ==========================================
def main():
    art = vc.cargar_artefactos()
    if art is None:
        return
    indice = vc.indices_modelo(art["features"])
    runs_tr = np.asarray(art["runs_train"], dtype=object)
    runs_te = np.asarray(art["runs_test"], dtype=object)

    # Ground truth nativo.
    etq = etiquetas.etiquetas_corridas()
    resumen = etiquetas.resumen(art)
    normales = resumen["normales"]
    anomalas = [r for r in dict.fromkeys(runs_te.tolist())
                if isinstance(r, str) and etq.get(r) == "anomalia"]
    vc.log("normales=%d anomalias=%d ventanas_test_anomalia=%d"
           % (len(normales), len(anomalas),
              resumen["ventanas_test_anomalia"]))

    os.makedirs(DIR_VAL, exist_ok=True)
    with open(os.path.join(DIR_VAL, "etiquetas.json"), "w",
              encoding="utf-8") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)
    vc.log("Guardado: %s" % os.path.join(DIR_VAL, "etiquetas.json"))

    Xtr3 = art["X_train"][:, :, indice]
    Xte3 = art["X_test"][:, :, indice]

    salida = {"protocolo": "dejar-una-corrida-fuera + normalizacion por corrida",
              "fuente_etiquetas": "nativa (dataset.etiqueta_manual)",
              "normales": normales, "anomalias": anomalas,
              "ventanas_test_anomalia": resumen["ventanas_test_anomalia"],
              "variantes": {}}

    for variante, (A, B) in {
            "crudo": (Xtr3, Xte3),
            "normalizado": (normalizar(Xtr3, runs_tr), normalizar(Xte3, runs_te))
    }.items():
        Xtr = A.reshape(len(A), -1)
        Xte = B.reshape(len(B), -1)
        salida["variantes"][variante] = {}
        for nombre, comps in COMBOS.items():
            vc.log("eval %s | %s" % (variante, nombre))
            salida["variantes"][variante][nombre] = evaluar(
                comps, Xtr, runs_tr, normales, Xte, runs_te, anomalas)

    print("\n===== Tabla honesta (normalizado, q01) =====")
    print("%-18s %6s %6s %8s %8s %7s %7s"
          % ("esquema", "FPR_c", "TPR_c", "FPR_ven", "TPR_ven", "prec", "F1"))
    for nombre in COMBOS:
        m = salida["variantes"]["normalizado"][nombre]["q01"]
        print("%-18s %6.2f %6.2f %8.3f %8.3f %7.3f %7.3f"
              % (nombre, m["fpr_corrida"], m["tpr_corrida"],
                 m["fpr_ventana"], m["tpr_ventana"],
                 m["precision"], m["f1"]))

    # Ranking por F1 (normalizado, q01): la vara honesta.
    rank = sorted(COMBOS,
                  key=lambda n: salida["variantes"]["normalizado"][n]["q01"]["f1"],
                  reverse=True)
    salida["ranking_f1_normalizado_q01"] = [
        {"esquema": n,
         "f1": salida["variantes"]["normalizado"][n]["q01"]["f1"],
         "tpr_corrida": salida["variantes"]["normalizado"][n]["q01"]["tpr_corrida"],
         "fpr_corrida": salida["variantes"]["normalizado"][n]["q01"]["fpr_corrida"]}
        for n in rank]
    print("\n===== Ranking honesto (normalizado, q01) =====")
    for i, n in enumerate(rank, 1):
        r = salida["variantes"]["normalizado"][n]["q01"]
        print("%2d. %-18s F1=%.3f  TPR_c=%.2f  FPR_c=%.2f"
              % (i, n, r["f1"], r["tpr_corrida"], r["fpr_corrida"]))

    destino = os.path.join(DIR_VAL, "honesto.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)
    vc.log("Guardado: %s" % destino)


if __name__ == "__main__":
    main()
