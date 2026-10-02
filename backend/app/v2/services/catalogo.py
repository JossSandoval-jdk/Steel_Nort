"""Las dos filas que hay que tener antes de poder escribir una prediccion.

``predicciones_ml`` tiene dos claves foraneas: el modelo (``prd_mdl``) y el nodo
 (``prd_ins``). Ademas el trigger ``TR_prd_instancia_valida`` rechaza cualquier
ventana que empiece antes de ``instancias.ins_fec_alta``.

Ningun endpoint expone todavia el alta de esas dos filas, asi que se resuelven
solas la primera vez que llega telemetria: son datos que el backend ya conoce
(que artefactos cargo, que nodo esta empujando).
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.ml.detector import ML_ARTIFACTS, get_detector
from app.utils import utc_now
from app.v2.models.modelo import ModeloML
from app.v2.models.nodos import Instancia

log = logging.getLogger("steelnort.v2.catalogo")

# El collector manda host pero no puerto; 1433 es el de SQL Server por defecto.
PUERTO_POR_DEFECTO = 1433

# ``modelos_ml.mdl_cuantil`` guarda el punto operativo como cuantil.
CUANTIL_POR_UMBRAL = {"q10": 0.100, "q05": 0.050, "q01": 0.010}


def instancia(db: Session, nombre: str, host: str, desde) -> Instancia:
    """Nodo vigilado, buscandolo por su clave natural ``(host, puerto)``.

    ``desde`` es el inicio de la primera ventana evaluada: se usa como
    ``ins_fec_alta`` para no chocar con el trigger, que prohibe ventanas
    anteriores al alta del nodo.
    """
    fila = db.query(Instancia).filter(
        Instancia.ins_host == host,
        Instancia.ins_puerto == PUERTO_POR_DEFECTO,
    ).first()
    if fila:
        return fila

    fila = Instancia(
        ins_nom=nombre,
        ins_host=host,
        ins_puerto=PUERTO_POR_DEFECTO,
        ins_fec_alta=desde,
        ins_est="A",
    )
    db.add(fila)
    db.flush()
    log.info("Nodo dado de alta: %s (%s:%s)", nombre, host, PUERTO_POR_DEFECTO)
    return fila


def modelo_activo(db: Session) -> ModeloML:
    """Modelo en produccion, registrado a partir de lo que cargo el detector.

    Solo puede haber uno activo: lo garantiza el indice unico filtrado
    ``UX_mdl_produccion``. Si ya existe, se devuelve sin tocarlo (asi un
    modelo aprobado a mano no se pisa al reiniciar).
    """
    fila = db.query(ModeloML).filter(ModeloML.mdl_est == "A").first()
    if fila:
        return fila

    det = get_detector()
    umbral_nombre = det.umbral_nombre
    fila = ModeloML(
        mdl_nom=f"{det.modo.lower()}_{umbral_nombre}",
        mdl_tipo=det.modo.lower(),
        mdl_cuantil=CUANTIL_POR_UMBRAL.get(umbral_nombre, 0.010),
        mdl_umbral=det.umbral_actual,
        mdl_vars=json.dumps(det.features),
        mdl_hparms=json.dumps(
            {
                "ventana": det.ventana,
                "modo": det.modo,
                "zonal": True,
                "umbrales": det.umbrales,
            }
        ),
        mdl_ruta_art=ML_ARTIFACTS,
        mdl_est="A",
        mdl_fec_entr=utc_now(),
    )
    db.add(fila)
    db.flush()
    log.info("Modelo activo registrado: %s", fila.mdl_nom)
    return fila