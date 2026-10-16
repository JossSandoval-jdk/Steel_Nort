"""Conteo READ-ONLY de la BD de negocio (indica I-1.1, volumen extraido).

Solo ejecuta SELECT/COUNT y xp_readerrorlog; NO escribe nada en la BD.
Fuentes segun Objetivos_y_requisitos.md I-1.1: tablas de negocio,
DMVs (snapshot), Query Store y Error Log.

Salida: training/output/inventario/bd_conteos.csv
Uso:   python tools/inventario_bd.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--salida",
        default=str(BACKEND_ROOT / "training" / "output" / "inventario"
                    / "bd_conteos.csv"),
    )
    args = ap.parse_args()

    import pyodbc
    from app.collector.config import SQL_SERVER_CONN_STR

    conn = pyodbc.connect(SQL_SERVER_CONN_STR, timeout=10, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT @@SERVERNAME, DB_NAME()")
    servidor, base = cur.fetchone()
    print(f"Servidor: {servidor} | Base: {base}")

    filas: list[dict] = []

    def contar(fuente: str, nombre: str, sql: str) -> None:
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            if len(rows) == 1 and isinstance(rows[0][0], int):
                n = rows[0][0]           # SELECT COUNT(...)
            else:
                n = len(rows)            # TVF/EXEC con N filas (error log)
            filas.append({"fuente": fuente, "objeto": nombre,
                          "registros": int(n)})
            print(f"  {fuente:14s} {nombre:45s} {n}")
        except Exception as exc:
            filas.append({"fuente": fuente, "objeto": nombre,
                          "registros": None})
            print(f"  {fuente:14s} {nombre:45s} N/D ({exc})")

    # Tablas de negocio (persistidas)
    cur.execute(
        "SELECT s.name + '.' + t.name FROM sys.tables t "
        "JOIN sys.schemas s ON t.schema_id = s.schema_id "
        "ORDER BY s.name, t.name"
    )
    tablas = [r[0] for r in cur.fetchall()]
    for tq in tablas:
        contar("tabla_negocio", tq, f"SELECT COUNT_BIG(*) FROM {tq}")

    # DMV (snapshot; volatil por definicion)
    contar("dmv", "sys.dm_exec_query_stats",
           "SELECT COUNT(*) FROM sys.dm_exec_query_stats")
    contar("dmv", "sys.dm_os_wait_stats",
           "SELECT COUNT(*) FROM sys.dm_os_wait_stats")

    # Query Store
    contar("query_store", "sys.query_store_runtime_stats",
           "SELECT COUNT(*) FROM sys.query_store_runtime_stats")

    # Error Log (read-only; xp_readerrorlog devuelve una fila por linea)
    contar("error_log", "xp_readerrorlog(0,1)",
           "EXEC xp_readerrorlog 0, 1")

    conn.close()

    total = sum(f["registros"] for f in filas
                if isinstance(f["registros"], int))
    filas.append({"fuente": "(total)", "objeto": "(todas las fuentes)",
                  "registros": total})

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with open(salida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, ["fuente", "objeto", "registros"])
        w.writeheader()
        w.writerows(filas)
    print(f"\nI-1.1 conteo total: {total} registros en "
          f"{len(tablas)} tablas de negocio")
    print(f"Servidor={servidor} base={base} "
          f"fecha={datetime.now().isoformat(timespec='seconds')}")
    print(f"Salida: {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
