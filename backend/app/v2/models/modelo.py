"""Modelos de MODELO: que se despliega y en que estado esta su ciclo de vida.

Las cinco tablas del bloque 4 y 7 del esquema: el modelo publicado, cada
ventana evaluada, la deriva de sus variables y los reentrenamientos con su
bitacora de pasos. Todas apuntan a ``modelos_ml.mdl_cod``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
    DECIMAL,
    NVARCHAR,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.utils import utc_now
from app.v2.database import Base


class ModeloML(Base):
    """Modelo entrenado registrado.

    Solo uno puede estar activo (``mdl_est = 'A'``) a la vez: lo garantiza el
    indice unico filtrado ``UX_mdl_produccion``.
    """

    __tablename__ = "modelos_ml"
    __table_args__ = {"schema": "dbo"}

    mdl_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    mdl_nom: Mapped[str] = mapped_column(String(100), nullable=False)
    mdl_tipo: Mapped[str] = mapped_column(String(30), nullable=False, default="ensemble_z")
    mdl_cuantil: Mapped[float] = mapped_column(DECIMAL(4, 3), nullable=False, default=0.010)
    mdl_umbral: Mapped[float | None] = mapped_column(DECIMAL(10, 6))
    mdl_vars: Mapped[str | None] = mapped_column(NVARCHAR)
    mdl_hparms: Mapped[str | None] = mapped_column(NVARCHAR)
    mdl_ruta_art: Mapped[str | None] = mapped_column(String(500))
    mdl_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="C")
    mdl_fec_entr: Mapped[datetime | None] = mapped_column(DateTime)
    reg_usu: Mapped[int | None] = mapped_column(Integer)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    eli_usu: Mapped[int | None] = mapped_column(Integer)
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)


class PrediccionML(Base):
    """Una fila por ventana evaluada, no solo por anomalia.

    Guardar tambien las ventanas normales es lo que permite recalcular
    umbrales y medir la tasa de falsos positivos. ``prd_feats`` no se puede
    modificar despues (trigger ``TR_prd_features_inmutable``): es el insumo
    del reentrenamiento.
    """

    __tablename__ = "predicciones_ml"
    # implicit_returning=False porque hay dos triggers sobre esta tabla
    # (TR_prd_instancia_valida y TR_prd_features_inmutable). Por defecto
    # SQLAlchemy pide la PK con "INSERT ... OUTPUT inserted.prd_cod", y SQL
    # Server lo rechaza con el error 334 en cuanto la tabla tiene un trigger
    # habilitado. Sin esta linea, insertar una ventana anomala revienta.
    # Con ella sale "INSERT ...; select scope_identity()": un viaje extra,
    # aceptable porque aqui solo se guardan ventanas.
    __table_args__ = {"schema": "dbo", "implicit_returning": False}

    prd_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    prd_mdl: Mapped[int] = mapped_column(ForeignKey("dbo.modelos_ml.mdl_cod"), nullable=False)
    prd_ins: Mapped[int] = mapped_column(ForeignKey("dbo.instancias.ins_cod"), nullable=False)
    prd_ini: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    prd_fin: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    prd_sco_iso: Mapped[float | None] = mapped_column(DECIMAL(10, 6))
    prd_sco_cop: Mapped[float | None] = mapped_column(DECIMAL(10, 6))
    prd_sco_ens: Mapped[float] = mapped_column(DECIMAL(10, 6), nullable=False)
    prd_umbral: Mapped[float] = mapped_column(DECIMAL(10, 6), nullable=False)
    prd_zona: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="N")
    prd_es_anom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prd_feats: Mapped[str | None] = mapped_column(NVARCHAR)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class DerivaMonitor(Base):
    """Deriva de una variable del modelo.

    ``drv_metrica`` dice con que criterio se midio: ``P`` percentil, ``K`` KS.
    ``drv_est``: ``E`` en espera, ``A`` alerta, ``D`` deriva confirmada.
    """

    __tablename__ = "deriva_monitor"
    __table_args__ = {"schema": "dbo"}

    drv_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    drv_mdl: Mapped[int] = mapped_column(ForeignKey("dbo.modelos_ml.mdl_cod"), nullable=False)
    drv_fec: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    drv_var: Mapped[str] = mapped_column(String(100), nullable=False)
    drv_metrica: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="P")
    drv_valor: Mapped[float] = mapped_column(DECIMAL(10, 6), nullable=False)
    drv_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="E")
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class Reentrenamiento(Base):
    """Ciclo de reentrenamiento con su veredicto.

    F1 y FPR van antes y despues para defender el despliegue con numeros.
    ``ren_est``: ``P`` pendiente, ``E`` ejecutando, ``V`` validado, ``A``
    aprobado, ``R`` rechazado, ``X`` fallido.
    """

    __tablename__ = "reentrenamiento"
    __table_args__ = {"schema": "dbo"}

    ren_cod: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    ren_mdl_origen: Mapped[int] = mapped_column(ForeignKey("dbo.modelos_ml.mdl_cod"), nullable=False)
    ren_mdl_nuevo: Mapped[int | None] = mapped_column(ForeignKey("dbo.modelos_ml.mdl_cod"))
    ren_disparo: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    ren_motivo: Mapped[str | None] = mapped_column(String(200))
    ren_usu_sol: Mapped[int | None] = mapped_column(ForeignKey("dbo.usuario.usu_cod"))
    ren_fec_sol: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    ren_dat_ini: Mapped[datetime | None] = mapped_column(DateTime)
    ren_dat_fin: Mapped[datetime | None] = mapped_column(DateTime)
    ren_criterio: Mapped[str | None] = mapped_column(String(500))
    ren_n_train: Mapped[int | None] = mapped_column(Integer)
    ren_params: Mapped[str | None] = mapped_column(NVARCHAR)
    ren_f1_antes: Mapped[float | None] = mapped_column(DECIMAL(5, 4))
    ren_f1_desp: Mapped[float | None] = mapped_column(DECIMAL(5, 4))
    ren_fpr_antes: Mapped[float | None] = mapped_column(DECIMAL(5, 2))
    ren_fpr_desp: Mapped[float | None] = mapped_column(DECIMAL(5, 2))
    ren_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="P")
    ren_usu_apr: Mapped[int | None] = mapped_column(ForeignKey("dbo.usuario.usu_cod"))
    ren_fec_apr: Mapped[datetime | None] = mapped_column(DateTime)
    ren_obs: Mapped[str | None] = mapped_column(String(500))
    reg_usu: Mapped[int | None] = mapped_column(Integer)
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    eli_usu: Mapped[int | None] = mapped_column(Integer)
    fec_eli: Mapped[datetime | None] = mapped_column(DateTime)


class ReentrenamientoPaso(Base):
    """Bitacora paso a paso del reentrenamiento.

    No hay ``rep_cod``: la clave es ``(rep_ren, rep_orden)``, que ya es unico
    y es lo que siempre se consulta.
    """

    __tablename__ = "reentrenamiento_paso"
    __table_args__ = {"schema": "dbo"}

    rep_ren: Mapped[int] = mapped_column(ForeignKey("dbo.reentrenamiento.ren_cod"), primary_key=True)
    rep_orden: Mapped[int] = mapped_column(Integer, primary_key=True)
    rep_paso: Mapped[str] = mapped_column(String(50), nullable=False)
    rep_est: Mapped[str] = mapped_column(CHAR(1), nullable=False, default="P")
    rep_fec_ini: Mapped[datetime | None] = mapped_column(DateTime)
    rep_fec_fin: Mapped[datetime | None] = mapped_column(DateTime)
    rep_detalle: Mapped[str | None] = mapped_column(String(500))
    fec_reg: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)