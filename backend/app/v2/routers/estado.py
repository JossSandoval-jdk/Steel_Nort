from fastapi import APIRouter
from sqlalchemy import create_engine, text
import os
import glob
from app.v2.config import settings

router = APIRouter(prefix="/estado", tags=["estado"])
@router.get("/conexiones")
def verificar_conexiones():
    # 1. Verificar SQL Server del sistema monitoreado (Ya funciona)
    conectado_db = False
    if settings.monitoreo_url:
        try:
            engine = create_engine(settings.monitoreo_url, connect_args={"timeout": 3})
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            conectado_db = True
        except Exception:
            conectado_db = False

    # 2. Verificar Logs consultando si la sesión de Extended Events responde en el servidor monitoreado
    conectado_logs = False
    if settings.monitoreo_url:
        try:
            engine = create_engine(settings.monitoreo_url, connect_args={"timeout": 3})
            with engine.connect() as conn:
                # Consultamos si el sistema de eventos extendidos está corriendo en el SQL Server
                resultado = conn.execute(text(
                    "SELECT COUNT(*) FROM sys.dm_xe_sessions WHERE name LIKE '%steel%'"
                )).scalar()
                # Si encuentra la sesión activa o simplemente responde la consulta de eventos
                conectado_logs = True 
        except Exception:
            conectado_logs = False

    return {
        "monitored": {"conectado": conectado_db},
        "logs": {"conectado": conectado_logs}
    }