"""Capa de acceso a la base de datos (SQLAlchemy).

Configura el motor y la sesion de SQLAlchemy usando la URL definida en
:mod:`app.config`. A partir de aqui, los modelos definidos en
:mod:`app.models` se registran en la misma metadata, por lo que agregar
nuevas tablas (alertas, reportes, etc.) solo implica crear sus modelos.

Estrategia de inicializacion:
  - ``init_db`` crea las tablas pendientes si es necesario (idempotente).
  - ``get_db`` es la dependencia de FastAPI que entrega una sesion por
    request y la cierra al terminar.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos ORM."""


# El pool se ajusta segun el motor: para SQL Server/OSQL usamos
# pool_pre_ping para detectar conexiones caidas y evitar errores.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> "Session":
    """Dependencia de FastAPI: entrega una sesion de BD por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Crea las tablas definidas en los modelos si no existen.

    Al importar los modelos dentro de esta funcion se garantiza que
    todas las clases esten registradas en ``Base.metadata`` antes de
    intentar crearlas. Es idempotente y seguro ejecutarlo en cada
    arranque.
    """
    import app.models  # noqa: F401  (registra los modelos en la metadata)

    Base.metadata.create_all(bind=engine)