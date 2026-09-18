"""Router para exponer el diagnostico de anomalias generado por el pipeline.

Devuelve el JSON completo de ``informe_deteccion.json`` producido por
``05_diagnostico_resultados.py`` (acceso restringido a usuarios autenticados).
"""

from __future__ import annotations

import json
import os
from typing import Annotated

from fastapi import APIRouter, Depends

from app.routers.auth import get_current_user

router = APIRouter(prefix="/anomalias", tags=["anomalias"])

UsuarioActual = Annotated[object, Depends(get_current_user)]


@router.get("/diagnostico")
def get_diagnostico(_current: UsuarioActual):
    """Retorna el ultimo informe de deteccion generado.

    El script ``05_diagnostico_resultados.py`` escribe el archivo JSON en
    ``DIR_MODELADO / "diagnostico/informe_deteccion.json"``. Si el archivo
    no existe se devuelve un error 404.
    """
    # Importacion perezosa: evita fallos de arranque si el pipeline de
    # entrenamiento aun no genera este directorio.
    from training.nucleo.modeling import config as modeling_config

    ruta_json = os.path.join(
        modeling_config.DIR_MODELADO, "diagnostico", "informe_deteccion.json"
    )
    if not os.path.exists(ruta_json):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=404, content={"detail": "Informe de deteccion no disponible"}
        )
    with open(ruta_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    from fastapi.responses import JSONResponse

    return JSONResponse(content=data)