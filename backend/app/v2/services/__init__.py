"""Servicios de v2.

Un archivo por familia de tablas, con funciones planas que reciben la sesion
de SQLAlchemy. ``crud.py`` tiene las cinco operaciones compartidas (listar,
obtener, nuevo, cambiar, borrar) y el resto solo anade las reglas del dominio.
"""

from app.v2.services import acceso, crud, datos, deteccion, modelo, nodos, sistema

__all__ = ["acceso", "crud", "datos", "deteccion", "modelo", "nodos", "sistema"]