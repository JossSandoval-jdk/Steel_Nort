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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import auth, dominio, metricas, usuarios

# ==============================================================================
# LIFESPAN: Gestiona el ciclo de vida de la aplicación.
# Se encarga de inicializar la base de datos al arrancar el servidor.
# ==============================================================================
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Ejecuta tareas de inicializacion al arrancar la API."""
    init_db()
    yield

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
app.include_router(dominio.router)


@app.get("/")
def root() -> dict:
    """Ruta base para verificar que la API esta viva."""
    return {"app": "SteelNort API", "status": "ok", "version": "0.1.0"}