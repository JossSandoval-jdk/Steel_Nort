"""MENU DEL LABORATORIO DE MODELADO SteelNort.

Orientado al ENSEMBLE_Z (IsolationForest + COPOD) y a la comparacion de
modelos candidatos de deteccion de anomalias:

    1. Entrenar detectores alternativos  (detectar_candidatos.py: LOF/OCSVM/
       Elliptic/COPOD) -> alertas_test_*.csv + modelo_*.joblib en deteccion/
    2. Tuning del ENSEMBLE_Z            (ajustar_isolation_forest.py)
                                        -> grilla_iso/ (grilla, resumen, ranking)
    3. Comparar todos los modelos       (06_comparacion_modelado.py)
                                        -> tabla_comparativa_modelos.csv
    4. Discriminacion del ENSEMBLE_Z    (medir_discriminacion.py)
                                        -> informe_discriminacion.csv/.json
    5. Validacion completa del candidato (validar_candidato.py --stage todo)
                                        -> deteccion/validacion/ (INFORME_VALIDACION.md)
    6. Verificar el Detector en produccion (verificar_detector.py)

La raiz de trabajo coincide con menu_pipeline.py (.menu_pipeline.json o
STEELNORT_OUTPUT_DIR). Cada script resuelve sus imports solo y lee la misma
config (nucleo/modeling/config.py).

Uso:
    python tools/menu_laboratorio.py          (menu interactivo)
    python tools/menu_laboratorio.py --todo   (flujo completo sin preguntar)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from tools.menu_pipeline import (  # noqa: E402
    BACKEND_ROOT,
    MODELING_DIR,
    cargar_config,
    err,
    info,
    ok,
    paso,
    run_proceso,
    titulo,
    warn,
)

EXPERIMENTAL = MODELING_DIR / "experimental"
DETECTORES = ["lof", "elliptic", "ocsvm", "copod"]

PROGRAMAS = {
    "detectar": EXPERIMENTAL / "detectar_candidatos.py",
    "tuning": EXPERIMENTAL / "ajustar_isolation_forest.py",
    "comparar": EXPERIMENTAL / "06_comparacion_modelado.py",
    "medir": EXPERIMENTAL / "medir_discriminacion.py",
    "validar": EXPERIMENTAL / "validar_candidato.py",
    "verificar": EXPERIMENTAL / "verificar_detector.py",
}


def _env(cfg: dict) -> dict:
    return {"STEELNORT_OUTPUT_DIR": str(cfg["output_root"])}


def _raiz(cfg: dict) -> Path:
    return Path(cfg["output_root"])


def _ver_csv(ruta: Path, head=60):
    if not ruta.is_file():
        warn(f"No existe: {ruta}")
        return
    import pandas as pd
    df = pd.read_csv(ruta, encoding="utf-8-sig")
    print(df.head(head).to_string(index=False))
    ok(f"({len(df)} filas x {len(df.columns)} columnas) -> {ruta}")


def op_detectar(cfg: dict, nombres=None):
    paso(1, 6, f"DETECTAR CANDIDATOS {nombres or DETECTORES}")
    cmd = [sys.executable, "-u", str(PROGRAMAS["detectar"])]
    if nombres:
        cmd += nombres
    run_proceso(cmd, env_extra=_env(cfg), cwd=str(MODELING_DIR),
                prefijo="[DETECTAR] ")
    ok(f"Salida en deteccion/: alertas_test_*.csv, modelo_*.joblib, "
       f"scores_muestras_*.csv, importancia_variables_*.csv")


def op_tuning(cfg: dict, args=None):
    paso(2, 6, "TUNING DEL ENSEMBLE_Z (grilla isolation_forest -> z_score)")
    cmd = [sys.executable, "-u", str(PROGRAMAS["tuning"])]
    if args:
        cmd += args
    run_proceso(cmd, env_extra=_env(cfg), cwd=str(MODELING_DIR),
                prefijo="[TUNING] ")
    grilla = _raiz(cfg) / "modelado" / "grilla_iso"
    if grilla.is_dir():
        ok(f"Salida en grilla_iso/: "
           f"{sorted(p.name for p in grilla.iterdir())}")


def op_comparar(cfg: dict):
    paso(3, 6, "COMPARACION DE MODELOS CANDIDATOS")
    dir_det = _raiz(cfg) / "modelado" / "deteccion"
    disponibles = sorted(dir_det.glob("alertas_test*.csv"))
    if not disponibles:
        err("Sin alertas_test*.csv. Entrena detectores (opcion 1) o "
            "genera las alertas del pipeline (menu_pipeline, paso 4/5).")
        return
    info(f"Archivos: {[p.name for p in disponibles]}")
    run_proceso([sys.executable, "-u", str(PROGRAMAS["comparar"])],
                env_extra=_env(cfg), cwd=str(MODELING_DIR),
                prefijo="[COMPARA] ")


def op_ver_comparativa(cfg: dict):
    titulo("TABLA COMPARATIVA DE MODELOS")
    _ver_csv(_raiz(cfg) / "modelado" / "deteccion" /
             "tabla_comparativa_modelos.csv")


def op_medir(cfg: dict):
    paso(4, 6, "DISCRIMINACION DEL ENSEMBLE_Z EN TEST")
    run_proceso([sys.executable, "-u", str(PROGRAMAS["medir"])],
                env_extra=_env(cfg), cwd=str(MODELING_DIR),
                prefijo="[DISC] ")
    titulo("INFORME DE DISCRIMINACION")
    _ver_csv(_raiz(cfg) / "modelado" / "deteccion" /
             "informe_discriminacion.csv")
    j = _raiz(cfg) / "modelado" / "deteccion" / "informe_discriminacion.json"
    if j.is_file():
        d = json.loads(j.read_text(encoding="utf-8"))
        ok(f"Resumen: " + json.dumps(d, ensure_ascii=False, default=str))


def op_validar(cfg: dict, stage=None):
    paso(5, 6, "VALIDACION COMPLETA DEL CANDIDATO ENSEMBLE_Z")
    cmd = [sys.executable, "-u", str(PROGRAMAS["validar"]),
           "--stage", stage or "todo"]
    run_proceso(cmd, env_extra=_env(cfg), cwd=str(MODELING_DIR),
                prefijo="[VALIDAR] ")
    val_dir = _raiz(cfg) / "modelado" / "deteccion" / "validacion"
    if val_dir.is_dir():
        ok(f"Salida en deteccion/validacion/: "
           f"{sorted(p.name for p in val_dir.iterdir())}")


def op_verificar(cfg: dict):
    paso(6, 6, "VERIFICAR EL DETECTOR DE PRODUCCION (ml/artifacts)")
    run_proceso([sys.executable, "-u", str(PROGRAMAS["verificar"])],
                env_extra=_env(cfg), cwd=str(MODELING_DIR),
                prefijo="[VERIF] ")


def op_ver_validacion(cfg: dict):
    titulo("INFO DE VALIDACION DEL ENSEMBLE_Z")
    val_dir = _raiz(cfg) / "modelado" / "deteccion" / "validacion"
    if not val_dir.is_dir():
        err(f"No existe deteccion/validacion/. Ejecuta la validacion "
            f"(opcion 5): {val_dir}")
        return
    info(f"Directorio: {val_dir}")
    for p in sorted(val_dir.iterdir()):
        sz = p.stat().st_size
        info(f"  {p.name}  ({sz} bytes)")
    informe = val_dir / "INFORME_VALIDACION.md"
    if informe.is_file():
        print("\n" + informe.read_text(encoding="utf-8"))
    _ver_csv(val_dir / "resumen_modelos.csv")
    _ver_csv(val_dir / "aucs.csv")


def consola():
    titulo("MENU DEL LABORATORIO — ENSEMBLE_Z y COMPARACION")
    print("""
