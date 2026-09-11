"""Modelos ORM de SteelNort.

Este modulo agrega todas las entidades de la base de datos importando
cada archivo de dominio individual (p. ej. ``model_usuario``). Al
importarlos aqui, sus clases quedan registradas en ``Base.metadata`` y
``database.init_db`` puede crear las tablas automaticamente.

Escalar: para agregar una nueva tabla, cree su archivo (p. ej.
``model_alerta.py``) y agregue aqui su import.
"""

from app.models.model_usuario import EventosSesion, Sesiones, Usuarios
from app.models.model_alerta import Alertas, CausasRaiz, HeatmapAnomalias
from app.models.model_configuracion import ConfiguracionSistema
from app.models.model_ml import ModelosML, PrediccionesML
from app.models.model_muestra_normal import MuestrasNormales
from app.models.model_reporte import Reportes
from app.models.model_rol_permiso import Permisos, RolPermiso, Roles
from app.models.model_scada import NodosSCADA, Servicios

__all__ = [
	"Alertas",
	"CausasRaiz",
	"ConfiguracionSistema",
	"EventosSesion",
	"HeatmapAnomalias",
	"ModelosML",
	"MuestrasNormales",
	"NodosSCADA",
	"Permisos",
	"PrediccionesML",
	"Reportes",
	"RolPermiso",
	"Roles",
	"Servicios",
	"Sesiones",
	"Usuarios",
]