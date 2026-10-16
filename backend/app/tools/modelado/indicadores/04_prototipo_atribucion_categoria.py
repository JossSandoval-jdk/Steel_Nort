"""
04_prototipo_atribucion_categoria.py
====================================
PROTOTIPO — solo medicion, NO toca produccion.

Compara la atribucion ACTUAL (variable de mayor |z| -> regla R1-R7) contra
elegir el GRUPO con mayor desviacion agregada (CPU / Memoria / Disco y red /
Sesiones y transacciones / Bloqueos / API de negocio) para clasificar el tipo
de fallo. Mide si eso sube:

  I-3.1 precision de clasificacion por tipo
  I-3.3 efectividad del diagnostico (variables detectadas vs huella esperada)

Se prueban DOS alcances:
  - ventana : la primera ventana alertada (lo que emitiria el sistema ya).
  - intervalo: agrega |z| de TODAS las ventanas del fallo (firma del evento).

No modifica anomalia_v2.py: recalcula los z con el scaler del bundle de
produccion y agrupa las variables por categoria.

Entrada : igual que 03_evaluar_oe3.py
Salida  : output/modelado/indicadores/prototipo_categoria.json
"""

import importlib.util
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# Reusa la carga del detector y los timelines de 05 (sin duplicar la logica).
_AQUI = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("eval05", _AQUI / "03_evaluar_oe3.py")
_eval05 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_eval05)

import sys  # noqa: E402
sys.path.insert(0, str(_AQUI.parent))
from modelado_config import (                       # noqa: E402
    DATASET_PRINCIPALES, DIR_MODELADO, VARIABLES_MODELO, log,
)
sys.path.insert(0, str(_AQUI.parents[4]))
from app.v2.services.anomalia_v2 import CATEGORIAS, Z_MINIMO  # noqa: E402

DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")

# Categoria esperada por tipo de fallo, en terminos de CATEGORIAS.
CAT_ESPERADA = {
    "fault1":   {"estricta": "Disco y red",
                 "amplia": {"Disco y red", "Sesiones y transacciones"}},
    "fault5":   {"estricta": "Sesiones y transacciones",
                 "amplia": {"Sesiones y transacciones", "Disco y red"}},
    "fault2":   {"estricta": "Disco y red",
                 "amplia": {"Disco y red", "CPU"}},
    "fault3":   {"estricta": "API de negocio",
                 "amplia": {"API de negocio", "CPU", "Sesiones y transacciones"}},
    "lockwait": {"estricta": "Bloqueos", "amplia": {"Bloqueos"}},
}

# Etiqueta de REGLAS_PROBABLES -> categoria, para comparar en el mismo marco.
REGLA_A_CATEGORIA = {
    "I/O fisico": "Disco y red", "plan/indices": "Disco y red",
    "cliente lento": "Sesiones y transacciones", "Bloqueos": "Bloqueos",
    "CPU": "CPU", "Memoria": "Memoria", "Cambio general": None,
}

FOOTPRINT_MODELO = {
    tipo: [v for v in info["vars"] if v in set(VARIABLES_MODELO)]
    for tipo, info in _eval05.FOOTPRINT.items()
}

VARIANTES = ("max", "media", "suma", "cuenta", "exceso")


def z_por_variable(det, pred):
    """{variable: z} con el scaler del bundle (misma cuenta que el backend)."""
    scaler = getattr(det, "_scaler", None)
    posiciones = getattr(det, "_posiciones", {}) or {}
    zs = {}
    for nombre, valor in pred.get("features", {}).items():
        pos = posiciones.get(nombre, -1)
        if pos < 0 or scaler is None or pos >= len(scaler.mean_):
            continue
        if float(scaler.var_[pos]) == 0.0:
            continue
        escala = float(scaler.scale_[pos]) or 1.0
        zs[nombre] = (float(valor) - float(scaler.mean_[pos])) / escala
    return zs


def puntuar_categorias(zs):
    """Score por categoria para cada variante de agregacion."""
    puntajes = {v: {} for v in VARIANTES}
    for nombre_cat, variables in CATEGORIAS:
        valores = [abs(zs[v]) for v in variables if v in zs]
        if not valores:
            continue
        puntajes["max"][nombre_cat] = max(valores)
        puntajes["media"][nombre_cat] = float(np.mean(valores))
        puntajes["suma"][nombre_cat] = float(np.sum(valores))
        puntajes["cuenta"][nombre_cat] = sum(1 for x in valores if x >= Z_MINIMO)
        puntajes["exceso"][nombre_cat] = float(np.sum([max(0.0, x - Z_MINIMO)
                                                       for x in valores]))
    return puntajes


def dominante(puntajes, variante):
    if not puntajes[variante]:
        return None
    return max(puntajes[variante], key=puntajes[variante].get)


def top_vars_categoria(zs, categoria):
    variables = dict(CATEGORIAS)[categoria]
    ordenadas = sorted([(v, abs(zs[v])) for v in variables if v in zs],
                       key=lambda t: t[1], reverse=True)
    return [v for v, _ in ordenadas[:3]]


def categorias_por_variante(zs):
    puntajes = puntuar_categorias(zs)
    return {v: dominante(puntajes, v) for v in VARIANTES}


