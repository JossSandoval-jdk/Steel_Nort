"""Seed de roles y permisos por defecto del sistema SteelNort.

Población inicial (idempotente) de las tablas Roles, Permisos y
Rol_Permiso. Se ejecuta al arrancar la API junto con init_db.

Matriz por defecto:
  - Administrador: acceso total a usuarios, roles y reentrenamiento.
  - Supervisor: solo lectura de usuarios, roles y permisos.
  - Operador: sin permisos administrativos.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.model_rol_permiso import Permisos, RolPermiso, Roles

log = logging.getLogger("steelnort.seed_roles")

ROLES_DEFAULT = [
    ("Administrador", "Acceso total al sistema."),
    ("Supervisor", "Lectura de usuarios, roles y permisos."),
    ("Operador", "Operación diaria sin privilegios administrativos."),
]

PERMISOS_DEFAULT = [
    # Catálogo de permisos (clave, nombre, modulo)
    ("usuarios:leer", "Ver usuarios", "usuarios"),
    ("usuarios:crear", "Crear usuarios", "usuarios"),
    ("usuarios:editar", "Editar usuarios", "usuarios"),
    ("usuarios:eliminar", "Eliminar usuarios", "usuarios"),
    ("roles:leer", "Ver roles", "roles"),
    ("roles:crear", "Crear roles", "roles"),
    ("roles:editar", "Editar roles", "roles"),
    ("roles:eliminar", "Eliminar roles", "roles"),
    ("permisos:crear", "Crear permisos", "permisos"),
    ("ml:reentrenar", "Reentrenar modelo ML", "ml"),
]

# Matriz rol -> permisos (por clave)
MATRIZ_DEFAULT = {
    "Administrador": {
        "usuarios:leer",
        "usuarios:crear",
        "usuarios:editar",
        "usuarios:eliminar",
        "roles:leer",
        "roles:crear",
        "roles:editar",
        "roles:eliminar",
        "permisos:crear",
        "ml:reentrenar",
    },
    "Supervisor": {
        "usuarios:leer",
        "roles:leer",
    },
    "Operador": set(),
}


def seed_roles_y_permisos(db: Session) -> None:
    """Inserta roles y permisos por defecto si la tabla Roles está vacía.

    Es idempotente: si ya hay roles, no hace nada para no pisar
    cambios hechos por el administrador.
    """
    roles_existentes = db.execute(select(Roles)).scalars().first()
    if roles_existentes is not None:
        return

    log.info("Sembrando roles y permisos por defecto...")

    # 1. Catálogo de permisos
    permisos_por_clave: dict[str, Permisos] = {}
    for clave, nombre, modulo in PERMISOS_DEFAULT:
        permiso = Permisos(
            prm_clave=clave,
            prm_nom=nombre,
            prm_mod=modulo,
            prm_act=True,
            reg_usu="sistema",
        )
        db.add(permiso)
        permisos_por_clave[clave] = permiso
    db.flush()

    # 2. Catálogo de roles
    roles_por_nombre: dict[str, Roles] = {}
    for nombre, desc in ROLES_DEFAULT:
        rol = Roles(
            rol_nom=nombre,
            rol_desc=desc,
            rol_act=True,
            reg_usu="sistema",
        )
        db.add(rol)
        roles_por_nombre[nombre] = rol
    db.flush()

    # 3. Asignaciones N:N
    for nombre_rol, claves in MATRIZ_DEFAULT.items():
        rol = roles_por_nombre[nombre_rol]
        for clave in claves:
            permiso = permisos_por_clave.get(clave)
            if permiso is None:
                continue
            db.add(RolPermiso(rp_rol=rol.rol_cod, rp_prm=permiso.prm_cod, reg_usu="sistema"))

    db.commit()
    log.info("Roles y permisos por defecto sembrados correctamente.")