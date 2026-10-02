"""Servicio de ACCESO: login, permisos y CRUD de usuarios/roles/permisos.

Solo hay una regla que no es CRUD generico y por eso vive aqui: la clave del
usuario. ``UsuarioCreate``/``UsuarioUpdate`` la reciben como ``password`` y
este servicio la cifra con bcrypt antes de guardarla; al leer jamas se
devuelve (``UsuarioOut`` no tiene ese campo).
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.security import create_access_token, hash_password, verify_password
from app.utils import utc_now
from app.v2.models.acceso import Permiso, Rol, RolPermiso, Sesion, Usuario
from app.v2.schemas.acceso import PermisoCreate, RolCreate, UsuarioCreate, UsuarioUpdate
from app.v2.services import crud

MODULO = "acceso"


# =====================================================================
# USUARIOS
# =====================================================================


def listar_usuarios(db: Session, pagina: int, tamano: int, orden: str, con_bajas: bool, estado: str | None):
    return crud.listar(
        db,
        Usuario,
        orden or "usu_cod",
        filtros={"usu_est": estado} if estado else None,
        pagina=pagina,
        tamano=tamano,
        con_bajas=con_bajas,
    )


def obtener_usuario(db: Session, cod: int) -> Usuario:
    return crud.obtener_o_404(db, Usuario, "usu_cod", cod)


def crear_usuario(db: Session, datos: UsuarioCreate, actor: int | None) -> Usuario:
    """Crea el usuario y guarda ``password`` como hash bcrypt."""
    if _existe_usuario(db, datos.usu_log):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese usu_log ya existe")
    if not db.get(Rol, datos.rol_cod):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El rol {datos.rol_cod} no existe")

    campos = datos.model_dump(exclude={"password"})
    campos["usu_cla"] = hash_password(datos.password)
    return crud.nuevo(db, Usuario, campos, actor)


def actualizar_usuario(db: Session, cod: int, datos: UsuarioUpdate, actor: int | None) -> Usuario:
    campos = datos.model_dump(exclude_unset=True, exclude={"password"})
    if datos.password:
        campos["usu_cla"] = hash_password(datos.password)
    if campos.get("rol_cod") and not db.get(Rol, campos["rol_cod"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El rol indicado no existe")
    return crud.cambiar(db, Usuario, "usu_cod", cod, campos)


def eliminar_usuario(db: Session, cod: int, actor: int | None) -> Usuario:
    """Baja logica: ``usu_est = 'I'`` y se informa ``fec_eli``."""
    if actor == cod:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No se puede desactivar la propia cuenta"
        )
    return crud.borrar(db, Usuario, "usu_cod", cod, columna_estado="usu_est", actor=actor)


def _existe_usuario(db: Session, login: str) -> bool:
    return db.scalars(select(Usuario).where(Usuario.usu_log == login)).first() is not None


# =====================================================================
# ROLES
# =====================================================================


def listar_roles(db: Session, pagina: int, tamano: int, orden: str, con_bajas: bool, estado: str | None):
    return crud.listar(
        db,
        Rol,
        orden or "rol_nom",
        filtros={"rol_est": estado} if estado else None,
        pagina=pagina,
        tamano=tamano,
        con_bajas=con_bajas,
    )


def crear_rol(db: Session, datos: RolCreate, actor: int | None) -> Rol:
    if db.scalars(select(Rol).where(Rol.rol_nom == datos.rol_nom)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El rol '{datos.rol_nom}' ya existe")
    return crud.nuevo(db, Rol, datos.model_dump(), actor)


def eliminar_rol(db: Session, cod: int, actor: int | None) -> Rol:
    return crud.borrar(db, Rol, "rol_cod", cod, columna_estado="rol_est", actor=actor)


# =====================================================================
# PERMISOS Y ASIGNACIONES
# =====================================================================


def listar_permisos(db: Session, pagina: int, tamano: int, orden: str, con_bajas: bool, modulo: str | None):
    return crud.listar(
        db,
        Permiso,
        orden or "per_mod,per_acc",
        filtros={"per_mod": modulo} if modulo else None,
        pagina=pagina,
        tamano=tamano,
        con_bajas=con_bajas,
    )


def crear_permiso(db: Session, datos: PermisoCreate, actor: int | None) -> Permiso:
    existente = db.scalars(
        select(Permiso).where(Permiso.per_mod == datos.per_mod, Permiso.per_acc == datos.per_acc)
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe {datos.per_mod}:{datos.per_acc}"
        )
    return crud.nuevo(db, Permiso, datos.model_dump(), actor)


def listar_roles_permisos(db: Session, pagina: int, tamano: int, orden: str, rol_cod: int | None):
    return crud.listar(
        db,
        RolPermiso,
        orden or "rp_cod",
        filtros={"rol_cod": rol_cod} if rol_cod else None,
        pagina=pagina,
        tamano=tamano,
    )


def asignar_permiso(db: Session, rol_cod: int, per_cod: int, actor: int | None) -> RolPermiso:
    """Asigna un permiso a un rol. El par ya existe,asi que no se duplica."""
    if not db.get(Rol, rol_cod):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El rol {rol_cod} no existe")
    if not db.get(Permiso, per_cod):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El permiso {per_cod} no existe")

    ya_esta = db.scalars(
        select(RolPermiso).where(RolPermiso.rol_cod == rol_cod, RolPermiso.per_cod == per_cod)
    ).first()
    if ya_esta:
        return ya_esta
    return crud.nuevo(db, RolPermiso, {"rol_cod": rol_cod, "per_cod": per_cod}, actor)


def quitar_permiso(db: Session, rp_cod: int, actor: int | None) -> RolPermiso:
    return crud.borrar(db, RolPermiso, "rp_cod", rp_cod, columna_estado="rp_est", actor=actor)


# =====================================================================
# SESIONES
# =====================================================================


def listar_sesiones(
    db: Session,
    pagina: int,
    tamano: int,
    orden: str,
    usuario: int | None,
    estado: str | None,
):
    filtros = {}
    if usuario:
        filtros["ses_usu"] = usuario
    if estado:
        filtros["ses_est"] = estado
    return crud.listar(db, Sesion, orden or "-ses_fec_ini", filtros or None, pagina=pagina, tamano=tamano)


# =====================================================================
# LOGIN Y PERMISOS
# =====================================================================


def autenticar(db: Session, login: str, clave: str, ip: str | None) -> tuple[Usuario, str, str, int]:
    """Valida usuario y clave. Devuelve ``(usuario, rol, token, minutos)``."""
    usuario = db.scalars(
        select(Usuario).where(Usuario.usu_log == login, Usuario.fec_eli.is_(None))
    ).first()

    if usuario is None or not verify_password(clave, usuario.usu_cla):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o clave incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if usuario.usu_est != "A":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El usuario esta inactivo")

    rol = db.get(Rol, usuario.rol_cod)
    token, minutos = create_access_token(usuario.usu_cod, extra={"rol_cod": usuario.rol_cod})
    return usuario, rol.rol_nom if rol else "", token, minutos


def registrar_sesion(db: Session, usuario_cod: int, ip: str | None) -> Sesion:
    """Abre la fila de ``sesiones`` que accompany al token."""
    sesion = Sesion(ses_usu=usuario_cod, ses_fec_ini=utc_now(), ses_ip=ip, ses_est="A")
    db.add(sesion)
    db.commit()
    db.refresh(sesion)
    return sesion


def cerrar_sesion(db: Session, sesion_cod: int) -> None:
    sesion = db.get(Sesion, sesion_cod)
    if sesion is None or sesion.ses_est != "A":
        return
    sesion.ses_fec_fin = utc_now()
    sesion.ses_est = "C"
    db.commit()


def permisos_del_rol(db: Session, rol_cod: int) -> list[str]:
    """Permisos de un rol en formato ``modulo:accion``."""
    filas = db.execute(
        select(Permiso.per_mod, Permiso.per_acc)
        .join(RolPermiso, RolPermiso.per_cod == Permiso.per_cod)
        .where(RolPermiso.rol_cod == rol_cod, RolPermiso.rp_est == "A", Permiso.per_est == "A")
    ).all()
    return sorted(f"{mod}:{acc}" for mod, acc in filas)


def es_administrador(rol: str | None) -> bool:
    """El rol Administrador tiene permiso implicito sobre todo."""
    return rol == "Administrador"