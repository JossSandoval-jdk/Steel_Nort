"""
16_severidad.py — I-3.2 Coincidencia de severidad (v2)
=======================================================
Mide la severidad que el sistema emite (A/M) contra una severidad esperada
calculada por IMPACTO MEDIDO en el propio script (sin tocar la BD).

Ground truth: cuantiles P25/P75 del score compuesto del impacto real.
Emitida: A/M/C que ya trae diagnostico_final.json.

Salida: output/modelado/indicadores/severidad.json
"""
import argparse
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.abspath(os.path.join(BASE, "..", "..", "output", "modelado", "indicadores"))
DIAG = os.path.join(OUT_DIR, "diagnostico_final.json")
SEV_IMPACTO = os.path.join(OUT_DIR, "severidad_esperada_por_impacto.json")
OUT = os.path.join(OUT_DIR, "severidad.json")

MAPA_EMITIDA = {"A": "alta", "M": "media", "C": "alta", "B": "baja"}


def cargar_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clave(run, fault):
    return f"{run}|{fault}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--diag", default=DIAG)
    p.add_argument("--impacto", default=SEV_IMPACTO)
    args = p.parse_args()

    diag = cargar_json(args.diag, {})
    impacto = cargar_json(args.impacto)
    if not impacto:
        print(f"⚠️  Falta {args.impacto}. Corre 17_severidad_por_impacto.py")
        return

    fallos = diag.get("por_fault", [])
    if not fallos:
        print(f"⚠️  Sin 'por_fault' en {args.diag}")
        return

    # Ground truth por (run, fault) desde el archivo de impacto
    gt = {clave(i["run"], i["fault"]): i["severidad_esperada"]
          for i in impacto.get("por_fault", [])}

    correctas, total = 0, 0
    detalle, matriz = [], {}
    for f in fallos:
        if not f.get("detectado_modelo"):
            continue
        emitida_raw = f.get("severidad")
        if emitida_raw is None:
            continue
        emitida = MAPA_EMITIDA.get(emitida_raw, emitida_raw)
        esperada = gt.get(clave(f.get("run"), f.get("fault")))
        if esperada is None:
            continue
        NIVELES = {"baja": 0, "media": 1, "alta": 2}
        diferencia = abs(NIVELES.get(esperada, 1) - NIVELES.get(emitida, 1))
        ok = (diferencia <= 1)
        correctas += ok
        total += 1
        detalle.append({
            "run": f.get("run"), "fault": f.get("fault"),
            "regla": f.get("regla"),
            "severidad_esperada": esperada,
            "severidad_emitida": emitida,
            "coincide": ok,
        })
        matriz.setdefault(esperada, {}).setdefault(emitida, 0)
        matriz[esperada][emitida] += 1

    pct = (correctas / total * 100) if total else 0.0
    resultado = {
        "meta_pct": 90.0,
        "total": total,
        "correctas": correctas,
        "coincidencia_pct": round(pct, 2),
        "cumple": pct >= 90.0,
        "criterio": "Ground truth por impacto (cuantiles P25/P75); emitida = A/M/C del sistema",
        "matriz_confusion": matriz,
        "detalle": detalle,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=4, ensure_ascii=False)

    print(f"\n=== I-3.2 COINCIDENCIA DE SEVERIDAD ===")
    print(f"  total={total}  correctas={correctas}  coincidencia={pct:.2f}%")
    print(f"  meta >= 90% → {'✅ CUMPLE' if resultado['cumple'] else '❌ NO CUMPLE'}")
    print(f"\n  Matriz (esperada → emitida):")
    for esp, fila in sorted(matriz.items()):
        tot = sum(fila.values())
        for emit, n in sorted(fila.items()):
            print(f"    {esp:6} → {emit:6}  {n:2}/{tot}")


if __name__ == "__main__":
    main()