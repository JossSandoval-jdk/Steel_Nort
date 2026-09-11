# FastAPI router para exponer el diagnóstico de anomalías generado por el pipeline.
# Este endpoint devuelve el JSON completo de `informe_deteccion.json`.

from __future__ import annotations

from fastapi import APIRouter
# from fastapi import Depends
# from app.routers.auth import get_current_user
from fastapi.responses import JSONResponse
import json
import os

# JWT authentication dependency
from app.routers.auth import get_current_user

# Importamos la configuración del módulo de modelado donde se define DIR_MODELADO
from app.training.nucleo.modeling import config as modeling_config

router = APIRouter(prefix="/anomalias", tags=["anomalias"])

@router.get("/diagnostico")
def get_diagnostico():
    """Retorna el último informe de detección generado.

    El script `05_diagnostico_resultados.py` escribe el archivo JSON en
    `modeling_config.DIR_MODELADO / "diagnostico/informe_deteccion.json"`.
    Si el archivo no existe se devuelve un error 404.
    """
    ruta_json = os.path.join(modeling_config.DIR_MODELADO, "diagnostico", "informe_deteccion.json")
    if not os.path.exists(ruta_json):
        return JSONResponse(status_code=404, content={"detail": "Informe de detección no disponible"})
    with open(ruta_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(content=data)