═══════ PIPELINE DE PRODUCCION (ver tools/menu_pipeline.py) ═══════
   (capturas -> preparacion -> modelado 01-03 -> reglas -> despliegue)

═══════ LABORATORIO DE MODELADO ═══════
 H  Ayuda        : que es el ENSEMBLE_Z, como se combinan ISO+COPOD
                  y donde vive la info de validacion
 1  Detectar     : entrenar alternativos (LOF/OCSVM/Elliptic/COPOD)
 2  Tuning       : ajustar hiperparametros del ENSEMBLE_Z (grilla_iso)
 3  Comparar     : generar tabla comparativa de todos los modelos
 4  Ver tablas   : mostrar la tabla comparativa guardada
 5  Discriminar  : FPR/TPR del ENSEMBLE_Z en test (informe_discriminacion)
 6  Validar      : validacion completa del candidato (INFORME_VALIDACION)
 7  Verificar    : probar el Detector real de produccion (ml/artifacts)
 8  Ver info     : mostrar validacion guardada (opcion 6 con datos ya listos)
 0  Raiz         : configuracion / raiz de trabajo
 X  TODO         : 1(todos) -> 3 -> 2 -> 5 -> 6 -> 7 sin parar
 Q  Salir
""")


def opcion_config(cfg: dict):
    titulo("CONFIGURACION DE RAIZ DE TRABAJO")
    print(f"  Raiz actual: {cfg['output_root']}")
    r = input("  Nueva raiz (Enter para mantener): ").strip()
    if r:
        cfg["output_root"] = r
        from tools.menu_pipeline import guardar_config
        guardar_config(cfg)
        ok(f"Raiz actualizada: {cfg['output_root']}")
    raiz = Path(cfg["output_root"])
    info(f"Raiz: {raiz}")
    info(f"deteccion/ existe: {(raiz / 'modelado' / 'deteccion').is_dir()}")


def ayuda():
    titulo("EL ENSEMBLE_Z (IsolationForest + COPOD combinados)")
    print("""
