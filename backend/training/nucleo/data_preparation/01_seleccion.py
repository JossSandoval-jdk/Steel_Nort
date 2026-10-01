from pathlib import Path
import pandas as pd
import config


def log(msg):
    print(f"[SELECCION] {msg}", flush=True)


def clasificar(columna, conjuntos):
    """Clasifica una columna según prioridad."""
    orden = [
        ("excluida",        conjuntos["excluidas"]),
        ("redundante",      conjuntos["redundantes"]),
        ("contador_a_tasa", conjuntos["a_tasa"]),
        ("contador",        conjuntos["contador"]),
        ("continua",        conjuntos["continua"]),
        ("feature_modelo",  conjuntos["features"]),
    ]
    for etiqueta, conjunto in orden:
        if columna in conjunto:
            return etiqueta
    return "disponible"


def main():
    conjuntos = {
        "features":    set(config.FEATURES_MODELO),
        "continua":    set(config.METRICAS_CONTINUAS),
        "contador":    set(config.METRICAS_CONTADOR),
        "a_tasa":      set(config.METRICAS_A_TASA),
        "excluidas":   set(config.EXCLUIR_MEDICION_CORRUPTA),
        "redundantes": set(config.VARIABLES_REDUNDANTES),
    }

    # Reportar solapamientos entre listas
    solapamientos = {
        "features ∩ redundantes": conjuntos["features"] & conjuntos["redundantes"],
        "features ∩ excluidas":   conjuntos["features"] & conjuntos["excluidas"],
        "continua ∩ contador":    conjuntos["continua"] & conjuntos["contador"],
    }
    for nombre, solape in solapamientos.items():
        if solape:
            log(f"⚠ {nombre}: {sorted(solape)}")

    # Universo: unión de todas las listas
    universo = set().union(*conjuntos.values())

    filas = [
        {
            "columna": col,
            "clasificacion": clasificar(col, conjuntos),
            "en_features_modelo": col in conjuntos["features"],
        }
        for col in sorted(universo)
    ]
    df = pd.DataFrame(filas)

    # Reportar features sin tipo de métrica asignado
    huerfanas = conjuntos["features"] - (
        conjuntos["continua"] | conjuntos["contador"] | conjuntos["a_tasa"]
    )
    if huerfanas:
        log(f"⚠ Features sin tipo de métrica: {sorted(huerfanas)}")

    dir_inv = Path(config.DIR_INVENTARIO)
    dir_inv.mkdir(parents=True, exist_ok=True)
    ruta = dir_inv / config.ARCHIVO_VARIABLES
    df.to_csv(ruta, index=False, encoding="utf-8-sig")

    log(f"Variables en catálogo: {len(df)}")
    log(f"Guardado en: {ruta}")

    print("\n=== POR CLASIFICACIÓN ===")
    print(df.groupby("clasificacion").size().to_string())
    print("\n=== EN FEATURES DEL MODELO ===")
    print(df["en_features_modelo"].value_counts().to_string())


if __name__ == "__main__":
    main()