"""Capa de acceso a datos de v2.

A diferencia de v1, la metadata de v2 es **independiente** (``Base`` propio).
Los nombres de tabla del esquema canonico son en minuscula y con prefijo de
tres letras (``rol``, ``alertas``), y en SQL Server la comparacion no
distingue mayusculas: compartir ``Base`` con v1 (``Usuarios``, ``Alertas``)
haria que ``create_all`` chocara entre las dos versiones.

La base ``bdSteelNort_v2`` la crea ``database/schema_bdsteelnort.sql``, que ademas
instala particiones, triggers y procedimientos que SQLAlchemy no sabe crear.
Por eso el arranque solo **verifica** que existan las 21 tablas; crearlas aqui
deja la base sin particionar y es opcional (``V2_AUTO_CREATE``).
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.v2.config import settings

log = logging.getLogger("steelnort.v2.database")

# Crear las tablas desde Python pierde las particiones y los triggers del script
# canonico, asi que viene desactivado: se ejecuta database/schema_bdsteelnort.sql.
AUTO_CREATE = os.getenv("V2_AUTO_CREATE", "false").lower() in {"1", "true", "yes", "si"}


class Base(DeclarativeBase):
    """Base declarativa de los modelos de v2 (21 tablas de bdSteelNort_v2)."""


engine = create_engine(settings.database_url, pool_pre_ping=True, echo=False)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Session:
    """Dependencia de FastAPI: una sesion por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def nombres_de_tablas() -> set[str]:
    """Nombres de tabla (minusculas) del esquema ``dbo``, tal como los ve el servidor."""
    return {t.lower() for t in inspect(engine).get_table_names(schema="dbo")}


def verificar_esquema() -> tuple[list[str], list[str]]:
    """Compara los modelos declarados con las tablas reales.

    Devuelve ``(presentes, faltantes)``. No lanza excepcion: el arranque decide
    si es un fallo o solo un aviso segun ``V2_AUTO_CREATE``.
    """
    import app.v2.models  # noqa: F401  registra las tablas en Base.metadata

    reales = nombres_de_tablas()
    declaradas = {t.name.lower() for t in Base.metadata.sorted_tables}
    presentes = sorted(declaradas & reales)
    return presentes, sorted(declaradas - reales)


def init_db(auto_crear: bool = AUTO_CREATE) -> list[str]:
    """Verifica el esquema y devuelve la lista de tablas faltantes.

    Con ``auto_crear=True`` las crea (solo util en una base de pruebas: pierde
    particiones, triggers y procedimientos del script canonico).
    """
    _, faltantes = verificar_esquema()
    if not faltantes:
        return []

    if auto_crear:
        log.warning("V2_AUTO_CREATE activo: creando %d tablas sin particiones ni triggers.", len(faltantes))
        Base.metadata.create_all(bind=engine, checkfirst=True)
        _, faltantes = verificar_esquema()

    if faltantes:
        raise RuntimeError(
            "Faltan tablas en la base de v2: "
            + ", ".join(faltantes)
            + ". Ejecute database/schema_bdsteelnort.sql (crea la base completa)."
        )
    return []


def sondear_logs() -> dict:
    """Comprueba que se pueda leer el log del SQL Server monitoreado.

    SteelNort vigila el sistema de escritorio y de ahi saca los logs. Esta
    funcion intenta leer el ``errorlog`` del servidor con ``xp_readerrorlog``:
    si responde, es que la conexion a los logs esta viva.

    Igual que ``sondear_monitoreo``, nunca lanza excepcion.
    """
    if not settings.monitoreo_url:
        return {
            "conectado": False,
            "configurado": False,
            "detalle": "Sin configurar (V2_MONITOREO_URL vacio)",
        }

    motor = engine_monitoreo()
    try:
        with motor.connect() as cx:
            fila = cx.execute(text("SELECT TOP 1 * FROM xp_readerrorlog(0, 1, NOLIMIT)")).first()
        if fila is None:
            return {"conectado": False, "configurado": True, "detalle": "El errorlog vino vacio"}
        return {
            "conectado": True,
            "configurado": True,
            "origen": "errorlog de SQL Server",
            "detalle": "Logs conectados",
        }
    except Exception as exc:  # el error ES el resultado de este chequeo
        log.warning("No se pudieron leer los logs del sistema monitoreado: %s", exc)
        return {
            "conectado": False,
            "configurado": True,
            "detalle": f"Sin conexion: {exc.__class__.__name__}",
        }


def version_bd() -> str:
    """``SELECT @@VERSION`` recortado, para el reporte de arranque."""
    with engine.connect() as cx:
        fila = cx.execute(text("SELECT CONVERT(varchar(80), SERVERPROPERTY('ProductVersion'))")).first()
    return str(fila[0]) if fila else "desconocida"


# =====================================================================
# CONEXION AL SISTEMA MONITOREADO
# =====================================================================
# SteelNort vigila otro SQL Server (el del sistema de escritorio). Es una
# conexion aparte, con su propio esquema, y solo se usa para comprobar que
# responde: no se leen las tablas de v2 ni se escribe nada.

_engine_monitoreo = None


def engine_monitoreo():
    """Engine del sistema monitoreado, o ``None`` si no esta configurado.

    Se crea la primera vez que se usa (y no al importar el modulo) para que
    unset V2_MONITOREO_URL no rompa el arranque.
    """
    global _engine_monitoreo
    if not settings.monitoreo_url:
        return None
    if _engine_monitoreo is None:
        _engine_monitoreo = create_engine(settings.monitoreo_url, pool_pre_ping=True, echo=False)
    return _engine_monitoreo


def sondear_monitoreo() -> dict:
    """Comprueba que el sistema monitoreado responda.

    Devuelve un diccionario con ``conectado`` y ``detalle`` para pintar, mas
    algunos datos que demuestran que la conexion es real de verdad: version
    del servidor, base y cuantas tablas tiene.

    Nunca lanza excepcion: si algo falla, devuelve ``conectado=False`` con el
    motivo en ``detalle``. Para eso sirve: que un chequeo de salud no tumbe la
    pantalla.
    """
    if not settings.monitoreo_url:
        return {
            "conectado": False,
            "configurado": False,
            "detalle": "Sin configurar (V2_MONITOREO_URL vacio)",
        }

    motor = engine_monitoreo()
    try:
        with motor.connect() as cx:
            version = cx.execute(text("SELECT CONVERT(varchar(80), @@VERSION)")).scalar() or ""
            base = cx.execute(text("SELECT DB_NAME()")).scalar() or ""
            # Cuantas tablas de usuario tiene: el indice clustered de
            # sys.partitions da el conteo sin recorrer la tabla.
            tablas = cx.execute(
                text(
                    "SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped = 0"
                )
            ).scalar()
        producto = version.splitlines()[0] if version else "desconocida"
        return {
            "conectado": True,
            "configurado": True,
            "base": str(base),
            "servidor": producto,
            "tablas": int(tablas or 0),
            "detalle": "Conectado",
        }
    except Exception as exc:
        log.warning("No se pudo conectar al sistema monitoreado: %s", exc)
        return {
            "conectado": False,
            "configurado": True,
            "detalle": f"Sin conexion: {exc.__class__.__name__}",
        }