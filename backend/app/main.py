"""Punto de entrada de la aplicacion FastAPI SteelNort.

Inicializa los componentes centrales al arrancar:
  - recursos de base de datos (tablas si faltan),
  - CORS para el frontend,
  - registro de rutas (de momento solo autenticacion).

Para escalar: conforme se agreguen modulos (alertas, reportes, ML,
CRUD de nodos, etc.), se crean nuevos routers en ``app/routers`` y se
registran aqui con ``app.include_router(...)``.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Asegura que el directorio raiz del backend (padre de ``app``) este en
# sys.path. Esto permite ejecutar ``python app/main.py`` directamente
# ademas de ``uvicorn app.main:app`` (que ya lo inyecta por ser modulo).
BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

log = logging.getLogger("steelnort.main")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import SessionLocal, init_db
from app.routers import auth, dashboard, dominio, metricas, reentrenamiento, roles, telemetria, usuarios
from app.services.seed_roles import seed_roles_y_permisos
from app.services.sincronizacion import start_monitor, stop_monitor

# ==============================================================================
# LIFESPAN: Gestiona el ciclo de vida de la aplicación.
# Se encarga de inicializar la base de datos al arrancar el servidor.
# ==============================================================================
def _resumen_vps_sql() -> list[str]:
    """Estado de la conexion al SQL Server de negocio (Podman/VPS 1434).

    Prueba la conexion con las credenciales del collector y lee las
    ultimas lineas del error log para demostrar que la fuente de logs
    esta conectada.
    """
    from app.services.sincronizacion import _test_vps_sql

    ok = _test_vps_sql()
    lineas = ["  SQL Podman (VPS) : 127.0.0.1:1434  [CONECTADO]" if ok
              else "  SQL Podman (VPS) : 127.0.0.1:1434  [OFFLINE]"]

    if ok:
        lineas.append("  Logs del VPS       : errorlog de SQL Server (ultimas lineas):")
        try:
            from app.collector.config import SQL_SERVER_CONN_STR
            import pyodbc  # noqa: PLC0415

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


def _reporte_arranque(detect, mdl, nodos_lista, db_nombre) -> str:
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Ejecuta tareas de inicializacion al arrancar la API.

    Al prender el backend se prepara TODO el sistema:
      1. Crea/se verifica las tablas de la BD (init_db) y comprueba la conexion.
      2. Siembra roles y permisos por defecto.
      3. Carga el detector ML (modelo + scaler + umbrales).
         Si falta un artefacto, el backend FALLA al arrancar (fail-fast).
      4. Registra el modelo desplegado en Modelos_ML y muestra el resumen:
         nodos SCADA reconocidos, umbrales y conexion -> verificables en logs.
    """
    init_db()
    db = SessionLocal()
    try:
        # 2. Roles y permisos por defecto.
        seed_roles_y_permisos(db)

        # 3. Carga eager del detector: si no existe -> arranque aborted.
        from app.ml.detector import get_detector
        detect = get_detector()

        # 4. Mirror del detector en Modelos_ML (auto-registro si falta).
        from app.services.anomalias import obtener_modelo_activo
        mdl = obtener_modelo_activo(db)

        # 5. Nodos SCADA reconocidos actualmente en la BD.
        from app.models.model_scada import NodosSCADA
        nodos = (
            db.query(NodosSCADA)
            .filter(NodosSCADA.fec_eli.is_(None))
            .order_by(NodosSCADA.ndo_nom)
            .all()
        )
        db.commit()

        db_nombre = (settings.database_url.split("?", 1)[0]
                     .replace("mssql+pyodbc://", ""))
        reporte = _reporte_arranque(detect, mdl, nodos, db_nombre)
        log.info("\n%s", reporte)
        print("\n" + reporte)  # garantiza visibilidad en la consola de uvicorn
    finally:
        db.close()
    # 6. Monitor de sincronizacion: vigila VPS SQL + daemon/web y alerta.
    start_monitor()
    yield
    stop_monitor()

# ==============================================================================
# FASTAPI APP: Instancia principal de la API.
# Configura el título, versión y middleware CORS para comunicación con el frontend.
# ==============================================================================
app = FastAPI(
    title="SteelNort API",
    description="API del sistema SCADA de monitoreo y deteccion de anomalias.",
    version="0.1.0",
    lifespan=lifespan,
)

# Configuracion CORS: permite al frontend React consumir la API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# ROUTERS: Registro de los módulos funcionales de la aplicación.
# - auth: Autenticación y seguridad.
# - metricas: Datos de sensores y sistemas.
# - usuarios: Gestión de cuentas.
# - dominio: Lógica de negocio específica de la planta.
# ==============================================================================
app.include_router(auth.router)
app.include_router(metricas.router)
app.include_router(usuarios.router)
app.include_router(roles.router)
app.include_router(dominio.router)
app.include_router(telemetria.router)
app.include_router(dashboard.router)
app.include_router(reentrenamiento.router)


@app.get("/")
def root() -> dict:
    """Ruta base para verificar que la API esta viva."""
    return {"app": "SteelNort API", "status": "ok", "version": "0.1.0"}