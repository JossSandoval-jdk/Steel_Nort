"""Inyector de anomalias de rendimiento REALES contra el SQL de negocio (VPS/Podman).

Complementa ``tools/generar_carga.py`` (carga normal) con escenarios de
anomalia ejecutados DENTRO del motor. Cada fallo tiene una huella de
rendimiento identificable en las metricas/eventos que capturan los
collectors:

    lockwait  -> retencion de lock con sesiones bloqueadas (lock_waits)
    fault1    -> escrituras al log por INSERTs/UPDATEs concurrentes (total_writes)
    fault2    -> falta de indice / full scan: lecturas fisicas altas (total_reads)
    fault3    -> CPU alta por loops/agregados pesados (cpu_usr)
    fault5    -> commits altamente concurrentes (transactions_per_sec)

Ejecuta una secuencia alternada: normal -> fault -> normal -> fault ...
y al terminar escribe el ground truth automatico:

    <corrida>/anomalias_timeline.csv      (tipo,inicio,fin en el reloj local)
    <corrida>/descripcion_simulacion.json (plan de la simulacion)

Ese timeline es el que consume ``05_diagnostico_resultados.py`` para
cruzar deteccion vs realidad.

Uso:
    python tools/inyectar_anomalias.py --duracion 180 --faults lockwait,fault1,fault2,fault5,fault3 \
        --corrida carga5

(mientras corre, mantenga prendidos el/los collectors para que la corrida
quede capturada en training/captures/<nombre>).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from contextlib import suppress

with suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import pyodbc  # noqa: E402

from app.collector.config import SQL_SERVER_CONN_STR  # noqa: E402
import generar_carga  # noqa: E402  (reutiliza scratch y ops normales)

NOMBRE_SESION = "SteelNortCargaAnomalia"
SCRATCH_ANOMALIA = "dbo.anomalia_scratch"
FILAS_SCRATCH = 200_000

_random_seg = random.Random(20260911)


def log(msg):
    print(f"[ANOM] {msg}", flush=True)


def _cadena_conexion():
    if "APP=" in SQL_SERVER_CONN_STR:
        return SQL_SERVER_CONN_STR
    return SQL_SERVER_CONN_STR + "APP=" + NOMBRE_SESION + ";"


def _conectar(autocommit=False, timeout=6):
    """Conexion con login timeout corto: si SQL se satura por la misma
    inyeccion, no se montan hilos colgados 15s (cascada de timeouts)."""
    conn = pyodbc.connect(_cadena_conexion(), autocommit=autocommit,
                          timeout=timeout)
    return conn


# ----------------------------------------------------------------------
# Preparacion de la mesa de trabajo
# ----------------------------------------------------------------------

def _aplicar_sql(sql, parametros=None):
    conn = pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
    try:
        cur = conn.cursor()
        if parametros:
            cur.execute(sql, parametros)
        else:
            cur.execute(sql)
        try:
            cur.commit()
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _asegurar_scratch_anomalia():
    """Tabla grande (sin indice en grp/segregador) para full scans reales."""
    _aplicar_sql(
        "IF OBJECT_ID('" + SCRATCH_ANOMALIA + "','U') IS NULL "
        "CREATE TABLE " + SCRATCH_ANOMALIA + " ("
        "id INT IDENTITY(1,1) PRIMARY KEY, "
        "payload VARCHAR(200) NOT NULL, "
        "grp INT NOT NULL, "
        "segregador BIGINT NOT NULL);"
    )
    try:
        conn = pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM " + SCRATCH_ANOMALIA)
        n = int(cur.fetchval() or 0)
        conn.close()
    except Exception:
        n = -1
    if n < FILAS_SCRATCH:
        log("Rellenando anomalia_scratch con filas de trabajo...")
        _aplicar_sql(
            "SET NOCOUNT ON; DELETE FROM " + SCRATCH_ANOMALIA + "; "
            "INSERT INTO " + SCRATCH_ANOMALIA + " (payload, grp, segregador) "
            "SELECT 'anomalia-' + CONVERT(varchar(10), n) AS payload, "
            "(n % 100) AS grp, "
            "CAST(RAND(n) * 1000000000 AS BIGINT) AS segregador "
            "FROM ("
            "SELECT TOP (" + str(FILAS_SCRATCH) + ") ROW_NUMBER() OVER "
            "(ORDER BY (SELECT NULL)) AS n FROM sys.all_objects a "
            "CROSS JOIN sys.all_objects b CROSS JOIN sys.all_objects c"
            ") AS fuente;"
        )
    log(f"{SCRATCH_ANOMALIA}: {max(n, FILAS_SCRATCH)} filas listas")


def limpiar_sesiones():
    try:
        conn = pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        cur = conn.cursor()
        cur.execute("SELECT @@SPID")
        propio = int(cur.fetchval())
        cur.execute(
            "SELECT session_id FROM sys.dm_exec_sessions "
            "WHERE program_name = ? AND session_id > 50 AND session_id <> ?",
            NOMBRE_SESION, propio,
        )
        for row in cur.fetchall():
            try:
                cur.execute(
                    "DECLARE @p int = ?; EXEC('KILL ' + CONVERT(varchar(10), @p))",
                    int(row[0]),
                )
            except Exception:
                pass
        conn.close()
    except Exception:
        pass


# ----------------------------------------------------------------------
# Fases: una funcion por fault. Reciben (duracion) y corren su firma.
# ----------------------------------------------------------------------

def _fase_normal(duracion):
    generar_carga._worker_loop(0, duracion, 0.005)


def _fase_lockwait(duracion):
    # Holder retiene un UPDATE sobre la fila pivote; los workers se atoran.
    try:
        holder = _conectar(autocommit=False)
    except Exception as e:
        log(f"lockwait: no pude tomar conexion holder ({e}); fase saltada")
        return
    bloqueados = []
    try:
        cur = holder.cursor()
        cur.execute("BEGIN TRAN")
        cur.execute(
            "UPDATE " + SCRATCH_ANOMALIA + " SET payload = 'LOCKED' WHERE id = 1"
        )
        fin = time.time() + duracion
        for w in range(6):
            t = threading.Thread(target=_worker_bloqueado, args=(fin,), daemon=True)
            t.start()
            bloqueados.append(t)
        log(f"lockwait: lock retenido {duracion}s sobre id=1 con 6 bloqueados")
        while time.time() < fin:
            time.sleep(0.5)
        cur.execute("COMMIT")
    except Exception as e:
        log(f"lockwait: error en fase ({e}); intentando liberar")
        try:
            cur.execute("ROLLBACK")
        except Exception:
            pass
    finally:
        try:
            holder.close()
        except Exception:
            pass
    for t in bloqueados:
        t.join(timeout=duracion + 3)


def _worker_bloqueado(fin):
    try:
        conn = _conectar(autocommit=False, timeout=4)
        cur = conn.cursor()
        while time.time() < fin:
            try:
                cur.execute(
                    "UPDATE " + SCRATCH_ANOMALIA
                    + " SET payload = 'wait' WHERE id = 1"
                )
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
            time.sleep(0.2)
        conn.close()
    except Exception:
        pass


def _fase_fault1_log_writes(duracion):
    fin = time.time() + duracion

    def worker():
        try:
            conn = _conectar(autocommit=False)
            cur = conn.cursor()
            while time.time() < fin:
                try:
                    cur.execute(
                        "INSERT INTO " + SCRATCH_ANOMALIA
                        + " (payload, grp, segregador) VALUES (?, ?, ?)",
                        ("fault1-" + str(_random_seg.randint(1, 10 ** 9)),
                         _random_seg.randint(0, 99), _random_seg.randint(0, 10 ** 9)),
                    )
                    cur.execute(
                        "UPDATE " + SCRATCH_ANOMALIA
                        + " SET payload = LEFT(CONVERT(varchar(200), "
                        "REPLICATE('x', 100) + ?), 200) WHERE id = "
                        "(SELECT TOP (1) id FROM " + SCRATCH_ANOMALIA + ")",
                        ("fault1-" + str(_random_seg.randint(1, 10 ** 6)),),
                    )
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
            conn.close()
        except Exception:
            pass

    hilos = [threading.Thread(target=worker, daemon=True) for _ in range(8)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    log("fault1: INSERT+UPDATE concurrentes (carga de log)")


def _fase_fault2_full_scan(duracion):
    fin = time.time() + duracion

    def worker():
        try:
            conn = _conectar(autocommit=True)
            cur = conn.cursor()
            while time.time() < fin:
                a = _random_seg.randint(0, 10 ** 9)
                b = a + _random_seg.randint(1000, 100000)
                cur.execute(
                    "SELECT COUNT(*) FROM " + SCRATCH_ANOMALIA
                    + " WHERE segregador BETWEEN ? AND ?", (a, b))
                cur.fetchall()
                # Como la columna segregador NO tiene indice, es un table scan.
                cur.execute(
                    "SELECT COUNT(*) FROM " + SCRATCH_ANOMALIA
                    + " WHERE payload LIKE ? OR grp = ?",
                    ("%" + str(_random_seg.randint(1000, 9999)) + "%",
                     _random_seg.randint(0, 99)),
                )
                cur.fetchall()
            conn.close()
        except Exception:
            pass

    hilos = [threading.Thread(target=worker, daemon=True) for _ in range(6)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    log("fault2: full scans sin indice sobre segregador/payload")


def _fase_fault5_commits(duracion):
    fin = time.time() + duracion

    def worker():
        try:
            conn = _conectar(autocommit=False)
            cur = conn.cursor()
            while time.time() < fin:
                try:
                    cur.execute("BEGIN TRAN")
                    for _ in range(5):
                        cur.execute(
                            "INSERT INTO " + SCRATCH_ANOMALIA
                            + " (payload, grp, segregador) VALUES (?, ?, ?)",
                            ("c5-" + str(_random_seg.randint(1, 10 ** 6)),
                             _random_seg.randint(0, 99), _random_seg.randint(0, 10 ** 9)),
                        )
                    cur.execute("COMMIT")
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
            conn.close()
        except Exception:
            pass

    hilos = [threading.Thread(target=worker, daemon=True) for _ in range(8)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    log("fault5: commits altamente concurrentes")


def _fase_fault3_cpu(duracion):
    fin = time.time() + duracion

    def worker():
        try:
            conn = _conectar(autocommit=True)
            cur = conn.cursor()
            while time.time() < fin:
                cur.execute("SET NOCOUNT ON; DECLARE @i BIGINT = 0; "
                            "WHILE @i < 3000000 SET @i = @i + 1")
                cur.fetchall()
                cur.execute(
                    "SELECT g.grp, COUNT(*), SUM(s.segregador % 97) "
                    "FROM " + SCRATCH_ANOMALIA + " g "
                    "CROSS JOIN (SELECT TOP (20) * FROM " + SCRATCH_ANOMALIA + ") j "
                    "GROUP BY g.grp")
                cur.fetchall()
            conn.close()
        except Exception:
            pass

    hilos = [threading.Thread(target=worker, daemon=True) for _ in range(5)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    log("fault3: loops CPU y agregados pesados")


FASES = {
    "normal":    {"nombre": "normal",    "fn": _fase_normal},
    "lockwait":  {"nombre": "lockwait",  "fn": _fase_lockwait},
    "fault1":    {"nombre": "fault1",    "fn": _fase_fault1_log_writes},
    "fault2":    {"nombre": "fault2",    "fn": _fase_fault2_full_scan},
    "fault3":    {"nombre": "fault3",    "fn": _fase_fault3_cpu},
    "fault5":    {"nombre": "fault5",    "fn": _fase_fault5_commits},
}


# ----------------------------------------------------------------------
# Orquesta la secuencia y graba el ground truth
# ----------------------------------------------------------------------

def construir_secuencia(duracion, faults):
    """Alterna normal/fault: normal0, fault1, normal, fault2, ... normal."""
    seg = duracion / (2 * len(faults) + 1)
    secuencia = [("normal", seg)]
    for f in faults:
        secuencia.append((f, seg))
        secuencia.append(("normal", seg))
    return secuencia


def main():
    ap = argparse.ArgumentParser(
        description="Inyecta anomalias de rendimiento reales en el SQL de negocio"
    )
    ap.add_argument("--duracion", type=int, default=180, help="segundos totales")
    ap.add_argument("--faults", default="lockwait,fault1,fault2,fault5,fault3",
                    help="lista de fallos separada por comas (en orden)")
    ap.add_argument("--corrida", default="carga5",
                    help="nombre de la corrida para el ground truth")
    ap.add_argument("--output-root", default=None,
                    help="raiz donde se guardan las corridas "
                         "(def: STEELNORT_OUTPUT_DIR o backend/training/output)")
    ap.add_argument("--solo-setup", action="store_true",
                    help="solo prepara anomalia_scratch y sale")
    args = ap.parse_args()

    faults = [f.strip().lower() for f in args.faults.split(",") if f.strip()]
    for f in faults:
        if f not in FASES:
            log(f"ERROR: fault desconocido '{f}'. Validos: "
                f"{', '.join(sorted(FASES))}")
            sys.exit(2)

    if args.output_root:
        output_root = args.output_root
    elif os.getenv("STEELNORT_OUTPUT_DIR"):
        output_root = os.getenv("STEELNORT_OUTPUT_DIR")
    else:
        output_root = str(
            Path(BACKEND_ROOT) / "training" / "output"
        )

    corrida_dir = os.path.join(output_root, args.corrida)
    os.makedirs(corrida_dir, exist_ok=True)

    limpiar_sesiones()
    _asegurar_scratch_anomalia()

    if args.solo_setup:
        log("Setup anomalia_scratch completado.")
        return

    secuencia = construir_secuencia(args.duracion, faults)

    log(f"Simulacion: {args.duracion}s, fallos={faults}, corrida={args.corrida}")
    log(f"Secuencia (fases): {[(f, int(d)) for f, d in secuencia]}")

    timeline = []
    inicio_global = None
    for fase, dur in secuencia:
        ahora = datetime.now()
        if inicio_global is None:
            inicio_global = ahora
        log(f"fase {fase}: {ahora.strftime('%H:%M:%S')} "
            f"({int(dur)}s planeados)")
        fn = FASES[fase]["fn"]
        resultado = {}
        def _runner():
            try:
                fn(dur)
            except Exception as e:
                resultado["error"] = e
        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()
        fin_fase = datetime.now()   # hora REAL de fin (alineado al reloj del collector)
        if resultado.get("error"):
            log(f"fase {fase}: ERROR interno ({resultado['error']})")
        if fase != "normal":
            timeline.append({
                "tipo": fase,
                "inicio": ahora.strftime("%Y-%m-%d %H:%M:%S"),
                "fin": fin_fase.strftime("%Y-%m-%d %H:%M:%S"),
            })
        log(f"fase {fase}: terminada a las {fin_fase.strftime('%H:%M:%S')}")

    # Ground truth
    ruta_timeline = os.path.join(corrida_dir, "anomalias_timeline.csv")
    with open(ruta_timeline, "w", encoding="utf-8") as f:
        f.write("tipo,inicio,fin\n")
        for r in timeline:
            f.write(f"{r['tipo']},{r['inicio']},{r['fin']}\n")
    log(f"Ground truth escrito: {ruta_timeline}")

    descripcion = {
        "corrida": args.corrida,
        "inicio": inicio_global.strftime("%Y-%m-%d %H:%M:%S"),
        "duracion_total_s": args.duracion,
        "faults": faults,
        "secuencia": [{"fase": f, "segundos": int(d)} for f, d in secuencia],
        "timeline": timeline,
        "motor": "SQL Server Podman (localhost:1434/SteelNort)",
        "nota": "fases intercaladas normal/fault; el ground truth se expresa "
                "en el reloj local del collector",
    }
    ruta_desc = os.path.join(corrida_dir, "descripcion_simulacion.json")
    with open(ruta_desc, "w", encoding="utf-8") as f:
        json.dump(descripcion, f, ensure_ascii=False, indent=2)
    log(f"Descripcion escrita: {ruta_desc}")

    limpiar_sesiones()
    log("Inyeccion completada. Los collectors debieron capturar la corrida.")


if __name__ == "__main__":
    main()