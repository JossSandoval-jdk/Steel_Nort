import os
import joblib
import pandas as pd
import json

# Configuración de rutas
INPUT_DIR = "backend/app/tools/output/modelado"
OUTPUT_DIR = "backend/app/tools/output/modelado/legibilidad"

def exportar():
    # Asegurar que el directorio de salida existe
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    for filename in os.listdir(INPUT_DIR):
        file_path = os.path.join(INPUT_DIR, filename)
        
        # Saltar si es una carpeta o si es el propio archivo de script
        if not os.path.isfile(file_path):
            continue
            
        name, ext = os.path.splitext(filename)
        
        try:
            # 1. Exportar modelos joblib/pkl a JSON
            if ext in ['.joblib', '.pkl']:
                modelo = joblib.load(file_path)
                data = {"archivo": filename, "tipo": str(type(modelo))}
                if hasattr(modelo, 'get_params'):
                    data["parametros"] = modelo.get_params()
                
                with open(os.path.join(OUTPUT_DIR, f"{name}.json"), 'w') as f:
                    json.dump(data, f, indent=4)
                print(f"✅ Exportado modelo: {filename} -> {name}.json")

            # 2. Exportar parquet a CSV
            elif ext == '.parquet':
                df = pd.read_parquet(file_path)
                df.to_csv(os.path.join(OUTPUT_DIR, f"{name}.csv"), index=False)
                print(f"✅ Exportado dataset: {filename} -> {name}.csv")

        except Exception as e:
            print(f"❌ Error procesando {filename}: {e}")

    print(f"\n🎯 Exportación completada en: {OUTPUT_DIR}")

if __name__ == "__main__":
    exportar()
