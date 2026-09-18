"""Reporte de arranque del backend SteelNort.

Compone el resumen visible en consola cuando el servidor queda listo:
estado de la conexion SQL (VPS + errorlog), modelo activo, umbrales y
nodos reconocidos.
"""

from __future__ import annotations

import pyodbc  # noqa: PLC0415

from app.config import settings


def _resumen_vps_sql() -> list[str]:
    """Estado de la conexion al SQL Server de negocio (Podman/VPS 1434)."""
    from app.services.sincronizacion import _test_vps_sql

    ok = _test_vps_sql()
    lineas = [
        "  SQL Podman (VPS) : 127.0.0.1:1434  [CONECTADO]" if ok
        else "  SQL Podman (VPS) : 127.0.0.1:1434  [OFFLINE]"
    ]

    if ok:
        lineas.append("  Logs del VPS       : errorlog de SQL Server (ultimas lineas):")
        try:
            from app.collector.config import SQL_SERVER_CONN_STR

            conn = pyodbc.connect(SQL_SERVER_CONN_STR, timeout=5, autocommit=True)
            try:
                cur = conn.cursor()
                cur.execute("EXEC sp_readerrorlog 0")
                for row in cur.fetchmany(3):
                    texto = " ".join(str(row[2]).split())
                    lineas.append(f"      - {texto[:100]}")
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as exc:
            lineas.append(f"      (no se pudo leer el errorlog: {exc})")
    return lineas


def _reporte_arranque(detect, mdl, nodos_lista, db_nombre: str) -> str:
    """Compone el resumen visible cuando el backend queda listo."""
    nodos = nodos_lista or []
    linea_nodos = (
        ", ".join(f"{n.ndo_nom} ({n.ndo_ip})" for n in nodos)
        if nodos else "(sin nodos registrados; se auto-registran al recibir telemetria)"
    )
    umbral = detect.umbral_actual
    return "\n".join([
        "=" * 76,
        "  STEELNORT  |  SISTEMA PRENDIDO  |  SCADA + ML",
        "=" * 76,
        f"  Base de datos     : {db_nombre}  [CONECTADO]",
        *_resumen_vps_sql(),
        f"  Modelo registrado : {getattr(mdl, 'mdl_nom', 'n/a')}  (mdl_cod={getattr(mdl, 'mdl_cod', '?')})",
        "  Detector ML       : Isolation Forest",
        f"  Ventana           : {detect._ventana} muestras",
        f"  Features          : {len(detect._features21)}  ->  {', '.join(detect._features21)}",
        f"  Umbral activo     : {detect._umbral_nombre} = {umbral}",
        f"  Umbrales q10/q05/q01: {detect._umbrales.get('q10')} / {detect._umbrales.get('q05')} / {detect._umbrales.get('q01')}",
        f"  Artefacto modelo  : {detect._ruta_modelo}",
        f"  Nodos reconocidos : {linea_nodos}",
        "=" * 76,
        "  Endpoints: /  |  telemetria en /telemetria  |  SSE en /telemetria/live",
        "  Validar modelo:  python tools/simular_carga.py",
        "=" * 76,
    ])


def nombre_bd_visible() -> str:
    """Nombre legible de la BD activa a partir de ``settings.database_url``."""
    return (settings.database_url.split("?", 1)[0]
            .replace("mssql+pyodbc://", ""))