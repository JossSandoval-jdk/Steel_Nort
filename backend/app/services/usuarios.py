"""Operaciones de negocio para la administracion de usuarios."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.model_usuario import Usuarios
from app.schemas import UsuarioCreate, UsuarioUpdate
from app.security import hash_password


def listar_usuarios(db: Session) -> list[Usuarios]:
    return list(db.scalars(select(Usuarios).where(Usuarios.fec_eli.is_(None)).order_by(Usuarios.usu_cod)))


def crear_usuario(db: Session, payload: UsuarioCreate, actor: Usuarios) -> Usuarios:
    if db.scalar(select(Usuarios).where(Usuarios.usu_ema == payload.usu_ema)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya esta registrado.")
    usuario = Usuarios(
        usu_nom=payload.usu_nom,
        usu_ema=str(payload.usu_ema),
        usu_pwd=hash_password(payload.password),
        usu_rol=payload.usu_rol,
        usu_ini=payload.usu_ini,
        usu_act=True,
        reg_usu=str(actor.usu_cod),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def actualizar_usuario(db: Session, usuario_id: int, payload: UsuarioUpdate, actor: Usuarios) -> Usuarios:
    usuario = db.get(Usuarios, usuario_id)
    if usuario is None or usuario.fec_eli is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    cambios = payload.model_dump(exclude_unset=True)
    if "usu_ema" in cambios:
        existente = db.scalar(select(Usuarios).where(Usuarios.usu_ema == cambios["usu_ema"], Usuarios.usu_cod != usuario_id))
        if existente:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya esta registrado.")
        cambios["usu_ema"] = str(cambios["usu_ema"])
    if "password" in cambios:
        usuario.usu_pwd = hash_password(cambios.pop("password"))
    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)
    usuario.reg_usu = str(actor.usu_cod)
    db.commit()
    db.refresh(usuario)
    return usuario


def eliminar_usuario(db: Session, usuario_id: int, actor: Usuarios) -> None:
    if usuario_id == actor.usu_cod:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes eliminar tu propio usuario.")
    usuario = db.get(Usuarios, usuario_id)
    if usuario is None or usuario.fec_eli is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    usuario.usu_act = False
    usuario.eli_usu = str(actor.usu_cod)
    usuario.fec_eli = datetime.now(timezone.utc)
    db.commit()