"""Crea tu cuenta de administrador en la API v2.

Se ejecuta una vez, antes de arrancar la API. Pregunta por pantalla el nombre,
el usuario, la clave y el DNI, comprueba que la clave se haya escrito bien y
guarda la clave cifrada (bcrypt). La clave no queda en ningun archivo.

    python crear_admin_v2.py

Lo que hace:
  1. crea los 24 permisos y los tres roles si no existen;
  2. crea tu usuario con el rol Administrador (todo permitido);
  3. si el usuario ya existe, le actualiza la clave y los datos.

La base de datos sale de ``V2_DATABASE_URL`` (o de ``DATABASE_URL``) en el
``.env``. No escribe nada en el codigo: ni usuario ni clave.
"""

from __future__ import annotations

import getpass
import sys

from app.v2.config import settings
from app.v2.database import SessionLocal, verificar_esquema
from app.v2.services import semilla

MIN_CLAVE = 8


def preguntar(texto: str, por_defecto: str = "") -> str:
    while True:
        valor = input(texto).strip() or por_defecto
        if valor:
            return valor
        print("  -> no puede quedar vacio")


def preguntar_opcional(texto: str) -> str | None:
    return input(texto).strip() or None


def preguntar_clave() -> str:
    while True:
        clave = getpass.getpass("  Clave (minimo 8 caracteres): ")
        if len(clave) < MIN_CLAVE:
            print(f"  -> muy corta, minimo {MIN_CLAVE} caracteres")
            continue
        if clave != getpass.getpass("  Repite la clave: "):
            print("  -> las dos claves no coinciden")
            continue
        return clave


def main() -> int:
    print()
    print("=" * 62)
    print(f" SteelNort v2 - alta de administrador ({settings.nombre_base})")
    print("=" * 62)

    try:
        _, faltantes = verificar_esquema()
    except Exception as error:
        print(f"\nNo se pudo conectar con la base: {error}")
        print("Revise V2_DATABASE_URL en el .env y que el servidor SQL este arriba.\n")
        return 1

    if faltantes:
        print(f"\nFaltan {len(faltantes)} tablas en la base. Ejecute primero:")
        print("  database/schema_bdsteelnort.sql\n")
        return 1

    print("\nTus datos de administrador:\n")
    nombre = preguntar("  Nombre completo            : ")
    login = preguntar("  Usuario de acceso          : ")
    dni = preguntar("  DNI (obligatorio, es unico): ")
    email = preguntar_opcional("  Correo (opcional)          : ")
    telefono = preguntar_opcional("  Telefono (opcional)        : ")
    clave = preguntar_clave()

    print("\nRoles disponibles: " + ", ".join(semilla.ROLES))
    rol = preguntar("  Rol                        : ", "Administrador")

    with SessionLocal() as db:
        semilla.sembrar(db)  # permisos y roles

        con_dni = semilla.usuario_por_dni(db, dni)
        if con_dni is not None and con_dni.usu_log != login:
            print(f"\nEse DNI ya pertenece al usuario '{con_dni.usu_log}'. Abortado.\n")
            return 1

        try:
            usuario = semilla.crear_admin(
                db,
                nombre=nombre,
                login=login,
                clave=clave,
                dni=dni,
                email=email,
                telefono=telefono,
                rol_nombre=rol,
            )
        except Exception as error:
            print(f"\nNo se pudo guardar el usuario: {error}\n")
            return 1

    print("\n" + "-" * 62)
    print(f" Listo: {usuario.usu_nom} (id {usuario.usu_cod})")
    print(f" Usuario: {usuario.usu_log}   Rol: {rol}")
    print(f" Clave guardada cifrada: si ({len(clave)} caracteres)")
    print(" Entra en  http://127.0.0.1:8200/docs  ->  POST /api/v2/auth/login")
    print("-" * 62)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