¿Por que dos modelos?
  IsolationForest   : detecta anomalias aislables en el espacio de features
                      (debe intentar separarlas pocas veces). Da puntuacion
                      via decision_function: mas ALTO = mas NORMAL.
  COPOD             : detecta anomalias de cola (outliers por densidad
                      empirica), metrico y rapido. Su decision_function se
                      invierte para que, como ISO, mas ALTO = mas NORMAL.

¿Como se combinan?
  1) Se entrenan los DOS con las mismas ventanas normales (train).
  2) Sobre ese train se calculan media y desviacion de cada puntuacion:
       mu_iso, sd_iso, mu_copod, sd_copod   (funcion estadisticas)
  3) Cada puntuacion se estandariza a z:  z = (score - mu) / sd
  4) Se promedian los dos z:  z_ens = (z_iso + z_copod) / 2
     -> un solo indice donde NORMAL = por encima de 0, ANOMALO = negativo.
  5) Umbrales congelados sobre el train: q10=-1.1804, q05=-1.3569,
     q01=-2.1446. Una ventana se marca con dureza q__ si z_ens < umbral.
  Esto se llama ENSEMBLE_Z y es lo que usa el detector de produccion.

¿Donde esta implementado y sus datos?
  - Codigo  : backend/app/ml/ensamble_z.py (estadisticas, z_score, EnsambleZ)
              backend/app/ml/detector.py (Detector usa _ens.score + umbrales)
  - Artef.  : backend/ml/artifacts/{modelo_isolation_forest, modelo_copod,
              scaler}.joblib  (desplegados por menu_pipeline, paso 6)
  - Laborat.: backend/training/nucleo/modeling/experimental/
              ajustar_isolation_forest.py   (grilla de tuning)
              medir_discriminacion.py       (informe_discriminacion)
              validar_candidato.py          (deteccion/validacion/)
  - INFO DE VALIDACION:
      backend/training/output/modelado/deteccion/validacion/
      (INFORME_VALIDACION.md + resumen_modelos.csv, aucs.csv,
       estabilidad_semillas.csv, sensibilidad_vars.csv, operativas_runs.csv,
       errores_fp_contribucion.csv, robustez_resumen.json, latencia.json,
       integracion.json, registro_modelo.json, modelo_candidato.joblib)
""", )
    warn("Nota: 'deteccion' (sin acento) es el nombre real de la carpeta.")


def flujo_todo(cfg: dict):
    op_detectar(cfg)
    op_tuning(cfg)
    op_comparar(cfg)
    op_medir(cfg)
    op_validar(cfg)
    op_verificar(cfg)
    op_ver_comparativa(cfg)


def main():
    ap = argparse.ArgumentParser(description="Menu laboratorio SteelNort")
    ap.add_argument("--todo", action="store_true",
                    help="flujo completo sin preguntar")
    ap.add_argument("--raiz", default=None, help="STEELNORT_OUTPUT_DIR")
    args = ap.parse_args()

    cfg = cargar_config()
    if args.raiz:
        cfg["output_root"] = args.raiz

    if args.todo:
        return 0 if flujo_todo(cfg) is not False else 1

    consola()
    while True:
        op = input("  Opcion: ").strip().lower()
        try:
            if op in ("q", "quit", "salir", "exit"):
                ok("Hasta luego.")
                break
            elif op in ("h", "ayuda", "help"):
                ayuda()
            elif op == "1":
                nombres = input("  Detectores (listo vacio = todos, "
                                "p.ej. copod lof): ").split()
                op_detectar(cfg, nombres or None)
            elif op == "2":
                op_tuning(cfg)
            elif op == "3":
                op_comparar(cfg)
            elif op == "4":
                op_ver_comparativa(cfg)
            elif op == "5":
                op_medir(cfg)
            elif op == "6":
                op_validar(cfg)
            elif op == "7":
                op_verificar(cfg)
            elif op == "8":
                op_ver_validacion(cfg)
            elif op == "0":
                opcion_config(cfg)
            elif op == "x":
                flujo_todo(cfg)
            else:
                err(f"Opcion desconocida '{op}'")
        except KeyboardInterrupt:
            warn("Interrumpido por el usuario.")
        except Exception as exc:
            err(f"Error: {exc}")


if __name__ == "__main__":
    main()