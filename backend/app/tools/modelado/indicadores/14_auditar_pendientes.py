"""
14_auditar_pendientes.py
========================
Audita los indicadores que `docs/guia_indicadores.md` deja "por calcular":
I-0 (reduccion del tiempo de deteccion), I-3.2 (severidad) e I-3.3
(efectividad del diagnostico).

No inventa datos: cada cifra sale de un artefacto del repo. Cuando una meta
NO es medible con los datos actuales, lo deja explicito en el JSON.

Entrada : output/modelado/indicadores/diagnostico_final.json
          output/modelado/indicadores/clasificador_tipo.json
Salida  : output/modelado/indicadores/auditoria_pendientes.json

Uso:
    python indicadores/14_auditar_pendientes.py
    python indicadores/14_auditar_pendientes.py --ttd-pre 600
"""

import argparse
import ast
import json
import os
import sys
from pathlib import Path

import numpy as np

# Config del modelado (parents[1] = tools/modelado/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelado_config import DIR_MODELADO, VARIABLES_MODELO, log  # noqa: E402

DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")


def leer(nombre):
    ruta = os.path.join(DIR_VAL, nombre)
    if not os.path.isfile(ruta):
        log(f"Falta {ruta}.")
        return None
    with open(ruta, encoding="utf-8") as fh:
        return json.load(fh)


def leer_footprint():
    """Extrae el dict ``FOOTPRINT`` de 03_evaluar_oe3.py sin ejecutarlo."""
    ruta = os.path.join(os.path.dirname(__file__), "03_evaluar_oe3.py")
    if not os.path.isfile(ruta):
        return {}
    arbol = ast.parse(open(ruta, encoding="utf-8").read())
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(
                getattr(t, "id", None) == "FOOTPRINT" for t in nodo.targets):
            try:
                return ast.literal_eval(nodo.value)
            except (ValueError, SyntaxError):
                return {}
    return {}


def evaluar_i33(diag):
    """I-3.3 efectividad del diagnostico = fallos con huella coincidente / detectados."""
    r = diag["resumen"]
    detectados = r["detectados_modelo"]
    return {
        "indicador": "I-3.3",
        "meta": 0.85,
        "valor": r["efectividad_diagnostico"],
        "correctos": r["con_coincidencia_huella"],
        "total": detectados,
        "cumple": bool(r["efectividad_diagnostico"] >= 0.85),
        "nota": "Coincidencia entre variables_top y la huella esperada (FOOTPRINT de "
                "03_evaluar_oe3.py). Ya medido por el propio script; el techo lo fija "
                "la senal del detector (ver I-3.1).",
    }


def evaluar_i33_alineado(diag, footprint):
    """Comprueba si alinear la huella al modelo cambiaria I-3.3.

    No se puede recalcular desde ``diagnostico_final.json`` porque solo guarda
    ``variables_top`` (un top-3), no las variables desviadas completas. Pero si
    NINGUNA de las coincidencias registradas (``coincide_huella``) es una
    variable ajena al modelo, entonces las variables de la huella que el modelo
    no maneja nunca coincidieron: quitarlas no puede cambiar el resultado.
    """
    if not footprint:
        return None

    modelo = set(VARIABLES_MODELO)
    fuera_del_modelo = sorted({v for d in footprint.values() for v in d.get("vars", [])
                               if v not in modelo})
    coincidencias = [v for p in diag["por_fault"] for v in p.get("coincide_huella", [])]
    coincidencias_fuera = sorted({v for v in coincidencias if v not in modelo})
    cambia = bool(coincidencias_fuera)

    return {
        "variante": "huella_alineada_al_modelo",
        "cambia_el_resultado": cambia,
        "variables_fuera_del_modelo": fuera_del_modelo,
        "coincidencias_totales": len(coincidencias),
        "coincidencias_fuera_del_modelo": coincidencias_fuera,
        "valor_tras_alinear": None if cambia else diag["resumen"]["efectividad_diagnostico"],
        "nota": ("Las variables de la huella que el modelo NO maneja "
                 f"({', '.join(fuera_del_modelo) or 'ninguna'}) nunca coincidieron "
                 "(todas las coincidencias registradas son variables del modelo), "
                 "asi que alinear la huella es un no-op: I-3.3 sigue en "
                 f"{diag['resumen']['efectividad_diagnostico']:.2%}. No es un problema "
                 "de definicion de huella sino de senal del detector."),
    }


