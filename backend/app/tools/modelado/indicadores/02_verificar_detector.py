"""
02_verificar_detector.py
========================
Verifica el detector real (app.tools.motor.detector) en dos orígenes:
el desplegado (.env) y el bundle nuevo (output/modelado/produccion).

Puntúa las ventanas de train (normales) y test (fallos) con el mismo
código que corre el backend, y compara ISO, ENSEMBLE_Z y LOF+Elliptic.

Entrada : output/modelado/artefactos_modelo.pkl
          <backend>/app/ml/detector.py
Salida  : output/modelado/indicadores/verificacion.json
"""

import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np

# Rutas al config del modelado
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelado_config import (                       # noqa: E402
    DIR_MODELADO, VENTANA, VARIABLES_MODELO, log,
)

# Backend en sys.path para importar app.tools.motor.detector
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")
DIR_PRODUCCION = os.path.join(DIR_MODELADO, "produccion")
QQ = {"q10": 0.10, "q05": 0.05, "q01": 0.01}
# Nombre real de cada pedido (para distinguir alias de fallo al forzar).
MODO_ESPERADO = {"ISO": "ISOLATION_FOREST", "Z": "ENSEMBLE_Z",
                 "LOF_ELL": "ENSEMBLE_LOF_ELL"}


# ==========================================
# Carga
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


# ==========================================
# Detector de producción
# ==========================================
def cargar_detector(art_dir=None, train_pkl=None):
    """Importa el Detector del backend. Sin rutas usa las del .env."""
    try:
        from app.tools.motor.detector import Detector, ML_ARTIFACTS, TRAIN_PKL
    except ImportError as e:
        log(f"No se pudo importar app.tools.motor.detector: {e}")
        return None

    art_dir = Path(art_dir) if art_dir else Path(ML_ARTIFACTS)
    train_pkl = train_pkl or TRAIN_PKL
    ruta_modelo = art_dir / "modelo_isolation_forest.joblib"
    if not ruta_modelo.exists():
        log(f"Falta {ruta_modelo}.")
        return None

    return Detector(
        ruta_modelo=str(ruta_modelo),
        ruta_modelo_copod=str(art_dir / "modelo_copod.joblib"),
        ruta_modelo_lof=str(art_dir / "modelo_lof.joblib"),
        ruta_modelo_elliptic=str(art_dir / "modelo_elliptic.joblib"),
        ruta_scaler=str(art_dir / "scaler.joblib"),
        ruta_features=str(art_dir / "features_modelo.csv"),
        ruta_train_pkl=train_pkl,
        ventana=VENTANA,
        umbral_nombre="q01",
    )


def puntuar_lote(det, X):
    """Puntúa cada fila de X con el Detector (1 por 1)."""
    return np.array([det._score_ensamble(X[i:i + 1]) for i in range(len(X))])


def verificar_ruta_viva(origen, art_dir=None, train_pkl=None):
    """Prueba la ruta real ``evaluar()`` (con escalado), no el score pelado.

    Es la que corre en ``/telemetria/push``; si el escalador no calza con las
    features, revienta aquí (p. ej. IndexError en ``_escalar``).
    """
    os.environ["STEELNORT_ENSEMBLE"] = ""  # modo auto, como en produccion
    det = cargar_detector(art_dir, train_pkl)
    if det is None:
        return {"origen": origen, "ruta_viva": "sin detector"}

    muestra = {f: 0.0 for f in det.features}
    try:
        for _ in range(det.ventana):
            r = det.evaluar("verificacion", muestra)
    except Exception as e:  # noqa: BLE001
        log(f"RUTA VIVA FALLA [{origen}]: {e!r}")
        return {"origen": origen, "modo": det.modo, "ruta_viva": f"ERROR: {e}"}
    return {"origen": origen, "modo": det.modo, "ruta_viva": "ok",
            "score": r["score"] if r else None,
            "zona": (r or {}).get("zona")}


# ==========================================
# Main
# ==========================================
def main():
    art = cargar_artefactos()
    if art is None:
        return

    indice = indices_modelo(art["features"])
    X_train = aplanar(art["X_train"], indice)
    X_test = aplanar(art["X_test"], indice)

    if len(X_test) == 0:
        log("Sin ventanas de test.")
        return

    log(f"Train: {len(X_train)} | Test: {len(X_test)} | "
        f"Features: {len(indice)} | Ventana: {VENTANA}")

    os.makedirs(DIR_VAL, exist_ok=True)

    def probar(origen, art_dir=None, train_pkl=None):
        """Corre los 3 pedidos (ISO/Z/LOF_ELL) sobre un origen de artefactos."""
        filas = []
        for pref in ("ISO", "Z", "LOF_ELL"):
            os.environ["STEELNORT_ENSEMBLE"] = pref
            det = cargar_detector(art_dir, train_pkl)
            if det is None:
                filas.append({"origen": origen, "modo": pref,
                              "error": "detector no disponible"})
                continue
            modo = det.modo
            log(f"== {origen}: {modo} (pedido {pref})")
            if modo != MODO_ESPERADO[pref]:  # no se pudo forzar el modo pedido
                log(f"AVISO: se pidio {pref} y se uso {modo}")

            s_train = puntuar_lote(det, X_train)
            s_test = puntuar_lote(det, X_test)
            for q in QQ:
                thr = det.umbrales[q]
                filas.append({
                    "origen": origen, "modo": modo, "pedido": pref,
                    "umbral": q,
                    "tpr_test": round(float((s_test < thr).mean()), 4),
                    "fpr_train": round(float((s_train < thr).mean()), 4),
                    "thr": round(float(thr), 4),
                })
        return filas

    filas = probar("desplegado")
    pkl_prod = os.path.join(DIR_PRODUCCION, "dataset_muestras_train.pkl")
    hay_prod = os.path.exists(pkl_prod)
    if hay_prod:
        filas += probar("produccion", DIR_PRODUCCION, pkl_prod)
    else:
        log(f"Sin bundle nuevo en {DIR_PRODUCCION}")

    # Ruta viva (evaluar) por origen: caza fallos de escalado.
    vida = [verificar_ruta_viva("desplegado")]
    if hay_prod:
        vida.append(verificar_ruta_viva("produccion", DIR_PRODUCCION, pkl_prod))

    # Guardar
    ruta = os.path.join(DIR_VAL, "verificacion.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({
            "n_train": len(X_train), "n_test": len(X_test),
            "ventana": VENTANA, "modos": filas, "ruta_viva": vida,
        }, f, ensure_ascii=False, indent=2)
    log(f"Verificación: {ruta}")

    # Resumen
    print("\n=== VERIFICACIÓN DEL DETECTOR REAL ===")
    for f in filas:
        if "error" in f:
            print(f"  [{f['origen']:<10}] {f['modo']:<18} ERROR: {f['error']}")
            continue
        aviso = "" if f["modo"] == MODO_ESPERADO[f["pedido"]] else "  <-- no es el pedido"
        print(f"  [{f['origen']:<10}] {f['modo']:<18} {f['umbral']}: "
              f"TPR={f['tpr_test']:.4f} FPR_train={f['fpr_train']:.4f} "
              f"thr={f['thr']:.4f}{aviso}")
    print("\n=== RUTA VIVA (evaluar, con escalado) ===")
    for v in vida:
        extra = (f"score={v.get('score')} zona={v.get('zona')}"
                 if v.get("ruta_viva") == "ok" else "")
        print(f"  [{v['origen']:<10}] {v.get('modo', ''):<18} "
              f"{v['ruta_viva']} {extra}")


if __name__ == "__main__":
    main()