def main():
    tl = _eval05.cargar_timelines()
    if tl.empty:
        log("Sin timelines.")
        return
    ds = pd.read_parquet(DATASET_PRINCIPALES)
    det = _eval05.construir_detector()
    from app.v2.services.anomalia_v2 import _regla_probable
    log(f"Detector: {det.modo} (prototipo de atribucion por categoria)")

    por_fault = []
    for run in sorted(tl["run_name"].unique()):
        sub = ds[ds["run_name"] == run].sort_values("timestamp")
        if sub.empty:
            continue
        muestras = []
        for _, fila in sub.iterrows():
            muestra = {v: (0.0 if pd.isna(fila[v]) else float(fila[v]))
                       for v in VARIABLES_MODELO}
            muestra["fecha_str"] = str(fila["timestamp"])
            muestras.append(muestra)

        resultados = det.evaluar_lote(run, muestras)
        ventanas = []
        for out in resultados:
            i = out["indice"]
            ventanas.append({
                "ini": pd.Timestamp(sub.iloc[i - det.ventana + 1]["timestamp"]),
                "fin": pd.Timestamp(sub.iloc[i]["timestamp"]),
                "pred": out,
            })

        for _, f in tl[tl["run_name"] == run].iterrows():
            idx = [w for w in ventanas
                   if w["ini"] <= f["fin"] and w["fin"] >= f["inicio"]]
            alertadas = sorted([w for w in idx if w["pred"]["es_anomalia"]],
                               key=lambda w: w["fin"])
            if not alertadas:
                continue

            # Alcance "ventana": solo la primera alertada.
            pred = alertadas[0]["pred"]
            zs_ventana = z_por_variable(det, pred)
            cat_ventana = categorias_por_variante(zs_ventana)

            # Alcance "intervalo": |z| medio por variable sobre todo el fallo.
            zs_intervalo = defaultdict(list)
            for w in idx:
                for k, v in z_por_variable(det, w["pred"]).items():
                    zs_intervalo[k].append(abs(v))
            zint = {k: float(np.mean(v)) for k, v in zs_intervalo.items()}
            cat_intervalo = categorias_por_variante(zint)

            _, etiqueta_regla, _ = _regla_probable(pred)
            cat_actual = REGLA_A_CATEGORIA.get(etiqueta_regla)

            esperada = CAT_ESPERADA.get(f["tipo"])
            huella = set(FOOTPRINT_MODELO.get(f["tipo"], []))

            coincide = {}
            for alcance, zs, cats in (("v", zs_ventana, cat_ventana),
                                      ("i", zint, cat_intervalo)):
                for v in VARIANTES:
                    cat = cats.get(v)
                    top = top_vars_categoria(zs, cat) if cat else []
                    coincide[f"{alcance}_{v}"] = sorted(set(top) & huella)

            por_fault.append({
                "run": run, "fault": f["tipo"],
                "categoria_actual": cat_actual,
                "categorias_ventana": cat_ventana,
                "categorias_intervalo": cat_intervalo,
                "esperada_estricta": esperada["estricta"] if esperada else None,
                "esperada_amplia": sorted(esperada["amplia"]) if esperada else None,
                "coincide": coincide,
            })

    # ---- Metricas ----
    filas = [p for p in por_fault if p["esperada_estricta"] is not None]
    metricas = {"actual": {
        "tipo_estricto": round(sum(1 for p in filas
                                   if p["categoria_actual"] == p["esperada_estricta"])
                               / len(filas), 4) if filas else None,
        "tipo_amplio": round(sum(1 for p in filas
                                 if p["categoria_actual"] in (p["esperada_amplia"] or []))
                             / len(filas), 4) if filas else None,
        "diagnostico": None,
    }}
    for alcance in ("ventana", "intervalo"):
        for v in VARIANTES:
            est_ok = sum(1 for p in filas
                         if p[f"categorias_{alcance}"].get(v) == p["esperada_estricta"])
            amp_ok = sum(1 for p in filas
                         if p[f"categorias_{alcance}"].get(v) in (p["esperada_amplia"] or []))
            pre = "v_" if alcance == "ventana" else "i_"
            diag_ok = sum(1 for p in por_fault
                          if p["fault"] in FOOTPRINT_MODELO
                          and p["coincide"].get(pre + v))
            metricas[f"{pre}{v}"] = {
                "tipo_estricto": round(est_ok / len(filas), 4) if filas else None,
                "tipo_amplio": round(amp_ok / len(filas), 4) if filas else None,
                "diagnostico": round(diag_ok / len(por_fault), 4) if por_fault else None,
            }

    resumen = {
        "modelo": det.modo,
        "faults_detectados": len(por_fault),
        "nota": ("Prototipo de medicion: no modifica anomalia_v2.py. "
                 "v_=primera ventana alertada, i_=agregado del intervalo. "
                 "'actual' = regla por variable de mayor |z|."),
        "metricas": metricas,
        "huella_modelo": FOOTPRINT_MODELO,
    }

    os.makedirs(DIR_VAL, exist_ok=True)
    ruta = os.path.join(DIR_VAL, "prototipo_categoria.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"resumen": resumen, "por_fault": por_fault},
                  fh, ensure_ascii=False, indent=2, default=str)

    print("\n=== PROTOTIPO: atribucion por categoria (I-3.1 / I-3.3) ===")
    print(f"  modelo={det.modo} | faults detectados={len(por_fault)} | "
          f"con tipo esperado={len(filas)}")
    print(f"  {'variante':<10} {'tipo estricto':>14} {'tipo amplio':>12} {'diagnostico':>12}")
    for clave, m in metricas.items():
        print(f"  {clave:<10} {str(m['tipo_estricto']):>14} "
              f"{str(m['tipo_amplio']):>12} {str(m['diagnostico']):>12}")
    print(f"\nInforme: {ruta}")


if __name__ == "__main__":
    main()
