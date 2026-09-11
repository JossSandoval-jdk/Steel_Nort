"""Generador de carga de trabajo REAL sobre el SQL Server de negocio (VPS/Podman).

A diferencia de ``tools/simular_carga.py`` (que inyecta muestras sinteticas
directo a la API web y nunca toca el motor), este script ejecuta actividad
T-SQL real contra ``SQL_HOST:SQL_PORT`` (el SQL Server de Podman en ``1434``
que simula el VPS):

    - SELECTs sobre tablas de negocio (lecturas + S-locks)
    - INSERTs / UPDATEs sobre una tabla scratch (transacciones + writes)
    - transacciones explicitas con COMMIT (transactions/sec)

Como la actividad es real DENTRO del motor, los colectores la capturan:

    - ``log_event_collector``  -> events.log + sqlserver_logs.log
    - ``xe_collector``         -> events_xe.log (SQL batches, lentos, etc.)
    - ``metrics_collector``    -> metrics.log (DMVs y contadores)
    - ``stream_daemon``        -> publica la carga en vivo a la web

Sesiones identificadas con APP=SteelNortCargaNormal para poder KILL de las
huerfanas al terminar (``limpiar_sesiones``).

Uso:
    python tools/generar_carga.py --duracion 120 --workers 10 [--retardo 0.02]

(mientras corre, mantenga prendidos el backend y el/los collectors).
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import threading
import time
from pathlib import Path

# Asegura que la raiz del backend este en sys.path (para app.collector.config).
BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import pyodbc  # noqa: E402

from app.collector.config import SQL_SERVER_CONN_STR  # noqa: E402

# Identificador de sesion: permite limpiar huerfanas sin tocar otras.
NOMBRE_SESION = "SteelNortCargaNormal"

# Tabla scratch de la carga normal (nunca toca datos de negocio).
SCRATCH = "dbo.carga_normal_scratch"

_lock_registro = threading.Lock()
_spids_activos: set[int] = set()


def log(msg):
    print(f"[CARGA-NORMAL] {msg}", flush=True)


def _cadena_conexion():
    if "APP=" in SQL_SERVER_CONN_STR:
        return SQL_SERVER_CONN_STR
    return SQL_SERVER_CONN_STR + "APP=" + NOMBRE_SESION + ";"


def _crear_conexion():
    conn = pyodbc.connect(_cadena_conexion(), autocommit=False)
    try:
        cur = conn.cursor()
        cur.execute("SELECT @@SPID")
        with _lock_registro:
            _spids_activos.add(int(cur.fetchval()))
    except Exception:
        pass
    return conn


def _cerrar_conexion(conn):
    if conn is None:
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT @@SPID")
        with _lock_registro:
            _spids_activos.discard(int(cur.fetchval()))
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass


def limpiar_sesiones():
    """KILL de cualquier sesion de la carga normal que haya quedado huerfana."""
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
        with _lock_registro:
            _spids_activos.clear()
    except Exception:
        pass


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


def _asegurar_scratch():
    """Crea (si no existe) y rellena la tabla scratch de la carga normal."""
    _aplicar_sql(
        "IF OBJECT_ID('" + SCRATCH + "','U') IS NULL "
        "CREATE TABLE " + SCRATCH + " ("
        "id INT IDENTITY(1,1) PRIMARY KEY, "
        "payload VARCHAR(200) NOT NULL, "
        "ts DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME());"
    )
    try:
        conn = pyodbc.connect(SQL_SERVER_CONN_STR, autocommit=True)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM " + SCRATCH)
        n = int(cur.fetchval() or 0)
        conn.close()
    except Exception:
        n = -1
    if n < 500:
        _aplicar_sql(
            "SET NOCOUNT ON; "
            "DELETE FROM " + SCRATCH + " WITH (TABLOCK); "
            ";WITH cte AS (SELECT TOP (500) ROW_NUMBER() OVER "
            "(ORDER BY (SELECT NULL)) AS n FROM sys.all_objects a "
            "CROSS JOIN sys.all_objects b) "
            "INSERT INTO " + SCRATCH + " (payload) "
            "SELECT 'carga-normal-' + CONVERT(varchar(10), n) FROM cte;"
        )


# ---------------------------------------------------------------------------
# Operaciones "normales" (lectura real de tablas de negocio del VPS).
# ---------------------------------------------------------------------------

SQL_SELECTS = [
    "SELECT TOP (50) p.pro_cod, p.pro_nom, p.pro_pre_venta, i.inv_cant "
    "FROM producto p LEFT JOIN inventario i ON i.pro_cod = p.pro_cod "
    "WHERE p.pro_est = 'A' OPTION (RECOMPILE);",
    "SELECT TOP (100) k.kar_cod, k.pro_cod, k.kar_fec, k.kar_cant, k.kar_tip_mov "
    "FROM kardex k ORDER BY k.kar_cod DESC OPTION (RECOMPILE);",
    "SELECT TOP (100) v.ven_cod, v.cli_cod, v.ven_fec, v.ven_est, v.ven_total, "
    "a.alm_nom FROM venta v JOIN almacen a ON a.alm_cod = v.alm_cod "
    "ORDER BY v.ven_cod DESC OPTION (RECOMPILE);",
    "SELECT v.ven_est, COUNT(*) AS n, SUM(v.ven_total) AS total "
    "FROM venta v WHERE v.ven_fec >= DATEADD(day, -30, GETDATE()) "
    "GROUP BY v.ven_est OPTION (RECOMPILE);",
    "SELECT TOP (200) dv.dve_cod, dv.ven_cod, dv.pro_cod, dv.dve_cant, "
    "dv.dve_pre_uni FROM detalle_venta dv WHERE dv.ven_cod > 0 "
    "ORDER BY dv.dve_cod DESC OPTION (RECOMPILE);",
    "SELECT TOP (50) i.inv_cod, i.pro_cod, i.alm_cod, i.inv_cant, p.pro_nom "
    "FROM inventario i JOIN producto p ON p.pro_cod = i.pro_cod "
    "ORDER BY i.inv_cod DESC OPTION (RECOMPILE);",
]


def _op_select(cur):
    cur.execute(random.choice(SQL_SELECTS))
    cur.fetchall()


def _op_insert(cur):
    cur.execute(
        "INSERT INTO " + SCRATCH + " (payload) VALUES (?)",
        ("carga-" + str(random.randint(1, 10 ** 6)),),
    )


def _op_update(cur):
    cur.execute(
        "UPDATE " + SCRATCH + " SET ts = SYSUTCDATETIME() "
        "WHERE id = (SELECT TOP (1) id FROM " + SCRATCH + " ORDER BY NEWID());"
    )


def _op_transaccion(cur):
    cur.execute("BEGIN TRAN;")
    cur.execute(
        "UPDATE " + SCRATCH + " SET ts = SYSUTCDATETIME() "
        "WHERE id = (SELECT TOP (1) id FROM " + SCRATCH + " ORDER BY NEWID());"
    )
    cur.execute("COMMIT;")


OPERACIONES = [
    (_op_select, 40),
    (_op_select, 20),
    (_op_insert, 15),
    (_op_update, 15),
    (_op_transaccion, 10),
]


def _operacion_ponderada():
    total = sum(w for _, w in OPERACIONES)
    r = random.uniform(0, total)
    acum = 0
    for fn, w in OPERACIONES:
        acum += w
        if r <= acum:
            return fn
    return OPERACIONES[-1][0]


def _worker_loop(worker_id, duracion, retardo_max):
    conn = _crear_conexion()
    cur = conn.cursor()
    fin = time.time() + duracion
    n_ops = 0
    try:
        while time.time() < fin:
            op = _operacion_ponderada()
            try:
                op(cur)
                conn.commit()
                n_ops += 1
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
            if retardo_max > 0:
                time.sleep(random.uniform(0, retardo_max))
    finally:
        _cerrar_conexion(conn)
    log(f"Worker {worker_id} termino ({n_ops} ops)")


def main():
    ap = argparse.ArgumentParser(
        description="Carga normal T-SQL real al SQL de negocio (VPS/Podman)"
    )
    ap.add_argument("--duracion", type=int, default=120, help="segundos de carga")
    ap.add_argument("--workers", type=int, default=10, help="hilos concurrentes")
    ap.add_argument("--retardo", type=float, default=0.02,
                    help="espera aleatoria (s) entre operaciones; 0 = sin espera")
    args = ap.parse_args()

    limpiar_sesiones()
    _asegurar_scratch()

    destino = SQL_SERVER_CONN_STR.split(";")[1]
    log(f"Duración {args.duracion}s, {args.workers} workers, destino {destino}")
    log("Carga normal T-SQL directa sobre el VPS (sin tocar datos de negocio)")

    hilos = [
        threading.Thread(
            target=_worker_loop,
            args=(i + 1, args.duracion, args.retardo),
            daemon=True,
        )
        for i in range(max(1, args.workers))
    ]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()

    limpiar_sesiones()
    log("Carga normal completada. Los collectors debieron capturar metricas/logs/eventos.")


if __name__ == "__main__":
    main()