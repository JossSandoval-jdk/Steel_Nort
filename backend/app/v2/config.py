"""Configuracion de la version 2 (lecta de variables ``V2_*``).

La base de v2 es ``bdSteelNort_v2``, que se crea con
``database/schema_bdsteelnort.sql`` (21 tablas, particiones, triggers y
procedimientos). Va aparte de la de v1 para que las dos coexistan.

Hereda todos los parametros de la configuracion de v1 (``app.config``) para no
duplicar el bloque de seguridad, y cada uno puede sobreescribirse con el
prefijo ``V2_`` en el ``.env``:

    V2_DATABASE_URL=mssql+pyodbc://localhost,1433/bdSteelNort_v2?...
    V2_RATE_LIMIT_MAX=2000
"""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from app.config import Settings as SettingsV1

NOMBRE_BASE = "bdSteelNort_v2"

DEFAULT_URL = (
    f"mssql+pyodbc://localhost,1433/{NOMBRE_BASE}"
    "?driver=ODBC+Driver+18+for+SQL+Server"
    "&Trusted_Connection=yes&TrustServerCertificate=yes"
)


class SettingsV2(SettingsV1):
    """Configuracion propia de v2."""

    database_url: str = DEFAULT_URL

    # SQL Server del sistema de escritorio que SteelNort monitorea. Es OTRO
    # servidor, con su propio esquema: aqui solo se comprueba que responde,
    # no se leen las tablas de v2. Vacio = esa conexion no se revisa.
    #
    #     V2_MONITOREO_URL=mssql+pyodbc://sa:clave@localhost,1434/SteelNort?...
    #
    # Ojo: la clave va aqui, en el .env, que no se sube al repositorio.
    monitoreo_url: str = ""

    # El collector escribe filas crudas por HTTP: el limite de v1 (120/min)
    # no sirve aqui.
    rate_limit_max: int = 2000
    rate_limit_window_seconds: int = 60

    # --- Ciclo de monitoreo -------------------------------------------------
    # El backend lee el SQL Server del escritorio cada ``ciclo_intervalo``
    # segundos, guarda la muestra, la evalua contra la ventana de las ultimas
    # ``ciclo_ventana`` muestras y, si sale anomala, abre la alerta.
    #
    # Con el simulador encendido se inventan las muestras con el mismo formato
    # que las reales, para poder probar el pipeline entero sin depender del
    # servidor de escritorio. En cuanto haya uno de verdad: V2_CICLO_SIMULADO=no
    #
    #     V2_CICLO_ACTIVO=no        # apaga la tarea de fondo
    #     V2_CICLO_INTERVALO=15     # segundos entre lecturas
    #     V2_CICLO_VENTANA=30       # muestras de historico para el z-score
    #     V2_CICLO_UMBRAL_Z=3.0     # |z| a partir del cual es anomalia
    #     V2_CICLO_SIMULADO=si
    ciclo_activo: bool = True
    ciclo_intervalo: int = 15
    ciclo_ventana: int = 30
    ciclo_umbral_z: float = 3.0
    ciclo_simulado: bool = True

    # Titulo y version que se exponen en /docs.
    titulo: str = "SteelNort API v2"
    version: str = "2.0.0"

    model_config = SettingsConfigDict(
        env_prefix="V2_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def nombre_base(self) -> str:
        """Nombre de la base a la que se conecta (para los mensajes)."""
        return self.database_url.split("/")[-1].split("?")[0]

    @property
    def nombre_base_monitoreada(self) -> str:
        """Nombre de la base del sistema monitoreado, o "" si no esta configurada."""
        if not self.monitoreo_url:
            return ""
        return self.monitoreo_url.split("/")[-1].split("?")[0]


settings = SettingsV2()