def evaluar_i32(diag, sev_esperada):
    """I-3.2 severidad. NO hay ground truth: solo se puede simular un criterio.

    Se calcula la coincidencia SOLO si el llamador aporta un mapa
    (fault -> severidad esperada). Con el mapa que propone la guia, el
    resultado queda por debajo de la meta. Se marca `ground_truth: false`.
    """
    detectados = [p for p in diag["por_fault"]
                  if p["detectado_modelo"] and p["severidad"]]
    salida = {
        "indicador": "I-3.2",
        "meta": 0.90,
        "ground_truth": False,
        "valor": None,
        "cumple": None,
        "distribucion_emitida": diag["resumen"]["distribucion_severidad"],
        "nota": "Los escenarios del repo (anomalias_timeline.csv y origen.json) NO "
                "definen severidad esperada: no existe ground truth. 03_evaluar_oe3.py "
                "lo declara ('sin ground truth: solo distribucion'). No es medible "
                "honestamente sin etiquetar la severidad por escenario.",
    }
    if sev_esperada:
        correctas = sum(1 for p in detectados
                        if p["severidad"] == sev_esperada.get(p["fault"], None))
        salida.update({
            "valor": round(correctas / len(detectados), 4) if detectados else None,
            "correctas": correctas,
            "total": len(detectados),
            "cumple": bool(detectados and correctas / len(detectados) >= 0.90),
            "supuesto": sev_esperada,
            "nota": ("HIPOTETICO: usa un mapa de severidad esperada NO respaldado por "
                     "el repo. Se reporta solo como cota superior del criterio; NO "
                     "acredita el indicador."),
        })
    return salida


def evaluar_i0(diag, ttd_pre_seg):
    """I-0 reduccion del tiempo de deteccion (TTFA del modelo vs. revision manual)."""
    detectados = [p for p in diag["por_fault"]
                  if p["detectado_modelo"] and p["ttfa_seg"] is not None]
    ttd_post = np.array([p["ttfa_seg"] for p in detectados], dtype=float)
    salida = {
        "indicador": "I-0",
        "meta_p": 0.05,
        "n": int(len(ttd_post)),
        "ttd_post_mediana_s": round(float(np.median(ttd_post)), 1),
        "ttd_post_media_s": round(float(np.mean(ttd_post)), 1),
        "cumple": None,
        "profesional": False,
    }
    if ttd_pre_seg is None:
        salida["nota"] = ("Falta el TTD previo (O1, revision manual). Es el dato que el "
                          "gerente debe aportar. Con --ttd-pre se calcula el contraste.")
        return salida

    ttd_pre = np.full_like(ttd_post, float(ttd_pre_seg))
    try:
        from scipy.stats import shapiro, ttest_rel, wilcoxon
        dif = ttd_post - ttd_pre
        p_norm = float(shapiro(dif).pvalue)
        if p_norm > 0.05:
            stat, p = ttest_rel(ttd_pre, ttd_post)
            prueba = "t de Student relacionada"
        else:
            stat, p = wilcoxon(ttd_pre, ttd_post)
            prueba = "Wilcoxon"
    except Exception as e:  # scipy ausente o muestra degenerada
        salida["nota"] = f"No se pudo contrastar ({e})."
        return salida

    reduccion = (1 - ttd_post.mean() / ttd_pre.mean()) * 100
    salida.update({
        "prueba": prueba,
        "p_valor": round(float(p), 6),
        "estadistico": round(float(stat), 4),
        "reduccion_pct": round(reduccion, 1),
        "ttd_pre_supuesto_s": float(ttd_pre_seg),
        "cumple": bool(p < 0.05),
        "profesional": False,
        "nota": ("OJO: el TTD previo (O1) es un SUPUESTO (--ttd-pre). El contraste es "
                 "significativo frente a ese supuesto, pero el valor no esta "
                 "respaldado por un artefacto. I-0 sigue siendo [Propuesto]/pendiente "
                 "hasta cerrar el O1 y el replay A/B."),
    })
    return salida


