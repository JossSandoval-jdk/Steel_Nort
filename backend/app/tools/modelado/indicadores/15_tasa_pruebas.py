"""
15_tasa_pruebas.py
==================
I-5.3 - Tasa de funcionamiento = casos_exitosos / casos_totales.

Corre la suite `backend/tests` con pytest, deja el JUnit XML y calcula la tasa.

Entrada : backend/tests (suite pytest)
Salida  : output/modelado/indicadores/reporte_pytest.xml
          output/modelado/indicadores/tasa_pruebas.json

Uso:
    python indicadores/15_tasa_pruebas.py
"""

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Config del modelado (parents[1] = tools/modelado/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelado_config import DIR_MODELADO, log  # noqa: E402

DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")
BACKEND = Path(__file__).resolve().parents[4]          # .../backend
RUTA_XML = os.path.join(DIR_VAL, "reporte_pytest.xml")


def correr_pytest() -> bool:
    cmd = [sys.executable, "-m", "pytest", "tests", f"--junitxml={RUTA_XML}", "-q"]
    log("Ejecutando: " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(BACKEND), capture_output=True, text=True)
    # 0 = todo OK, 1 = hubo fallos (igual queremos leer el XML).
    if proc.returncode not in (0, 1):
        log(proc.stdout[-2000:])
        log(proc.stderr[-2000:])
        return False
    return True


def leer_junit():
    if not os.path.isfile(RUTA_XML):
        return None
    raiz = ET.parse(RUTA_XML).getroot()
    suites = [raiz] if raiz.tag == "testsuite" else list(raiz)
    total = fallos = errores = omitidos = 0
    for s in suites:
        total += int(s.get("tests", 0))
        fallos += int(s.get("failures", 0))
        errores += int(s.get("errors", 0))
        omitidos += int(s.get("skipped", 0))
    return total, fallos, errores, omitidos


def main():
    correr_pytest()
    datos = leer_junit()
    if datos is None:
        log("No se genero el JUnit XML.")
        return

    total, fallos, errores, omitidos = datos
    exitosos = total - fallos - errores - omitidos
    tasa = round(exitosos / total, 4) if total else 0.0

    resultado = {
        "indicador": "I-5.3",
        "meta": 0.90,
        "casos_totales": total,
        "casos_exitosos": exitosos,
        "fallidos": fallos,
        "errores": errores,
        "omitidos": omitidos,
        "tasa_funcionamiento": tasa,
        "cumple": bool(total and tasa >= 0.90),
        "suite": "backend/tests",
    }
    ruta = os.path.join(DIR_VAL, "tasa_pruebas.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2)

    print("\n=== I-5.3 TASA DE FUNCIONAMIENTO ===")
    print(f"  {exitosos}/{total} pruebas OK ({tasa:.2%}) -> "
          f"{'CUMPLE' if resultado['cumple'] else 'NO CUMPLE'} (meta >= 90 %)")
    print(f"Informe: {ruta}")


if __name__ == "__main__":
    main()
