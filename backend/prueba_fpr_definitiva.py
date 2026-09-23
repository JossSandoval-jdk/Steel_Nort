import sys
import os
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
import warnings

# Silenciar warnings para ver resultados limpios, excepto cuando queramos evidenciar el error
warnings.filterwarnings("ignore")

BACKEND_ROOT = Path(r"d:\SteelNort_web\backend")
MODELING_DIR = BACKEND_ROOT / "training" / "nucleo" / "modeling"
sys.path.insert(0, str(MODELING_DIR))

import config
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.covariance import EllipticEnvelope
from sklearn.preprocessing import StandardScaler

def cargar_muestras():
    ruta = BACKEND_ROOT / "training" / "output" / "modelado" / "dataset_muestras_train.pkl"
    with open(ruta, "rb") as f:
        return pickle.load(f)

def seleccionar_features(d):
    modelo_cols = [c for c in config.VARIABLES_MODELO if c in d["features"]]
    return [d["features"].index(c) for c in modelo_cols]

def flat(x, idx):
    return x[:, :, idx].reshape(x.shape[0], -1)

def main():
    print("Iniciando Prueba de Falsos Positivos (Validación Cruzada 'Leave-One-Out')\n")
    print("Mecánica: Entrenamos cada modelo con N-1 corridas normales y probamos qué tantas")
    print("FALSAS ALARMAS (FPR) lanza sobre la 1 corrida normal restante que nunca vio.\n")
    
    d = cargar_muestras()
    idx = seleccionar_features(d)
    runs = np.array(d["runs"])
    X_raw = d["X"] * d["scaler"].scale_ + d["scaler"].mean_
    
    corridas = sorted(list(set(runs)))
    print(f"Corridas normales disponibles para la prueba: {corridas}\n")
    
    resultados = []

    for test_run in corridas:
        mask_test = (runs == test_run)
        mask_train = ~mask_test
        
        # Escalar
        sc = StandardScaler()
        X_train_fold = X_raw[mask_train]
        X_test_fold = X_raw[mask_test]
        
        # Evitar fallos si una corrida es vacía
        if len(X_test_fold) == 0 or len(X_train_fold) == 0:
            continue

        sc.fit(X_train_fold.reshape(-1, len(d["features"])))
        X_train_sc = sc.transform(X_train_fold.reshape(-1, len(d["features"]))).reshape(X_train_fold.shape)
        X_test_sc = sc.transform(X_test_fold.reshape(-1, len(d["features"]))).reshape(X_test_fold.shape)
        
        Xt = flat(X_train_sc, idx)
        Xv = flat(X_test_sc, idx)

        # 1. Isolation Forest
        iso = IsolationForest(random_state=42, n_estimators=100, contamination="auto")
        iso.fit(Xt)
        score_t = iso.decision_function(Xt)
        score_v = iso.decision_function(Xv)
        q05 = np.quantile(score_t, 0.05)
        fpr_iso = np.mean(score_v < q05)

        # 2. LOF
        lof = LocalOutlierFactor(n_neighbors=35, contamination="auto", novelty=True)
        lof.fit(Xt)
        score_t = lof.decision_function(Xt)
        score_v = lof.decision_function(Xv)
        q05 = np.quantile(score_t, 0.05)
        fpr_lof = np.mean(score_v < q05)

        # 3. OCSVM
        ocsvm = OneClassSVM(nu=0.05, gamma="scale")
        ocsvm.fit(Xt)
        score_t = ocsvm.decision_function(Xt)
        score_v = ocsvm.decision_function(Xv)
        q05 = np.quantile(score_t, 0.05)
        fpr_ocsvm = np.mean(score_v < q05)

        # 4. Elliptic Envelope
        fpr_ell = np.nan
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                ell = EllipticEnvelope(contamination=0.05, random_state=42)
                ell.fit(Xt)
                score_t = ell.decision_function(Xt)
                score_v = ell.decision_function(Xv)
                q05 = np.quantile(score_t, 0.05)
                fpr_ell = np.mean(score_v < q05)
        except Exception:
            pass

        resultados.append({
            "Test Run": test_run,
            "Ventanas": len(Xv),
            "FPR_IsoForest(%)": fpr_iso * 100,
            "FPR_LOF(%)": fpr_lof * 100,
            "FPR_OCSVM(%)": fpr_ocsvm * 100,
            "FPR_Elliptic(%)": fpr_ell * 100
        })

    df = pd.DataFrame(resultados)
    print(df.to_string(index=False, float_format="%.1f"))
    print("\nPROMEDIO FINAL DE FALSAS ALARMAS (FPR Medio en Producción Simulada):")
    promedios = df.mean(numeric_only=True)
    print(promedios.apply(lambda x: f"{x:.1f}%").to_string())
    print("\n*Nota: Al umbral q05 se espera idealmente un FPR cercano al 5.0%.")
    print("Valores ridículamente altos significan Sobreajuste (Overfitting).")

if __name__ == "__main__":
    main()

