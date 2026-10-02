"""Punto de entrada de la API v2 (SteelNort).

Arranque:
  1. comprueba que la base ``bdSteelNort_v2`` tiene las 21 tablas del script canonico;
  2. siembra roles, permisos y el administrador inicial (idempotente);
  3. monta los siete routers bajo el prefijo ``/api/v2``.

Se ejecuta con:  uvicorn app.v2.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text

from app.v2.config import settings
from app.v2.database import SessionLocal, init_db, verificar_esquema, version_bd
from app.v2.models.acceso import Usuario
from app.v2.routers import acceso, auth, datos, deteccion, modelo, nodos, sistema
from app.v2.schemas.comun import Salud
from app.v2.services import semilla
from app.v2.routers import estado
from app.v2.routers import telemetria
from app.ml.detector import get_detector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("steelnort.v2")

# Las 21 tablas del esquema canonico que expone esta API.
TABLAS = (
    "rol",
    "permiso",
    "usuario",
    "rol_permiso",
    "sesiones",
    "instancias",
    "sesiones_sql",
    "modelos_ml",
    "predicciones_ml",
    "deriva_monitor",
    "reentrenamiento",
    "reentrenamiento_paso",
    "alertas",
    "alerta_variable",
    "causas_raiz",
    "heatmap_anomalias",
    "metricas",
    "eventos",
    "logs_sql",
    "estadisticas_carga",
    "configuracion_sistema",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Comprueba el esquema y deja los roles y permisos sembrados.

    El usuario administrador no se crea aqui: se crea una sola vez con
    ``python crear_admin_v2.py``, que pregunta los datos al operador.
    """
    log.info("Conectando a %s", settings.database_url.split("@")[-1])
    init_db()
    presentes, _ = verificar_esquema()
    log.info("Esquema verificado: %d/%d tablas. SQL Server %s", len(presentes), len(TABLAS), version_bd())
    with SessionLocal() as db:
        semilla.sembrar(db)
    if db.scalar(select(func.count()).select_from(Usuario)) == 0:
        log.warning("No hay ningun usuario. Ejecute 'python crear_admin_v2.py' para crear el administrador.")
    yield


app = FastAPI(
    title=settings.titulo,
    version=settings.version,
    description=f"API de SteelNort sobre la base `{settings.nombre_base}` (21 tablas).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=1800,
)

API = "/api/v2"
app.include_router(auth.router, prefix=API)
app.include_router(acceso.router, prefix=API)
app.include_router(nodos.router, prefix=API)
app.include_router(modelo.router, prefix=API)
app.include_router(deteccion.router, prefix=API)
app.include_router(datos.router, prefix=API)
app.include_router(sistema.router, prefix=API)
app.include_router(estado.router, prefix=API)
app.include_router(telemetria.router, prefix=API)

@app.get(f"{API}/salud", response_model=Salud, tags=["sistema"], summary="Estado de la API")
def salud() -> Salud:
    """Comprueba tambien que la base responde."""
    presentes, faltantes = verificar_esquema()
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return Salud(
        app=settings.titulo,
        version=settings.version,
        base=settings.nombre_base,
        servidor=version_bd(),
        tablas_ok=len(presentes),
        tablas_faltantes=faltantes,
    )

@app.on_event("startup")
def startup_event():
    # Precarga los modelos ML en memoria al arrancar el servidor
    get_detector()
    print("Modelos de Machine Learning cargados correctamente.")