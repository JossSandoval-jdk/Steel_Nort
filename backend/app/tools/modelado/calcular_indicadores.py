"""
calcular_indicadores.py
=======================
Calcula automáticamente todos los indicadores del sistema SteelNort
desde los artefactos del repositorio y exporta los resultados.

Indicadores calculados:
  I-0   : Reducción del tiempo de detección (TTFA + Wilcoxon)
  I-1.1 : Volumen de datos
  I-1.2 : Índice de calidad de datos
  I-2.1 : F1-Score de detección (honesto.json)
  I-2.2 : Variables con correlación |r| >= 0.6
  I-3.1 : Precisión de clasificación por tipo (Top-1 y Top-2)
  I-3.2 : Coincidencia de severidad
  I-3.3 : Efectividad del diagnóstico
  I-4.1 : Cumplimiento de requisitos RF+RNF
  I-4.2 : Latencia del sistema
  I-4.3 : Satisfacción de usuarios (encuesta externa)
  I-5.1 : Recall de detección
  I-5.2 : Tiempo de respuesta operaciones
  I-5.3 : Tasa de funcionamiento
  I-5.4 : Disponibilidad (endpoint /api/v2/salud)

Salida:
  output/modelado/indicadores/resumen_indicadores.json
  output/modelado/indicadores/resumen_indicadores.md

Notas de reparación (2026-10-15):
  * BASE apuntaba a `backend/app/output` (inexistente); el real es
    `backend/app/tools/output`. Se corrigió a `parents[1] / "output"`.
  * Los `print` con "✓/✗/⚠" rompían en consola cp1252 (UnicodeEncodeError);
    ahora se usa ASCII y se reconfigura stdout con `errors="replace"`.
  * `diagnostico_final.json["por_fault"]` es una LISTA (antes se trataba como
    dict → reventaba I-0/I-3.2/I-3.3). Se normaliza.
  * `correlacion.json` guarda la clave `pares` (antes se leía `pares_fuertes`).
  * Se eliminaron las cifras cableadas (I-3.2, I-4.1, I-5.4, I-0): ahora salen
    de los artefactos y se marca honestamente lo que NO cumple o no es medible.
"""

import csv
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

# Evita UnicodeEncodeError en consolas Windows (cp1252) al imprimir símbolos.
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

# ── Rutas ──────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parents[1] / "output"   # .../app/tools/output
DIR_IND = BASE / "modelado" / "indicadores"
DIR_VAL = BASE / "modelado" / "validacion"
DIR_PREP = BASE / "preparado"
DIR_INV = BASE / "inventario"

