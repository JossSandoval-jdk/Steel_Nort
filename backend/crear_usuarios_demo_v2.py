"""Crea usuarios de prueba, uno por rol, para revisar la API y el frontend.

    python crear_usuarios_demo_v2.py

Crea (o actualiza) tres cuentas ficticias:

    ggeneral  -> Gerente general
    encargado -> Encargado
    operador  -> Operador

El administrador NO se crea aqui: ese es el tuyo y lo das de alta con
``python crear_admin_v2.py``, que te pregunta los datos.

IMPORTANTE: estas cuentas y sus claves estan escritas en este archivo a
proposito, para poder probarlas rapido. Son de uso local. Antes de publicar
la API, borralas:

    python crear_usuarios_demo_v2.py --borrar
"""

from __future__ import annotations

import sys

from sqlalchemy import delete, select

from app.v2.database import SessionLocal
from app.v2.models.acceso import Usuario
from app.v2.services import semilla

CLAVE_DEMO = "SteelNort2026!"

CUENTAS = [
    ("ggeneral", "Gerente General Demo", "10000000001", "ggeneral@demo.steelnort.local", "900000001", "Gerente general"),
    ("encargado", "Encargado Demo", "10000000002", "encargado@demo.steelnort.local", "900000002", "Encargado"),
    ("operador", "Operador Demo", "10000000003", "operador@demo.steelnort.local", "900000003", "Operador"),
]


def crear(db) -> None:
    semilla.sembrar(db)
    for login, nombre, dni, email, telefono, rol in CUENTAS:
        usuario = semilla.crear_admin(
            db, nombre=nombre, login=login, clave=CLAVE_DEMO, dni=dni, email=email, telefono=telefono, rol_nombre=rol
        )
        print(f"  {rol:<16} {usuario.usu_log:<10} id={usuario.usu_cod}  {usuario.usu_nom}")


def borrar(db) -> None:
    """Borra las cuentas de demo (deja intacto al administrador)."""
    for login, *_ in CUENTAS:
        db.execute(delete(Usuario).where(Usuario.usu_log == login))
    db.commit()
    restantes = db.scalars(select(Usuario.usu_log)).all()
    print("  borradas. usuarios que quedan:", list(restantes))


def main() -> int:
    print("\nSteelNort v2 - usuarios de prueba por rol")
    print("-" * 58)
    with SessionLocal() as db:
        if "--borrar" in sys.argv:
            borrar(db)
        else:
            crear(db)
            print("-" * 58)
            print(f"  clave de las tres cuentas: {CLAVE_DEMO}")
            print("  (solo local: cambiala o borra estas cuentas antes de publicar)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
