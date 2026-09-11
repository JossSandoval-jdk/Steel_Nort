"""MENU COMPLETO del pipeline SteelNort.

Un solo script para ejecutar TODO el flujo con mensajes de avance paso a paso:

    1. Generar captura NORMAL (colectores + carga T-SQL real)
    2. Generar captura CON ANOMALIAS (colectores + inyeccion de fallos)
    3. Preparacion de datos        (00 -> 06) -> CSVs del dataset
    4. Modelado / Reentrenamiento  (01 -> 03)   -> modelo + FPR
    5. Reglas de motor + Diagnostico (04 -> 05) -> informe_deteccion.json
    6. Despliegue a produccion     (ml/artifacts + training/datasets)
    7. Resultados obtenidos        (informe, FPR, importancia, artefactos)

La raiz de trabajo (OUTPUT_ROOT) por defecto es:
    1) la variable STEELNORT_OUTPUT_DIR,
    2) si no, D:\\Steel_Nort\\output si existe (continuidad con resultados previos),
    3) si no, backend/training/output.

Uso:
    python tools/menu_pipeline.py            (menu interactivo)
    python tools/menu_pipeline.py --todo     (flujo completo sin preguntar)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from contextlib import suppress

with suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
NUCLEO = BACKEND_ROOT / "app" / "training" / "nucleo"
PREP_DIR = NUCLEO / "data_preparation"
MODELING_DIR = NUCLEO / "modeling"
CAPTURES_DIR = BACKEND_ROOT / "training" / "captures"
ARTIFACTS_DIR = BACKEND_ROOT / "ml" / "artifacts"
DATASETS_DIR = BACKEND_ROOT / "training" / "datasets"
LOGS_DIR = BACKEND_ROOT / "logs"
CONFIG_FILE = BACKEND_ROOT / ".menu_pipeline.json"

PREP_SCRIPTS = [
    "00_inventario.py",
    "01_seleccion.py",
    "02_limpieza.py",
    "03_transformacion.py",
    "04_integracion.py",
    "05_seleccion_variables_clave.py",
    "06_seleccion_variables_principales.py",
]
MODELADO_SCRIPTS = [
    "01_muestras.py",
    "02_correlacion.py",
    "03_deteccion_isolation_forest.py",
]
POST_SCORE = ["04_reglas_motor.py", "05_diagnostico_resultados.py"]

COLECTORS = ["metrics_collector", "log_event_collector", "xe_collector"]


# ----------------------------------------------------------------------
# Utilidades de presentacion
# ----------------------------------------------------------------------

def titulo(texto):
    ancho = 74
    print("\n" + "=" * ancho)
    print(("  " + texto).ljust(ancho))
    print("=" * ancho)


def paso(n, total, texto):
    print("\n" + "-" * 74)
    print(f"[PASO {n}/{total}] {texto}")
    print("-" * 74)


def info(msg):
    print(f"  • {msg}", flush=True)


def ok(msg):
    print(f"  ✓ {msg}", flush=True)


def warn(msg):
    print(f"  ⚠ {msg}", flush=True)


def err(msg):
    print(f"  ✗ {msg}", flush=True)


# ----------------------------------------------------------------------
# Configuracion persistente (output root)
# ----------------------------------------------------------------------

def _output_root_default() -> Path:
    env = os.getenv("STEELNORT_OUTPUT_DIR")
    if env:
        return Path(env)
    return BACKEND_ROOT / "training" / "output"


def cargar_config() -> dict:
    cfg = {"output_root": str(_output_root_default())}
    if CONFIG_FILE.is_file():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def guardar_config(cfg: dict):
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ----------------------------------------------------------------------
# Subprocesos con salida en vivo
# ----------------------------------------------------------------------

def run_proceso(cmd, env_extra=None, prefijo="", cwd=None, check=True):
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    proc = subprocess.Popen(
        cmd, cwd=str(cwd or BACKEND_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )

    def _pump():
        for linea in proc.stdout:
            print(f"    {prefijo}{linea}", end="")

    t = threading.Thread(target=_pump, daemon=True)
    t.start()
    rc = proc.wait()
    t.join(timeout=1)
    if check and rc != 0:
        raise RuntimeError(f"Fallo: {' '.join(map(str, cmd))} (rc={rc})")
    return rc


# ----------------------------------------------------------------------
# Precondiciones
# ----------------------------------------------------------------------

def sql_podman_ok() -> bool:
    try:
        import pyodbc
        from app.collector.config import SQL_SERVER_CONN_STR
        conn = pyodbc.connect(SQL_SERVER_CONN_STR, timeout=10, autocommit=True)
        cur = conn.cursor()
        cur.execute("SELECT @@SERVERNAME")
        nombre = cur.fetchval()
        conn.close()
        info(f"SQL de negocio (Podman/1434): {nombre}")
        return True
    except Exception as exc:
        err(f"SQL de negocio NO accesible: {exc}")
        return False


def preflight(cfg: dict) -> bool:
    titulo("PRECONDICIONES")
    root = Path(cfg["output_root"])
    root.mkdir(parents=True, exist_ok=True)
    os.makedirs(CAPTURES_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    info(f"Raiz de trabajo (OUTPUT_ROOT): {root}")
    if not sql_podman_ok():
        return False
    info(f"Colectores: {', '.join(COLECTORS)}")
    if not (BACKEND_ROOT / ".venv").is_dir():
        warn("No se detecto .venv en backend (los pasos usan el python actual)")
    return True


def listar_corridas(root: Path) -> list[str]:
    """Nombres de corridas: subcarpetas de baseline/ y anomalias/ +
    corridas legacy directas en la raiz (excluye artefactos)."""
    carpetas_reservadas = {"inventario", "limpio", "integrado",
                           "modelado", "datasets", "baseline", "anomalias"}
    nombres = []
    for grupo in ("baseline", "anomalias"):
        gp = root / grupo
        if gp.is_dir():
            for d in gp.iterdir():
                if d.is_dir():
                    nombres.append(d.name)
    if root.is_dir():
        for d in root.iterdir():
            if d.is_dir() and d.name not in carpetas_reservadas \
                    and d.name not in nombres:
                nombres.append(d.name)
    return sorted(nombres)


def _timeline_anomalias(root: Path) -> Path | None:
    """Timeline de la corrida de anomalias más reciente (en anomalias/
    y, por compatibilidad, en la raiz)."""
    candidatos = list((root / "anomalias").glob("*anomalias_timeline.csv")) \
        if (root / "anomalias").is_dir() else []
    candidatos += list(root.glob("*anomalias_timeline.csv"))
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: p.stat().st_mtime)


# ----------------------------------------------------------------------
# Colectores en background
# ----------------------------------------------------------------------

def _start_collectors(dataset: str, log_base: Path) -> list[tuple[str, subprocess.Popen, object]]:
    """Arranca los 3 colectores; devuelve handles para detenerlos."""
    env = os.environ.copy()
    env["DATASET_NAME"] = dataset
    env["OUTPUT_BASE"] = str(CAPTURES_DIR)
    env["PYTHONIOENCODING"] = "utf-8"
    handles = []
    for nombre in COLECTORS:
        salida = open(log_base / f"{nombre}.log", "w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "app.collector." + nombre],
            cwd=str(BACKEND_ROOT), env=env,
            stdout=salida, stderr=subprocess.STDOUT,
        )
        handles.append((nombre, proc, salida))
        info(f"collector '{nombre}' arrancado (pid {proc.pid})")
    return handles


def _stop_collectors(handles, grace=6):
    info(f"Esperando {grace}s para captura parcial de cola...")
    time.sleep(grace)
    for nombre, proc, salida in handles:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        salida.close()
        info(f"collector '{nombre}' detenido")


def _pegar_captura(dataset: str, corrida: str, root: Path,
                   grupo: str = "") -> Path:
    """Copia training/captures/<dataset>/*.log (y el timeline de anomalias
    si existe) a <root>/[grupo]/<corrida>/."""
    origen = CAPTURES_DIR / dataset
    destino = Path(root)
    if grupo:
        destino = destino / grupo
    destino = destino / corrida
    destino.mkdir(parents=True, exist_ok=True)
    copiados = 0
    for archivo in glob.glob(str(origen / "*.log")):
        shutil.copy2(archivo, destino / os.path.basename(archivo))
        copiados += 1
    tl = origen / "anomalias_timeline.csv"
    if tl.is_file():
        shutil.copy2(tl, destino / "anomalias_timeline.csv")
        copiados += 1
    ok(f"Captura {copiados} archivo(s) -> {destino}")
    return destino


def _reportar_corrida(dir_corrida: Path, nombre: str):
    for f in ("metrics.log", "events.log", "sqlserver_logs.log"):
        p = dir_corrida / f
        if p.is_file():
            n = sum(1 for _ in p.open(encoding="utf-8", errors="replace"))
            ok(f"{nombre}/{f}: {n} lineas")
        else:
            warn(f"{nombre}/{f}: FALTA")


# ----------------------------------------------------------------------
# PASO 1: captura NORMAL
# ----------------------------------------------------------------------

def paso_captura_normal(cfg: dict, duracion=90, workers=10, corrida=None):
    root = Path(cfg["output_root"])
    if corrida is None:
        corrida = f"carga{len(listar_corridas(root)) + 1}"
    paso(1, 7, f"CAPTURA NORMAL -> baseline/{corrida}")
    if not sql_podman_ok():
        return False
    dataset = "cap_" + corrida
    log_base = LOGS_DIR / f"run_{corrida}"
    os.makedirs(log_base, exist_ok=True)

    handles = _start_collectors(dataset, log_base)
    try:
        time.sleep(4)
        ok(f"Generando carga normal T-SQL ({duracion}s, {workers} workers)...")
        run_proceso(
            [sys.executable, "-u", "tools/generar_carga.py",
             "--duracion", str(duracion), "--workers", str(workers)],
            prefijo="[CARGA-NORMAL] ",
        )
    finally:
        _stop_collectors(handles)

    dir_corrida = _pegar_captura(dataset, corrida, root, grupo="baseline")
    _reportar_corrida(dir_corrida, corrida)
    ok(f"Corrida NORMAL completada (baseline): {dir_corrida}")
    return True


# ----------------------------------------------------------------------
# PASO 2: captura CON ANOMALIAS
# ----------------------------------------------------------------------

def paso_captura_anomalias(cfg: dict, duracion=180,
                           faults="lockwait,fault1,fault2,fault5,fault3",
                           corrida="carga5", workers=10):
    root = Path(cfg["output_root"])
    paso(2, 7, f"CAPTURA CON ANOMALIAS -> anomalias/{corrida}")
    if not sql_podman_ok():
        return False
    dataset = "cap_" + corrida
    log_base = LOGS_DIR / f"run_{corrida}"
    os.makedirs(log_base, exist_ok=True)

    handles = _start_collectors(dataset, log_base)
    try:
        time.sleep(4)
        ok(f"Inyectando anomalias de rendimiento ({duracion}s, fallos={faults})...")
        run_proceso(
            [sys.executable, "-u", "tools/inyectar_anomalias.py",
             "--duracion", str(duracion), "--faults", faults,
             "--corrida", corrida, "--output-root", str(root / "anomalias")],
            prefijo="[ANOM] ",
        )
    finally:
        _stop_collectors(handles)

    dir_corrida = _pegar_captura(dataset, corrida, root, grupo="anomalias")
    _reportar_corrida(dir_corrida, corrida)
    if (dir_corrida / "anomalias_timeline.csv").is_file():
        ok(f"Ground truth: {dir_corrida / 'anomalias_timeline.csv'}")
    return True


# ----------------------------------------------------------------------
# PASO 3: preparacion de datos
# ----------------------------------------------------------------------

def paso_preparacion(cfg: dict):
    root = Path(cfg["output_root"])
    paso(3, 7, "PREPARACION DE DATOS (00->06)")
    corridas = listar_corridas(root)
    info(f"Corridas detectadas: {corridas}")
    if not corridas:
        err("Sin corridas. Genera primero captures (pasos 1 y/o 2).")
        return False
    env = {"STEELNORT_OUTPUT_DIR": str(root)}
    for script in PREP_SCRIPTS:
        info(f"Ejecutando {script}...")
        run_proceso([sys.executable, "-u", str(PREP_DIR / script)],
                    env_extra=env, cwd=PREP_DIR, prefijo=f"[{script}] ")

    ds = root / "integrado" / "dataset_carga_principales.csv"
    if ds.is_file():
        n = sum(1 for _ in ds.open(encoding="utf-8-sig", errors="replace")) - 1
        ok(f"Dataset preparado: {ds} ({max(n, 0)} filas)")
        cols = ds.open(encoding="utf-8-sig").readline().strip().replace(",", ", ")
        info(f"Columnas: {cols[:200]}...")
    else:
        warn("No se encontro dataset_carga_principales.csv")
    return True


# ----------------------------------------------------------------------
# PASO 4: modelado / reentrenamiento
# ----------------------------------------------------------------------

def paso_modelado(cfg: dict):
    root = Path(cfg["output_root"])
    paso(4, 7, "MODELADO / REENTRENAMIENTO (01->03)")
    env = {"STEELNORT_OUTPUT_DIR": str(root)}
    for script in MODELADO_SCRIPTS:
        info(f"Ejecutando {script}...")
        run_proceso([sys.executable, "-u", str(MODELING_DIR / script)],
                    env_extra=env, cwd=MODELING_DIR, prefijo=f"[{script}] ")

    alertas = root / "modelado" / "deteccion" / "alertas_test.csv"
    if alertas.is_file():
        info("Ventanas de test (corrida de anomalias) marcadas por umbral:")
        run_proceso(
            [sys.executable, "-u", "-c",
             "import pandas as pd; d=pd.read_csv(r'" + str(alertas).replace("\\", "/")
             + "');"
             "import sys; [print('    umbral %s: %.2f%%' % (q, 100*d[q].mean()))"
             " for q in ('q10','q05','q01')]"],
            env_extra=env, cwd=MODELING_DIR, prefijo="",
        )
    return True


# ----------------------------------------------------------------------
# PASO 5: reglas de motor + diagnostico
# ----------------------------------------------------------------------

def paso_diagnostico(cfg: dict):
    root = Path(cfg["output_root"])
    paso(5, 7, "REGLAS DE MOTOR + DIAGNOSTICO (04->05)")
    env = {"STEELNORT_OUTPUT_DIR": str(root)}
    for script in POST_SCORE:
        info(f"Ejecutando {script}...")
        run_proceso([sys.executable, "-u", str(MODELING_DIR / script)],
                    env_extra=env, cwd=MODELING_DIR, prefijo=f"[{script}] ")
    informe = root / "modelado" / "diagnostico" / "informe_deteccion.json"
    if informe.is_file():
        ok(f"Informe de diagnostico: {informe}")
    return True


# ----------------------------------------------------------------------
# PASO 6: despliegue a produccion
# ----------------------------------------------------------------------

def paso_despliegue(cfg: dict):
    root = Path(cfg["output_root"])
    paso(6, 7, "DESPLIEGUE DE ARTEFACTOS A PRODUCCION")
    det_dir = root / "modelado" / "deteccion"
    cor_dir = root / "modelado" / "correlacion"
    mod_dir = root / "modelado"

    pares = [
        (det_dir / "modelo_isolation_forest.joblib", ARTIFACTS_DIR, "modelo_isolation_forest.joblib"),
        (det_dir / "scaler.joblib", ARTIFACTS_DIR, "scaler.joblib"),
        (cor_dir / "features_modelo.csv", ARTIFACTS_DIR, "features_modelo.csv"),
        (cor_dir / "reglas_umbrales.csv", ARTIFACTS_DIR, "reglas_umbrales.csv"),
        (cor_dir / "variables_correlacion.csv", ARTIFACTS_DIR, "variables_correlacion.csv"),
        (det_dir / "importancia_variables.csv", ARTIFACTS_DIR, "importancia_variables.csv"),
        (mod_dir / "dataset_muestras_train.pkl", DATASETS_DIR, "dataset_muestras_train.pkl"),
    ]

    faltan = [p for p, _, _ in pares if not p.is_file()]
    if faltan:
        err(f"Faltan artefactos: {[str(p) for p in faltan]}")
        return False

    # Backup de los actuales
    for _, destino, nombre in pares:
        viejo = destino / nombre
        if viejo.is_file() and not (destino / (nombre + ".bak_old")).is_file():
            shutil.copy2(viejo, destino / (nombre + ".bak_old"))
    # Copia de los nuevos
    for origen, destino, nombre in pares:
        destino.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino / nombre)
        info(f"{nombre} <- {origen}")

    ok("Artefactos desplegados en ml/artifacts + training/datasets")
    info("El detector recargara al reiniciar el backend (get_detector cache).")
    return True


# ----------------------------------------------------------------------
# PASO 7: resultados obtenidos
# ----------------------------------------------------------------------

def paso_resultados(cfg: dict):
    root = Path(cfg["output_root"])
    paso(7, 7, "RESULTADOS OBTENIDOS")

    corridas = listar_corridas(root)
    info(f"Corridas disponibles: {corridas}")

    # 1. Informe de diagnostico
    informe = root / "modelado" / "diagnostico" / "informe_deteccion.json"
    if informe.is_file():
        d = json.loads(informe.read_text(encoding="utf-8"))
        res = d.get("resumen_deteccion", {})
        ok("Informe de deteccion (carga5 vs ground truth):")
        print(f"      ventanas test: {res.get('ventanas_carga5_test')} | "
              f"fault: {res.get('ventanas_fault')} | normal: {res.get('ventanas_normal')}")
        print(f"      alertas en fault: {res.get('alertas_en_fault')} | "
              f"falsas en normal: {res.get('alertas_en_normal_fp')} | "
              f"recall: {res.get('recall')} | fpr: {res.get('fpr')}")
        for fault, det in d.get("por_fault", {}).items():
            r = det.get("reglas", {})
            m = det.get("deteccion", {})
            vc = det.get("variables_causantes_top", [])[:4]
            print(f"      • {fault}: TPR {m.get('tpr')} | "
                  f"reglas {r.get('reglas_disparadas') or '-'} | "
                  f"top vars: {', '.join(v['variable'] for v in vc)}")
        concl = d.get("conclusion", {})
        info(f"Conclusion: es_anomalo={concl.get('es_anomalo')}, "
             f"faults={concl.get('faults_inyectados')}")
    else:
        warn("Informe de diagnostico no generado todavia (paso 5).")

    # 2. FPR del modelo
    alertas = root / "modelado" / "deteccion" / "alertas_test.csv"
    if alertas.is_file():
        try:
            import pandas as pd
            df = pd.read_csv(alertas).fillna(0)
            info("Ventanas de test (corrida de anomalias) marcadas:")
            for q in ("q01", "q05", "q10"):
                print(f"      {q}: {100 * df[q].mean():.2f}% del test")
        except Exception as exc:
            warn(f"Deteccion no disponible: {exc}")

    # 3. Importancia de variables
    imp = root / "modelado" / "deteccion" / "importancia_variables.csv"
    if imp.is_file():
        try:
            import pandas as pd
            df = pd.read_csv(imp, encoding="utf-8-sig")
            info("Top 8 variables de mayor importancia:")
            for _, r in df.head(8).iterrows():
                print(f"      {r['columna']:<28s} {float(r['importancia']):.4f}")
        except Exception as exc:
            warn(f"Importancia no disponible: {exc}")

    # 4. Ground truth de la corrida de anomalias
    tl = _timeline_anomalias(root)
    if tl:
        info(f"Ground truth de anomalias ({tl.parent.name}):")
        with tl.open(encoding="utf-8") as f:
            for linea in list(f)[1:]:
                print(f"      {linea.strip()}")

    # 5. Artefactos desplegados
    info("Artefactos en produccion (ml/artifacts):")
    for p in sorted(glob.glob(str(ARTIFACTS_DIR / "*"))):
        if os.path.isfile(p):
            sz = os.path.getsize(p) / 1024
            fecha = datetime.fromtimestamp(os.path.getmtime(p)).strftime("%d/%m %H:%M")
            print(f"      {os.path.basename(p):<36s} {sz:8.1f} KB  {fecha}")

    return True


# ----------------------------------------------------------------------
# Flujo completo
# ----------------------------------------------------------------------

def flujo_completo(cfg: dict, solo_capturas=False):
    if not preflight(cfg):
        return False
    corridas = listar_corridas(Path(cfg["output_root"]))
    num_corrida = len(corridas) + 1

    ok("Generando captura NORMAL de referencia...")
    paso_captura_normal(cfg, corrida=f"carga{num_corrida}")
    ok("Generando captura CON ANOMALIAS (carga5)...")
    paso_captura_anomalias(cfg, corrida="carga5")

    if solo_capturas:
        return True
    paso_preparacion(cfg)
    paso_modelado(cfg)
    paso_diagnostico(cfg)
    paso_despliegue(cfg)
    paso_resultados(cfg)
    return True


# ----------------------------------------------------------------------
# Menu interactivo
# ----------------------------------------------------------------------

MENU_TEXTO = """
╔══════════════════════════════════════════════════════════════╗
║   STEELNORT — MENU COMPLETO DEL PIPELINE                     ║
╠══════════════════════════════════════════════════════════════╣
║   1  Captura NORMAL        (colectores + carga T-SQL real)   ║
║   2  Captura ANOMALIAS     (inyeccion de fallos + timeline)  ║
║   3  Preparacion de datos  (00→06 → datasets CSV)            ║
║   4  Modelado/Reentrenar   (01→03 → modelo + FPR)            ║
║   5  Reglas + Diagnostico  (04→05 → informe_deteccion.json)  ║
║   6  Desplegar artefactos  (ml/artifacts + training/datasets)║
║   7  Resultados obtenidos  (informe, FPR, importancia, ...)  ║
║   9  TODO  (flujo completo sin parar)                        ║
║   0  Configuracion / raiz de trabajo                         ║
║   Q  Salir                                                   ║
╚══════════════════════════════════════════════════════════════╝
"""


def opcion_config(cfg: dict):
    titulo("CONFIGURACION")
    print(f"  Raiz de trabajo actual: {cfg['output_root']}")
    r = input("  Nueva raiz (Enter para mantener): ").strip()
    if r:
        cfg["output_root"] = r
        guardar_config(cfg)
        ok(f"Raiz actualizada: {cfg['output_root']}")
    preflight(cfg)
    corridas = listar_corridas(Path(cfg["output_root"]))
    info(f"Corridas en la raiz: {corridas or 'ninguna'}")


def main():
    ap = argparse.ArgumentParser(description="Menu del pipeline SteelNort")
    ap.add_argument("--todo", action="store_true", help="flujo completo sin preguntar")
    ap.add_argument("--solo-capturas", action="store_true",
                    help="con --todo: solo genera capturas normal+anomalias")
    ap.add_argument("--duracion-normal", type=int, default=90)
    ap.add_argument("--duracion-anom", type=int, default=180)
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    cfg = cargar_config()

    if args.todo:
        cmp = dict(cfg)
        cmp["duracion_normal"] = args.duracion_normal
        cmp["duracion_anomalias"] = args.duracion_anom
        cmp["workers"] = args.workers
        return 0 if flujo_completo(cmp, solo_capturas=args.solo_capturas) else 1

    titulo("MENU DEL PIPELINE STEELNORT")
    print(f"  Raiz de trabajo: {cfg['output_root']}")
    corridas = listar_corridas(Path(cfg["output_root"]))
    print(f"  Corridas detectadas: {corridas or 'ninguna'}")
    print(MENU_TEXTO)

    while True:
        op = input("  Opcion: ").strip().lower()
        try:
            if op == "1":
                corrida = input("  Nombre corrida (Enter = auto): ").strip() or None
                paso_captura_normal(cfg, corrida=corrida)
            elif op == "2":
                corrida = input("  Nombre corrida (Enter = carga5): ").strip() or "carga5"
                paso_captura_anomalias(cfg, corrida=corrida)
            elif op == "3":
                paso_preparacion(cfg)
            elif op == "4":
                paso_modelado(cfg)
            elif op == "5":
                paso_diagnostico(cfg)
            elif op == "6":
                paso_despliegue(cfg)
            elif op == "7":
                paso_resultados(cfg)
            elif op == "9":
                flujo_completo(cfg)
            elif op == "0":
                opcion_config(cfg)
            elif op in ("q", "quit", "salir"):
                ok("Hasta luego.")
                break
            else:
                err(f"Opcion desconocida '{op}'")
        except KeyboardInterrupt:
            warn("Interrumpido por el usuario.")
        except Exception as exc:
            err(f"Error: {exc}")


if __name__ == "__main__":
    main()