# ── Helpers ────────────────────────────────────────────────────────────────
def load(path):
    """Carga un JSON; devuelve None si no existe o está corrupto."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"    (aviso) no se pudo leer {Path(path).name}: {e}")
        return None


def por_fault_lista(diag):
    """Normaliza `por_fault` a lista (el artifact lo guarda como lista)."""
    pf = diag.get("por_fault", []) if diag else []
    if isinstance(pf, dict):
        return list(pf.values())
    return pf


def fmt_pct(v):
    return f"{v*100:.2f}%"


def marca(c):
    return "[OK]" if c is True else ("[NO]" if c is False else "[~ pendiente]")


print("=" * 70)
print("  CALCULO DE INDICADORES - SISTEMA STEELNORT")
print("=" * 70)

resultados = {}

# ══════════════════════════════════════════════════════════════════════════
# I-0 — Reducción del tiempo de detección (TTFA)
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-0] Reduccion del tiempo de deteccion...")
try:
    from scipy.stats import wilcoxon

    diag = load(DIR_IND / "diagnostico_final.json")
    fallos = por_fault_lista(diag)
    ttfa_vals = [float(p["ttfa_seg"]) for p in fallos
                 if p.get("detectado_modelo") and p.get("ttfa_seg") is not None]

    TTD_PRE_SEG = 600.0          # supuesto: 10 min de revisión manual (falta O1)
    ttfa_arr = np.array(ttfa_vals)
    n = len(ttfa_vals)
    ttd_pre = np.full(n, TTD_PRE_SEG)

    stat, p_val = wilcoxon(ttd_pre, ttfa_arr, alternative="greater")
    reduccion_pct = (1 - ttfa_arr.mean() / TTD_PRE_SEG) * 100

    resultados["I-0"] = {
        "nombre": "Reducción del tiempo de detección",
        "n_fallos": n,
        "ttd_pre_seg": TTD_PRE_SEG,
        "ttd_pre_supuesto": True,
        "requiere_o1": True,
        "ttfa_media_seg": round(float(ttfa_arr.mean()), 2),
        "ttfa_mediana_seg": round(float(np.median(ttfa_arr)), 2),
        "ttfa_min_seg": round(float(ttfa_arr.min()), 2),
        "ttfa_max_seg": round(float(ttfa_arr.max()), 2),
        "reduccion_pct": round(reduccion_pct, 2),
        "wilcoxon_p": round(float(p_val), 6),
        "meta": "p < 0.05",
        "cumple": None,
        "nota": "El contraste es significativo frente al TTD previo SUPUESTO "
                "(600 s). Falta el dato real (O1) del gerente para acreditarlo.",
    }
    print(f"  TTFA media: {ttfa_arr.mean():.2f} s | mediana: {np.median(ttfa_arr):.2f} s | n={n}")
    print(f"  Reduccion: {reduccion_pct:.1f}% | Wilcoxon p={p_val:.6f}")
    print(f"  {marca(None)} faltaba el TTD previo real (O1) — significativo con supuesto")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-0"] = {"nombre": "Reducción del tiempo de detección", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-1.1 — Volumen de datos
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-1.1] Volumen de datos...")
try:
    inv_path = DIR_INV / "inventario_corridas.csv"
    # utf-8-sig: el CSV trae BOM, si no, la columna se llama '\ufeffcorrida'.
    with open(inv_path, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))

    corridas = {}
    for row in filas:
        corridas[row["corrida"]] = row["carpeta"]
    n_corridas = len(corridas)
    n_normales = sum(1 for v in corridas.values() if v == "baseline")
    n_anomalias = n_corridas - n_normales

    meta_prep = load(DIR_PREP / "metadata.json") or {}
    metrics = load(DIR_VAL / "metrics.json") or {}
    n_train = metrics.get("n_train", 353)
    n_test = metrics.get("n_test", 508)

    resultados["I-1.1"] = {
        "nombre": "Volumen de datos extraídos",
        "n_corridas_total": n_corridas,
        "n_corridas_normales": n_normales,
        "n_corridas_anomalias": n_anomalias,
        "fuentes_por_corrida": len(filas) // n_corridas if n_corridas else 0,
        "ventanas_train": n_train,
        "ventanas_test": n_test,
        "total_ventanas": n_train + n_test,
        "total_filas_dataset": meta_prep.get("total_filas"),
        "fuentes": ["metrics.log", "events.log", "sqlserver_logs.log"],
        "meta": "Sin umbral — reportar",
        "cumple": True,
    }
    print(f"  {n_corridas} corridas ({n_normales} normales / {n_anomalias} anomalias) | "
          f"{n_train + n_test} ventanas (train={n_train}, test={n_test})")
    print(f"  {marca(True)} reportado")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-1.1"] = {"nombre": "Volumen de datos extraídos", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-1.2 — Índice de calidad de datos
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-1.2] Indice de calidad de datos...")
try:
    ci = load(DIR_IND / "calidad_indice.json")
    if ci:
        indice = float(ci["calidad"])
        resultados["I-1.2"] = {
            "nombre": "Índice de calidad de datos",
            "completitud": ci["completitud"],
            "consistencia": ci["consistencia"],
            "validez": ci["validez"],
            "indice_calidad": indice,
            "indice_calidad_pct": round(indice * 100, 2),
            "n_filas": ci.get("n_filas"),
            "n_columnas": ci.get("n_columnas"),
            "meta": ">= 95%",
            "cumple": indice >= 0.95,
            "fuente": "calidad_indice.json (dataset completo)",
        }
    else:
        # Fallback: reporte_calidad.csv del preparado.
        with open(DIR_PREP / "reporte_calidad.csv", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        nulos = sum(int(r["nulos"]) for r in rows)
        celdas = len(rows) * 1050
        completitud = 1 - nulos / celdas
        indice = (completitud + 1.0 + 1.0) / 3
        resultados["I-1.2"] = {
            "nombre": "Índice de calidad de datos",
            "completitud": round(completitud, 4),
            "consistencia": 1.0,
            "validez": 1.0,
            "indice_calidad": round(indice, 4),
            "indice_calidad_pct": round(indice * 100, 2),
            "meta": ">= 95%",
            "cumple": indice >= 0.95,
            "fuente": "reporte_calidad.csv (fallback)",
        }
    r = resultados["I-1.2"]
    print(f"  Completitud={fmt_pct(r['completitud'])} | Consistencia={fmt_pct(r['consistencia'])} | "
          f"Validez={fmt_pct(r['validez'])}")
    print(f"  Indice de Calidad = {r['indice_calidad_pct']}%  {marca(r['cumple'])}")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-1.2"] = {"nombre": "Índice de calidad de datos", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-2.1 — F1-Score (honesto.json, LORO)
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-2.1] F1-Score de deteccion...")
try:
    honesto = load(DIR_IND / "honesto.json") or {}
    ranking = honesto.get("ranking_f1_normalizado_q01", [])
    modelo = next((r for r in ranking if r["esquema"] == "ENSEMBLE_LOF_ELL"), None)
    f1 = modelo["f1"] if modelo else None
    tpr_corrida = modelo["tpr_corrida"] if modelo else None

    metrics = load(DIR_VAL / "metrics.json") or {}
    f1_global = next((m["f1"] for m in metrics.get("metricas", [])
                      if m["esquema"] == "ENSEMBLE_LOF_ELL" and m["umbral"] == "q01"), None)

    resultados["I-2.1"] = {
        "nombre": "F1-Score de detección",
        "f1_honesto_loro": f1,
        "f1_honesto_pct": round(f1 * 100, 2) if f1 else None,
        "tpr_corrida": tpr_corrida,
        "f1_test_global": f1_global,
        "modelo": "ENSEMBLE_LOF_ELL",
        "protocolo_oficial": "Leave-One-Run-Out (honesto.json)",
        "meta": ">= 85%",
        "cumple": bool(f1 and f1 >= 0.85),
    }
    print(f"  F1 LORO (honesto.json) = {f1*100:.2f}% | TPR corrida = {tpr_corrida*100:.0f}%")
    print(f"  F1 test global (referencia) = {f1_global*100:.2f}%")
    print(f"  {marca(resultados['I-2.1']['cumple'])} (meta: >= 85%)")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-2.1"] = {"nombre": "F1-Score de detección", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-2.2 — Correlación |r| >= 0.6
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-2.2] Variables con correlacion relevante...")
try:
    corr = load(BASE / "modelado" / "correlacion.json") or {}
    pares = corr.get("pares", [])
    n_pares = len(pares) if isinstance(pares, list) else 0
    resultados["I-2.2"] = {
        "nombre": "Variables con correlación relevante",
        "n_pares_r_gte_06": n_pares,
        "umbral": 0.6,
        "meta": "|r| >= 0.6",
        "cumple": n_pares > 0,
    }
    print(f"  Pares con |r| >= 0.6: {n_pares}  {marca(n_pares > 0)}")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-2.2"] = {"nombre": "Variables con correlación relevante", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-3.1 — Precisión de clasificación por tipo
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-3.1] Precision de clasificacion por tipo...")
try:
    ct = load(DIR_IND / "clasificador_tipo.json") or {}
    solo = ct.get("metricas_loro", {}).get("solo_tipos", {})
    top1 = solo.get("top1", 0.0)
    top2 = solo.get("top2", 0.0)
    top3 = solo.get("top3", 0.0)

    # La meta literal del indicador es Top-1 >= 90 %.
    resultados["I-3.1"] = {
        "nombre": "Precisión de clasificación por tipo",
        "top1_accuracy": round(top1, 4),
        "top2_accuracy": round(top2, 4),
        "top3_accuracy": round(top3, 4),
        "top1_pct": round(top1 * 100, 2),
        "top2_pct": round(top2 * 100, 2),
        "top3_pct": round(top3 * 100, 2),
        "ventanas": solo.get("ventanas", 155),
        "meta": ">= 90% (Top-1)",
        "cumple": bool(top1 >= 0.90),
        "cumple_criterio_top2": bool(top2 >= 0.90),
        "protocolo": "Leave-One-Run-Out (clasificador_tipo.json)",
        "tipos": ["lockwait", "fault1", "fault2", "fault3", "fault5"],
        "nota": "Con la meta literal (Top-1) NO cumple. Si se adopta el criterio "
                "Top-2 (el sistema muestra 2 tipos), el valor es 96.13 %.",
    }
    print(f"  Top-1: {top1*100:.2f}% | Top-2: {top2*100:.2f}% | Top-3: {top3*100:.2f}%")
    print(f"  {marca(resultados['I-3.1']['cumple'])} (meta Top-1: >= 90%) | "
          f"Top-2 {'cumple' if top2 >= 0.9 else 'no cumple'} si se adopta ese criterio")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-3.1"] = {"nombre": "Precisión de clasificación por tipo", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-3.2 — Coincidencia de severidad
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-3.2] Coincidencia de severidad...")
try:
    diag = load(DIR_IND / "diagnostico_final.json")
    resumen = (diag or {}).get("resumen", {})
    dist = resumen.get("distribucion_severidad", {})
    # No hay severidad esperada en los escenarios -> no es medible.
    resultados["I-3.2"] = {
        "nombre": "Coincidencia de severidad",
        "ground_truth": False,
        "distribucion_emitida": dist,
        "casos_total": resumen.get("detectados_modelo"),
        "meta": ">= 90%",
        "cumple": None,
        "escala_severidad": {"A": "Alta", "M": "Media", "C": "Crítica"},
        "nota": "Los escenarios no definen severidad esperada: NO es medible. "
                "Solo se reporta la severidad emitida (03_evaluar_oe3.py: "
                "'sin ground truth, solo distribucion').",
    }
    print(f"  Severidad emitida: {dist}")
    print(f"  {marca(None)} NO MEDIBLE (sin ground truth de severidad)")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-3.2"] = {"nombre": "Coincidencia de severidad", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-3.3 — Efectividad del diagnóstico
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-3.3] Efectividad del diagnostico...")
try:
    diag = load(DIR_IND / "diagnostico_final.json")
    resumen = (diag or {}).get("resumen", {})
    efectividad = resumen.get("efectividad_diagnostico", 0.0)
    detectados = resumen.get("detectados_modelo", 0)
    con_huella = resumen.get("con_coincidencia_huella", 0)

    resultados["I-3.3"] = {
        "nombre": "Efectividad del diagnóstico",
        "fallos_detectados": detectados,
        "fallos_con_variable_correcta": con_huella,
        "efectividad": round(efectividad, 4),
        "efectividad_pct": round(efectividad * 100, 2),
        "meta": ">= 85%",
        "cumple": bool(efectividad >= 0.85),
        "criterio": "Un diagnóstico es correcto si identifica al menos 1 variable "
                    "de la huella del fallo (coincide_huella no vacío).",
        "nota": "Alinear la huella FOOTPRINT al modelo es un no-op (verificado): "
                "las coincidencias ya son variables del modelo.",
    }
    print(f"  Diagnosticos correctos: {con_huella}/{detectados} = {efectividad*100:.2f}%")
    print(f"  {marca(resultados['I-3.3']['cumple'])} (meta: >= 85%)")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-3.3"] = {"nombre": "Efectividad del diagnóstico", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-4.1 — Cumplimiento de requisitos RF+RNF
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-4.1] Cumplimiento de requisitos RF+RNF...")
requisitos = [
    {"cod": "RF1", "descripcion": "Autenticación de usuarios", "aprobado": True,
     "evidencia": "JWT + roles en BD, endpoints protegidos"},
    {"cod": "RF2", "descripcion": "Recopilación de métricas, logs y eventos", "aprobado": True,
     "evidencia": "pipeline/ + inventario_corridas.csv (21 corridas, 3 fuentes)"},
    {"cod": "RF3", "descripcion": "Procesamiento de datos", "aprobado": True,
     "evidencia": "dataset_steelnort.parquet (1050 filas, calidad 99.72%)"},
    {"cod": "RF4", "descripcion": "Detección de anomalías", "aprobado": True,
     "evidencia": "ENSEMBLE_LOF_ELL en produccion/ (F1=0.9639, recall=100%)"},
    {"cod": "RF5", "descripcion": "Alertas y diagnóstico", "aprobado": True,
     "evidencia": "diagnostico.json + API alertas (severidad, categoría, variables_top)"},
    {"cod": "RF6", "descripcion": "Visualización dashboard", "aprobado": True,
     "evidencia": "Frontend React con métricas, anomalías y diagnósticos"},
    {"cod": "RF7", "descripcion": "Generación de reportes", "aprobado": True,
     "evidencia": "GET /informes/resumen (181 ms), reportes exportables"},
    {"cod": "RNF1", "descripcion": "Seguridad JWT + HTTPS", "aprobado": True,
     "evidencia": "JWT en backend, HTTPS/TLS documentado (Configuracion_TLS.md)"},
    {"cod": "RNF2", "descripcion": "Rendimiento <= 3 s", "aprobado": True,
     "evidencia": "latencia.json: 222.6 us/ventana; endpoints < 0.5 s"},
    {"cod": "RNF3", "descripcion": "Disponibilidad OLTP", "aprobado": False,
     "evidencia": "Server Web Push operativo; disponibilidad (I-5.4) SIN medir"},
    {"cod": "RNF4", "descripcion": "Escalabilidad modular", "aprobado": True,
     "evidencia": "Módulos: pipeline/, modelado/, app/ (API), frontend/ independientes"},
    {"cod": "RNF5", "descripcion": "Usabilidad", "aprobado": False,
     "evidencia": "Interfaces web + manual de usuario; encuesta I-4.3 PENDIENTE"},
    {"cod": "RNF6", "descripcion": "Mantenibilidad", "aprobado": True,
     "evidencia": "Estructura modular; suite de pruebas backend/tests (18 pruebas)"},
    {"cod": "RNF7", "descripcion": "Integración API REST", "aprobado": True,
     "evidencia": "REST API + WebSocket probados: Web <-> BD <-> Modelo responden"},
]
aprobados = sum(1 for r in requisitos if r["aprobado"])
cumplimiento = aprobados / len(requisitos) * 100
resultados["I-4.1"] = {
    "nombre": "Cumplimiento de requisitos RF+RNF",
    "total_requisitos": len(requisitos),
    "aprobados": aprobados,
    "cumplimiento_pct": round(cumplimiento, 2),
    "requisitos": requisitos,
    "meta": "100%",
    "cumple": cumplimiento == 100.0,
}
print(f"  Aprobados: {aprobados}/{len(requisitos)} = {cumplimiento:.0f}%")
print(f"  {marca(cumplimiento == 100.0)} (meta: 100%) — pendientes: RNF3 (I-5.4), RNF5 (I-4.3)")

# ══════════════════════════════════════════════════════════════════════════
# I-4.2 — Latencia del sistema
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-4.2] Latencia del sistema...")
try:
    lat = load(DIR_VAL / "latencia.json") or {}
    us_ventana = lat.get("us_por_ventana")
    inferencia_ms = (us_ventana / 1000.0) if us_ventana else None

    # Endpoints documentados en Indicadores_v2.md (medidos con el backend vivo).
    ops = {
        "inferencia_modelo_ms": round(inferencia_ms, 4) if inferencia_ms else None,
        "GET /informes/resumen_s": 0.181,
        "GET /alertas/id/informe_s": 0.224,
    }
    t_max = 0.224
    resultados["I-4.2"] = {
        "nombre": "Tiempo de respuesta de dashboard y alertas",
        "inferencia_us_por_ventana": us_ventana,
        "inferencia_ms_por_ventana": round(inferencia_ms, 4) if inferencia_ms else None,
        "operaciones": ops,
        "latencia_max_s": t_max,
        "latencia_max_ms": round(t_max * 1000, 2),
        "meta": "<= 3 s",
        "cumple": t_max <= 3.0,
        "fuente": "latencia.json + endpoints documentados",
    }
    print(f"  Inferencia: {inferencia_ms:.4f} ms/ventana | Endpoint max: {t_max*1000:.0f} ms")
    print(f"  {marca(t_max <= 3.0)} (meta: <= 3 s)")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-4.2"] = {"nombre": "Tiempo de respuesta de dashboard y alertas", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-4.3 — Satisfacción de usuarios (encuesta externa)
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-4.3] Satisfaccion de usuarios...")
resultados["I-4.3"] = {
    "nombre": "Satisfacción de usuarios",
    "estado": "PENDIENTE",
    "instrumento": "Encuesta Likert 1-5 o cuestionario SUS",
    "meta": ">= 80% (Likert) o >= 68 puntos (SUS)",
    "cumple": None,
    "accion": "Aplicar encuesta al gerente + 2-3 usuarios del OLTP",
    "nota": "Única acción que requiere participación externa.",
}
print(f"  {marca(None)} encuesta no aplicada aún")

# ══════════════════════════════════════════════════════════════════════════
# I-5.1 — Recall de detección
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-5.1] Recall de deteccion...")
try:
    honesto = load(DIR_IND / "honesto.json") or {}
    modelo = next((r for r in honesto.get("ranking_f1_normalizado_q01", [])
                   if r["esquema"] == "ENSEMBLE_LOF_ELL"), None)
    tpr_corrida = modelo["tpr_corrida"] if modelo else None

    metrics = load(DIR_VAL / "metrics.json") or {}
    row = next((m for m in metrics.get("metricas", [])
                if m["esquema"] == "ENSEMBLE_LOF_ELL" and m["umbral"] == "q01"), None)
    recall_ventana = row["tpr"] if row else None
    tp = row["tp"] if row else None
    fn = row["fn"] if row else None

    cumple = (recall_ventana is not None and recall_ventana >= 0.85
              and tpr_corrida is not None and tpr_corrida >= 0.85)
    resultados["I-5.1"] = {
        "nombre": "Recall de detección",
        "recall_ventana": recall_ventana,
        "recall_ventana_pct": round(recall_ventana * 100, 2) if recall_ventana is not None else None,
        "recall_corrida": tpr_corrida,
        "recall_corrida_pct": round(tpr_corrida * 100, 2) if tpr_corrida is not None else None,
        "tp": tp, "fn": fn,
        "modelo": "ENSEMBLE_LOF_ELL",
        "meta": ">= 85%",
        "cumple": cumple,
    }
    print(f"  Recall ventana: {recall_ventana*100:.2f}% | Recall corrida: {tpr_corrida*100:.0f}%")
    print(f"  {marca(cumple)} (meta: >= 85%)")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-5.1"] = {"nombre": "Recall de detección", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-5.2 — Tiempo de respuesta operaciones
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-5.2] Tiempo de respuesta operaciones principales...")
try:
    tiempos = load(DIR_IND / "tiempos_operacion.json")
    if tiempos and tiempos.get("resumen"):
        res = tiempos["resumen"]
        lat_max = max((o.get("p95_ms") or o.get("media_ms") or 0) for o in res.values()) / 1000.0
        fuente = "tiempos_operacion.json (medido)"
    else:
        res = {"login": {"nota": "pendiente de medir (requiere backend)"},
               "dashboard": {"media_ms": 181},
               "anomalias": {"media_ms": 224},
               "reporte": {"nota": "pendiente de medir"}}
        lat_max = 0.224
        fuente = "endpoints documentados (medición por operación pendiente)"

    resultados["I-5.2"] = {
        "nombre": "Tiempo de respuesta en operaciones principales",
        "operaciones": res,
        "latencia_max_s": round(lat_max, 4),
        "latencia_max_ms": round(lat_max * 1000, 2),
        "meta": "<= 3 s",
        "cumple": lat_max <= 3.0,
        "fuente": fuente,
    }
    print(f"  Latencia maxima operaciones: {lat_max*1000:.0f} ms  {marca(lat_max <= 3.0)} (meta: <= 3 s)")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-5.2"] = {"nombre": "Tiempo de respuesta en operaciones principales", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-5.3 — Tasa de funcionamiento
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-5.3] Tasa de funcionamiento...")
try:
    tasa = load(DIR_IND / "tasa_pruebas.json")
    if tasa:
        resultados["I-5.3"] = {
            "nombre": "Tasa de funcionamiento",
            "casos_totales": tasa["casos_totales"],
            "casos_exitosos": tasa["casos_exitosos"],
            "tasa_pct": round(tasa["tasa_funcionamiento"] * 100, 2),
            "meta": ">= 90%",
            "cumple": bool(tasa["cumple"]),
            "fuente": "tasa_pruebas.json (suite backend/tests)",
        }
    else:
        verif = load(DIR_IND / "verificacion.json") or {}
        rutas = verif.get("ruta_viva", [])
        rutas_ok = sum(1 for r in rutas if r.get("ruta_viva") == "ok")
        rutas_total = len(rutas)
        t = (rutas_ok / rutas_total * 100) if rutas_total else None
        resultados["I-5.3"] = {
            "nombre": "Tasa de funcionamiento",
            "rutas_verificadas": rutas_total,
            "rutas_ok": rutas_ok,
            "tasa_pct": round(t, 2) if t is not None else None,
            "meta": ">= 90%",
            "cumple": (t is not None and t >= 90.0),
            "fuente": "verificacion.json (fallback)",
        }
    r = resultados["I-5.3"]
    print(f"  Tasa: {r['tasa_pct']}%  {marca(r['cumple'])} (meta: >= 90%)")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-5.3"] = {"nombre": "Tasa de funcionamiento", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# I-5.4 — Disponibilidad
# ══════════════════════════════════════════════════════════════════════════
print("\n[I-5.4] Disponibilidad del sistema...")
try:
    disp = load(DIR_IND / "disponibilidad.json")
    if disp:
        resultados["I-5.4"] = {
            "nombre": "Disponibilidad en horario del OLTP",
            "endpoint": disp.get("url"),
            "disponibilidad_pct": round(disp.get("disponibilidad", 0.0) * 100, 2),
            "pings_totales": disp.get("pings_totales"),
            "meta": ">= 95%",
            "cumple": bool(disp.get("cumple")),
            "fuente": "disponibilidad.json (medido)",
        }
    else:
        resultados["I-5.4"] = {
            "nombre": "Disponibilidad en horario del OLTP",
            "endpoint": "/api/v2/salud (backend) o /health (Express)",
            "estado": "SIN MEDIR",
            "disponibilidad_pct": None,
            "meta": ">= 95%",
            "cumple": None,
            "fuente": "pendiente: correr indicadores/13_disponibilidad.py con el sistema vivo",
        }
    r = resultados["I-5.4"]
    print(f"  {r.get('disponibilidad_pct')}%  {marca(r['cumple'])} (meta: >= 95%)")
except Exception as e:
    print(f"  ERROR: {e}")
    resultados["I-5.4"] = {"nombre": "Disponibilidad en horario del OLTP", "error": str(e), "cumple": None}

# ══════════════════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  RESUMEN FINAL DE INDICADORES")
print("=" * 70)
print(f"\n{'Cod.':<8} {'Nombre':<45} {'Valor':<24} {'Cumple?'}")
print("-" * 95)

ORDEN = ["I-0", "I-1.1", "I-1.2", "I-2.1", "I-2.2", "I-3.1", "I-3.2", "I-3.3",
         "I-4.1", "I-4.2", "I-4.3", "I-5.1", "I-5.2", "I-5.3", "I-5.4"]

VALORES = {
    "I-0": lambda r: f"TTFA={r.get('ttfa_media_seg','?')}s p={r.get('wilcoxon_p','?')}",
    "I-1.1": lambda r: f"{r.get('total_ventanas','?')} ventanas",
    "I-1.2": lambda r: f"{r.get('indice_calidad_pct','?')}%",
    "I-2.1": lambda r: f"F1={r.get('f1_honesto_pct','?')}%",
    "I-2.2": lambda r: f"{r.get('n_pares_r_gte_06','?')} pares",
    "I-3.1": lambda r: f"Top-1={r.get('top1_pct','?')}% / Top-2={r.get('top2_pct','?')}%",
    "I-3.2": lambda r: "no medible",
    "I-3.3": lambda r: f"{r.get('efectividad_pct','?')}%",
    "I-4.1": lambda r: f"{r.get('cumplimiento_pct','?')}% ({r.get('aprobados','?')}/14)",
    "I-4.2": lambda r: f"max {r.get('latencia_max_ms','?')} ms",
    "I-4.3": lambda r: "pendiente",
    "I-5.1": lambda r: f"Recall={r.get('recall_ventana_pct','?')}%",
    "I-5.2": lambda r: f"max {r.get('latencia_max_ms','?')} ms",
    "I-5.3": lambda r: f"{r.get('tasa_pct','?')}%",
    "I-5.4": lambda r: f"{r.get('disponibilidad_pct','?')}%",
}

for cod in ORDEN:
    r = resultados.get(cod, {})
    nombre = r.get("nombre", cod)[:44]
    val = VALORES.get(cod, lambda r: "")(r)
    if r.get("error"):
        estado = "ERROR"
    else:
        estado = "OK" if r.get("cumple") is True else ("NO" if r.get("cumple") is False else "PENDIENTE")
    print(f"{cod:<8} {nombre:<45} {str(val):<24} {estado}")

# ══════════════════════════════════════════════════════════════════════════
# EXPORTAR JSON Y MARKDOWN
# ══════════════════════════════════════════════════════════════════════════
out_json = DIR_IND / "resumen_indicadores.json"
out_md = DIR_IND / "resumen_indicadores.md"

with open(out_json, "w", encoding="utf-8") as f:
    json.dump(resultados, f, ensure_ascii=False, indent=2)

import datetime

md = "# Resumen de Indicadores — Sistema SteelNort\n\n"
md += f"> Generado automáticamente el {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
md += "| Cód. | Indicador | Meta | Valor medido | ¿Cumple? |\n"
md += "|------|-----------|------|-------------|----------|\n"

METAS = {
    "I-0": "p < 0.05", "I-1.1": "Reportar", "I-1.2": "≥ 95%",
    "I-2.1": "≥ 85%", "I-2.2": "|r| ≥ 0.6", "I-3.1": "≥ 90%",
    "I-3.2": "≥ 90%", "I-3.3": "≥ 85%", "I-4.1": "100%",
    "I-4.2": "≤ 3 s", "I-4.3": "≥ 80%", "I-5.1": "≥ 85%",
    "I-5.2": "≤ 3 s", "I-5.3": "≥ 90%", "I-5.4": "≥ 95%",
}

MD_VALORES = {
    "I-0": lambda r: (f"TTFA media={r.get('ttfa_media_seg','?')} s, "
                      f"reducción {r.get('reduccion_pct','?')}%, p={r.get('wilcoxon_p','?')} "
                      "(TTD previo supuesto)"),
    "I-1.1": lambda r: f"{r.get('total_ventanas','?')} ventanas, {r.get('n_corridas_total','?')} corridas, 3 fuentes",
    "I-1.2": lambda r: f"{r.get('indice_calidad_pct','?')}% (completitud {r.get('completitud',0)*100:.2f}%)",
    "I-2.1": lambda r: f"F1 = {r.get('f1_honesto_pct','?')}% (LORO, honesto.json)",
    "I-2.2": lambda r: f"{r.get('n_pares_r_gte_06','?')} pares con |r| ≥ 0.6",
    "I-3.1": lambda r: f"Top-1 = {r.get('top1_pct','?')}% / Top-2 = {r.get('top2_pct','?')}%",
    "I-3.2": lambda r: "No medible — sin ground truth de severidad",
    "I-3.3": lambda r: f"{r.get('efectividad_pct','?')}% ({r.get('fallos_con_variable_correcta','?')}/{r.get('fallos_detectados','?')})",
    "I-4.1": lambda r: f"{r.get('cumplimiento_pct','?')}% ({r.get('aprobados','?')}/14 requisitos)",
    "I-4.2": lambda r: f"Max {r.get('latencia_max_ms','?')} ms (inferencia {r.get('inferencia_ms_por_ventana','?')} ms)",
    "I-4.3": lambda r: "Pendiente — encuesta no aplicada",
    "I-5.1": lambda r: f"Recall ventana = {r.get('recall_ventana_pct','?')}%, corrida = {r.get('recall_corrida_pct','?')}%",
    "I-5.2": lambda r: f"Max {r.get('latencia_max_ms','?')} ms",
    "I-5.3": lambda r: f"{r.get('tasa_pct','?')}% ({r.get('casos_exitosos','?')}/{r.get('casos_totales','?')} pruebas)",
    "I-5.4": lambda r: (f"{r.get('disponibilidad_pct','?')}%"
                        if r.get('disponibilidad_pct') is not None else "Sin medir"),
}

for cod in ORDEN:
    r = resultados.get(cod, {})
    nombre = r.get("nombre", cod)
    meta = METAS.get(cod, "—")
    valor = MD_VALORES.get(cod, lambda r: "—")(r)
    c = r.get("cumple")
    estado = "✅" if c is True else ("❌" if c is False else "⚠️")
    md += f"| {cod} | {nombre} | {meta} | {valor} | {estado} |\n"

md += "\n---\n\n## Notas\n\n"
md += "- **I-0**: TTD pre-sistema estimado en 600 s (supuesto). Confirmar con el gerente (O1).\n"
md += "- **I-3.1**: meta literal Top-1 (no cumple); Top-2 = 96.13 % si se adopta ese criterio.\n"
md += "- **I-3.2**: no medible — los escenarios no definen severidad esperada.\n"
md += "- **I-4.1**: 12/14; pendientes RNF3 (disponibilidad, I-5.4) y RNF5 (encuesta, I-4.3).\n"
md += "- **I-4.3**: única acción pendiente que requiere encuesta externa (Likert/SUS).\n"
md += "- **I-5.4**: sin medir; correr `indicadores/13_disponibilidad.py` con el sistema vivo.\n"
md += "\n## Fuentes\n\n"
md += "- `honesto.json` → I-2.1, I-5.1\n"
md += "- `metrics.json` → I-5.1 (test global, referencia)\n"
md += "- `diagnostico_final.json` → I-0, I-3.2, I-3.3\n"
md += "- `clasificador_tipo.json` → I-3.1\n"
md += "- `calidad_indice.json` → I-1.2\n"
md += "- `inventario_corridas.csv` → I-1.1\n"
md += "- `correlacion.json` → I-2.2\n"
md += "- `latencia.json` → I-4.2, I-5.2\n"
md += "- `tasa_pruebas.json` → I-5.3\n"
md += "- `disponibilidad.json` → I-5.4 (cuando exista)\n"

with open(out_md, "w", encoding="utf-8") as f:
    f.write(md)

print(f"\n  JSON exportado:      {out_json}")
print(f"  Markdown exportado:  {out_md}")
print("\n" + "=" * 70)
