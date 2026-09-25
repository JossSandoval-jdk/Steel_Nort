"""Punto de entrada de la aplicacion FastAPI SteelNort.

Inicializa los componentes centrales al arrancar:
  - tablas de la base de datos (si faltan),
  - roles y permisos por defecto,
  - detector ML (fail-fast si faltan artefactos),
  - monitor de sincronizacion VPS/daemon,
  - CORS, middlewares transversales y routers.
"""

from __future__ import annotations

import logging
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

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.middleware import (  # noqa: E402
    ModelProtectionMiddleware,
    ProxyHeadersMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from app.routers import (  # noqa: E402
    anomalias,
    auth,
    dashboard,
    dominio,
    drift,
    metricas,
    reentrenamiento,
    roles,
    telemetria,
    usuarios,
)
from app.services.seed_roles import seed_roles_y_permisos  # noqa: E402
from app.services.sincronizacion import start_monitor, stop_monitor  # noqa: E402
from app.services.drift import (  # noqa: E402
    start_drift_monitor,
    stop_drift_monitor,
)
from app.startup import _reporte_arranque, nombre_bd_visible  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Ejecuta tareas de inicializacion al arrancar la API.

    1. Crea/verifica las tablas (init_db) y comprueba la conexion.
    2. Siembra roles y permisos por defecto.
    3. Carga el detector ML (modelo + scaler + umbrales) con fail-fast.
    4. Registra el modelo desplegado en Modelos_ML.
    5. Lee los nodos SCADA reconocidos y muestra el resumen de arranque.
    6. Arranca el monitor de sincronizacion (VPS SQL + daemon).
    """
    init_db()
    db = SessionLocal()
    try:
        seed_roles_y_permisos(db)

        from app.ml.detector import get_detector
        detect = get_detector()

        from app.services.anomalias import obtener_modelo_activo
        mdl = obtener_modelo_activo(db)

        from app.models.model_scada import NodosSCADA
        nodos = (
            db.query(NodosSCADA)
            .filter(NodosSCADA.fec_eli.is_(None))
            .order_by(NodosSCADA.ndo_nom)
            .all()
        )
        db.commit()

        reporte = _reporte_arranque(detect, mdl, nodos, nombre_bd_visible())
        log.info("\n%s", reporte)
        print("\n" + reporte)  # garantiza visibilidad en la consola de uvicorn
    finally:
        db.close()

    start_monitor()
    start_drift_monitor()
    yield
    stop_drift_monitor()
    stop_monitor()


def crear_app() -> FastAPI:
    """Construye la instancia FastAPI con middlewares y routers."""
    app = FastAPI(
        title="SteelNort API",
        description="API del sistema SCADA de monitoreo y deteccion de anomalias.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Middlewares (orden: la ultima add_middleware queda MS externo).
    #
    # Flujo del request:
    #   ProxyHeaders -> CORS -> RequestLogging -> RateLimit
    #     -> ModelProtection -> SecurityHeaders -> app
    # ------------------------------------------------------------------
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ModelProtectionMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ProxyHeadersMiddleware)

    # ------------------------------------------------------------------
    # Routers: modulos funcionales de la aplicacion.
    # ------------------------------------------------------------------
    app.include_router(auth.router)
    app.include_router(metricas.router)
    app.include_router(usuarios.router)
    app.include_router(roles.router)
    app.include_router(dominio.router)
    app.include_router(telemetria.router)
    app.include_router(dashboard.router)
    app.include_router(anomalias.router)
    app.include_router(reentrenamiento.router)
    app.include_router(drift.router)

    @app.get("/")
    def root() -> dict:
        """Ruta base para verificar que la API esta viva."""
        return {"app": "SteelNort API", "status": "ok", "version": "0.1.0"}

    return app


# Instancia de la aplicacion (usada por uvicorn app.main:app).
app = crear_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8123, reload=False)