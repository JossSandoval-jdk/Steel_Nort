"""Modelos ORM de v2: 25 tablas en 7 familias.

Se agrupan por caracteristicas compartidas, no una por archivo:

    acceso.py         rol, permiso, usuario, rol_permiso, sesiones   (edicion manual)
    nodos.py          instancias, sesiones_sql                        (origen de la carga)
    modelo.py         modelos_ml, predicciones_ml, deriva_monitor,
                      reentrenamiento, reentrenamiento_paso          (ciclo del detector)
    deteccion.py      alertas, alerta_variable, causas_raiz,
                      alerta_regla, heatmap_anomalias                (avisos)
    datos.py          metricas, eventos, logs_sql,
                      estadisticas_carga                             (crudos, alta frecuencia)
    sistema.py        configuracion_sistema, auditoria               (clave/valor y registro)
    notificaciones.py notificaciones, push_suscripciones             (campanita y push)

Al importar este paquete, todas las clases quedan registradas en
``Base.metadata`` (metadata propia de v2) y ``verificar_esquema`` puede
compararlas con las tablas reales.
"""

from app.v2.models.acceso import Permiso, Rol, RolPermiso, Sesion, Usuario
from app.v2.models.datos import EstadisticaCarga, Evento, LogSQL, Metrica
from app.v2.models.deteccion import Alerta, AlertaRegla, AlertaVariable, CausaRaiz, HeatmapAnomalia
from app.v2.models.modelo import (
    DerivaMonitor,
    ModeloML,
    PrediccionML,
    Reentrenamiento,
    ReentrenamientoPaso,
)
from app.v2.models.nodos import Instancia, SesionSQL
from app.v2.models.notificaciones import Notificacion, PushSuscripcion
from app.v2.models.sistema import Auditoria, Configuracion

TABLAS = [
    Rol,
    Permiso,
    Usuario,
    RolPermiso,
    Sesion,
    Instancia,
    SesionSQL,
    ModeloML,
    PrediccionML,
    Alerta,
    AlertaVariable,
    CausaRaiz,
    AlertaRegla,
    HeatmapAnomalia,
    Metrica,
    Evento,
    LogSQL,
    EstadisticaCarga,
    DerivaMonitor,
    Reentrenamiento,
    ReentrenamientoPaso,
    Configuracion,
    Auditoria,
    Notificacion,
    PushSuscripcion,
]

__all__ = [c.__name__ for c in TABLAS] + ["TABLAS"]