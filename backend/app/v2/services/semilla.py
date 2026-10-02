"""Datos minimos para que la API arranque en una base recien creada.

Idempotente: si ya estan los roles o los permisos, no hace nada. Crea lo
minimo indispensable:

  - los seis modulos de la API y sus cuatro acciones  -> 24 permisos,
  - tres roles (Administrador, Operador, Observador) con su matriz.

El usuario administrador **no** se crea aqui a proposito: se crea con
``crear_admin`` desde el script ``backend/crear_admin_v2.py``, que pide los
datos de la persona que va a ser administradora. Asi nadie entra con una clave
que este escrita en el codigo.

Lo que este archivo NO hace:

  - no inventa contrasenas ni usuarios,
  - no toca ``permiso``/``rol_permiso`` que alguien haya editado a mano: si el
    permiso ya existe se reutiliza tal cual.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.security import hash_password
from app.v2.models.acceso import Permiso, Rol, RolPermiso, Usuario

log = logging.getLogger("steelnort.v2.semilla")

# Los modulos son los grupos de la API. ``tablero`` es la pantalla de Inicio
# (el resumen), que se separa de ``sistema`` (la configuracion) para poder
# darsela a todos los roles aunque solo unos manageen la configuracion.
MODULOS = ["tablero", "acceso", "nodos", "modelo", "deteccion", "datos", "sistema"]
ACCIONES = ["leer", "crear", "editar", "eliminar"]

# Los cuatro roles del sistema. El Administrador lo tiene todo por el nombre
# del rol (asi no depende de que la tabla de asignaciones este completa), por
# eso no aparece en la matriz.
#
# Que puede hacer cada uno:
#   Administrador   -> todo
#   Gerente general -> ve todo y escribe, pero no borra nada
#   Encargado       -> opera el dia a dia: Inicio, Dashboard, Reportes, Alertas
#                      y el trabajo del dia; sin usuarios ni configuracion
#   Operador        -> lo mismo que el encargado pero solo mirando
MATRIZ = {
    "Gerente general": [
        f"{modulo}:{accion}" for modulo in MODULOS for accion in ("leer", "crear", "editar")
    ],
    "Encargado": [
        f"{modulo}:{accion}"
        for modulo in ("tablero", "nodos", "modelo", "deteccion", "datos")
        for accion in ("leer", "crear", "editar")
    ],
    "Operador": [f"{modulo}:leer" for modulo in ("tablero", "nodos", "modelo", "deteccion", "datos")],
}

# Orden en que se listan en la API y en el alta de usuarios.
ROLES = ["Administrador", "Gerente general", "Encargado", "Operador"]


def sembrar(db: Session) -> dict:
    """Crea roles y permisos. Devuelve un resumen. No crea usuarios."""
    permisos = _crear_permisos(db)
    roles = {nombre: _crear_rol(db, nombre) for nombre in ROLES}
    _asignar_permisos(db, roles, permisos)
    resumen = {"permisos": len(permisos), "roles": sorted(roles)}
    log.info("Semilla v2 aplicada: %s", resumen)
    return resumen


def _crear_permisos(db: Session) -> dict[str, Permiso]:
    """Permiso por cada par ``modulo:accion``. Reutiliza los que ya existen."""
    existentes = {f"{p.per_mod}:{p.per_acc}": p for p in db.scalars(select(Permiso)).all()}
    nuevos = 0
    for modulo in MODULOS:
        for accion in ACCIONES:
            clave = f"{modulo}:{accion}"
            if clave not in existentes:
                existentes[clave] = Permiso(per_mod=modulo, per_acc=accion, per_est="A")
                db.add(existentes[clave])
                nuevos += 1
    if nuevos:
        db.commit()
    return existentes


def _crear_rol(db: Session, nombre: str) -> Rol:
    rol = db.scalars(select(Rol).where(Rol.rol_nom == nombre)).first()
    if rol is None:
        rol = Rol(rol_nom=nombre, rol_est="A")
        db.add(rol)
        db.commit()
        db.refresh(rol)
    return rol


def _asignar_permisos(db: Session, roles: dict[str, Rol], permisos: dict[str, Permiso]) -> None:
    for nombre, rol in roles.items():
        if nombre == "Administrador":
            continue  # tiene acceso implicito, no necesita filas de asignacion

        # La matriz es la fuente de verdad: se anade lo que falta y se retira
        # lo que sobra, asi un cambio de permisos no deja restos.
        deseados = {clave: permisos[clave].per_cod for clave in MATRIZ[nombre] if clave in permisos}
        asignaciones = db.scalars(select(RolPermiso).where(RolPermiso.rol_cod == rol.rol_cod)).all()

        for asignacion in asignaciones:
            if asignacion.per_cod not in deseados.values():
                db.delete(asignacion)

        nuevas = [
            RolPermiso(rol_cod=rol.rol_cod, per_cod=cod, rp_est="A")
            for cod in deseados.values()
            if cod not in {a.per_cod for a in asignaciones}
        ]
        if nuevas:
            db.add_all(nuevas)
        db.commit()


def crear_admin(
    db: Session,
    nombre: str,
    login: str,
    clave: str,
    dni: str,
    email: str | None = None,
    telefono: str | None = None,
    rol_nombre: str = "Administrador",
) -> Usuario:
    """Alta (o actualizacion) de la cuenta que administrara el sistema.

    La llama ``backend/crear_admin_v2.py``, que pregunta los datos por
    pantalla. Si el ``login`` ya existe le cambia la clave y los datos en vez
    de crear un duplicado.
    """
    rol = _crear_rol(db, rol_nombre)

    usuario = db.scalars(select(Usuario).where(Usuario.usu_log == login)).first()
    if usuario is None:
        usuario = Usuario(usu_log=login, rol_cod=rol.rol_cod)
        db.add(usuario)

    usuario.usu_nom = nombre
    usuario.usu_cla = hash_password(clave)
    usuario.usu_dni = dni
    usuario.usu_ema = email or None
    usuario.usu_tel = telefono or None
    usuario.usu_est = "A"
    usuario.rol_cod = rol.rol_cod
    usuario.fec_eli = None

    db.commit()
    db.refresh(usuario)
    log.info("Administrador '%s' listo (rol %s, id %d)", usuario.usu_log, rol.rol_nom, usuario.usu_cod)
    return usuario


def usuario_por_dni(db: Session, dni: str) -> Usuario | None:
    """Otro usuario con ese DNI (el DNI es unico en la tabla)."""
    return db.scalars(select(Usuario).where(Usuario.usu_dni == dni)).first()