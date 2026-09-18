"""
06_comparacion_modelos.py
=========================
Consolida las métricas de prueba (FPR y alertas) de todos los modelos 
entrenados y genera una tabla comparativa global.
"""

import os
import pandas as pd
import config

def log(msg):
    print(f"[COMPARACION] {msg}", flush=True)

def main():
    dir_det = config.DIR_DETECCION
    
    if not os.path.exists(dir_det):
        log(f"No existe el directorio de detección: {dir_det}")
        return

    # Buscar todos los archivos de alertas generados
    archivos = [f for f in os.listdir(dir_det) if f.startswith("alertas_test") and f.endswith(".csv")]
    
    if not archivos:
        log("No se encontraron archivos de alertas para comparar.")
        return

    resumen_global = []

    for archivo in archivos:
        # Extraer el nombre del modelo del nombre del archivo (ej. alertas_test_isolation_forest.csv -> isolation_forest)
        nombre_modelo = archivo.replace("alertas_test_", "").replace(".csv", "").upper()
        ruta_csv = os.path.join(dir_det, archivo)
        
        df = pd.read_csv(ruta_csv)
        total_muestras = len(df)
        
        fila = {"Modelo": nombre_modelo, "Total Muestras Test": total_muestras}
        
        # Calcular alertas y FPR para cada umbral estadístico
        for umbral in ["q10", "q05", "q01"]:
            if umbral in df.columns:
                n_alertas = int(df[umbral].sum())
                fpr = float(df[umbral].mean()) * 100
                fila[f"Alertas ({umbral})"] = n_alertas
                fila[f"FPR ({umbral}) %"] = round(fpr, 2)
                
        resumen_global.append(fila)

    df_comparativa = pd.DataFrame(resumen_global)
    
    # Guardar tabla comparativa en la carpeta de detección
    ruta_salida = os.path.join(dir_det, "tabla_comparativa_modelos.csv")
    df_comparativa.to_csv(ruta_salida, index=False, encoding="utf-8-sig")

    print("\n" + "="*65)
    print(" TABA COMPARATIVA DE RENDIMIENTO (FPR - Tasa de Falsas Alarmas)")
    print("="*65)
    print(df_comparativa.to_string(index=False))
    print("="*65)
    log(f"Tabla comparativa guardada en: {ruta_salida}")

if __name__ == "__main__":
    main()