def main():
    ap = argparse.ArgumentParser(description="Auditoria de indicadores pendientes")
    ap.add_argument("--ttd-pre", type=float, default=None,
                    help="TTD previo (O1) en segundos; sin el, I-0 no se contrasta")
    ap.add_argument("--sev", action="store_true",
                    help="incluye el calculo hipotetico de I-3.2 (mapa no respaldado)")
    args = ap.parse_args()

    diag = leer("diagnostico_final.json")
    if diag is None:
        return

    sev_map = ({"lockwait": "A", "fault1": "A", "fault2": "A",
                "fault3": "M", "fault5": "A"} if args.sev else None)

    footprint = leer_footprint()
    i33a = evaluar_i33_alineado(diag, footprint)

    resultado = {
        "fuente": "diagnostico_final.json",
        "modelo": diag["resumen"]["modelo"],
        "umbral": diag["resumen"]["umbral"],
        "faults": diag["resumen"]["faults"],
        "detectados": diag["resumen"]["detectados_modelo"],
        "I-0": evaluar_i0(diag, args.ttd_pre),
        "I-3.2": evaluar_i32(diag, sev_map),
        "I-3.3": evaluar_i33(diag),
    }
    if i33a:
        resultado["I-3.3_alineado"] = i33a

    ruta = os.path.join(DIR_VAL, "auditoria_pendientes.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2)

    print("\n=== AUDITORIA DE INDICADORES PENDIENTES ===")
    print(f"  modelo={resultado['modelo']} q01 | "
          f"{resultado['detectados']}/{resultado['faults']} fallos detectados")
    i33 = resultado["I-3.3"]
    print(f"  I-3.3 efectividad diagnostico = {i33['valor']:.2%} "
          f"({i33['correctos']}/{i33['total']}) -> "
          f"{'CUMPLE' if i33['cumple'] else 'NO CUMPLE'} (meta >= 85 %)")
    if "I-3.3_alineado" in resultado:
        a = resultado["I-3.3_alineado"]
        estado = "cambia" if a["cambia_el_resultado"] else "no cambia (no-op)"
        print(f"  I-3.3 alineando la huella al modelo = {estado} "
              f"(fuera del modelo: {', '.join(a['variables_fuera_del_modelo']) or 'ninguna'})")
    i32 = resultado["I-3.2"]
    if i32["valor"] is not None:
        print(f"  I-3.2 severidad (HIPOTETICO, sin ground truth) = {i32['valor']:.2%}"
              f" -> {'cumple' if i32['cumple'] else 'NO CUMPLE'} (meta >= 90 %)")
    else:
        print("  I-3.2 severidad = NO MEDIBLE (sin ground truth en los escenarios)")
    print(f"  I-3.2 severidad emitida = {i32['distribucion_emitida']}")
    i0 = resultado["I-0"]
    if i0.get("p_valor") is not None:
        print(f"  I-0 reduccion = {i0['reduccion_pct']}% | "
              f"{i0['prueba']} p={i0['p_valor']} (TTD previo SUPUESTO)")
    else:
        print("  I-0 = pendiente (falta TTD previo O1 del gerente)")
    print(f"\nInforme: {ruta}")


if __name__ == "__main__":
    main()
