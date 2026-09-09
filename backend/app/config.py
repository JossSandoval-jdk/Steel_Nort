"""Configuracion central del backend SteelNort.

Este modulo centraliza toda la configuracion de la aplicacion leyendo
las variables de entorno (archivo ``.env``) de forma tipada con
``pydantic-settings``.

Al usar una unica clase de configuracion, el proyecto escala de forma
ordenada: cada nuevo modulo (ML, alertas, reportes, etc.) puede leer
los valores desde aqui sin redefinir la fuente de origen.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion global del backend.

    Los atributos se completan con las variables de entorno definidas
    en ``.env``. Se mantienen con nombres en mayusculas para hacerlos
    equivalentes a los del archivo ``.env.example``.
    """

    # Conexion a la base de datos (SQL Server mediante pyodbc).
    database_url: str = (
        "mssql+pyodbc://localhost,1433/SteelNort"
        "?driver=ODBC+Driver+18+for+SQL+Server"
        "&Trusted_Connection=yes&TrustServerCertificate=yes"
    )

    # Seguridad (firma y vigencia de tokens).
    secret_key: str = "change-me-use-a-secret-key-of-at-least-32-chars"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    csrf_token_expire_minutes: int = 120

    # Credenciales del usuario administrador inicial (seed).
    seed_admin_nombre: str = "Administrador SteelNort"
    seed_admin_email: str = "admin@steelnort.com"
    seed_admin_password: str = "Admin123!"
    seed_admin_rol: str = "Administrador"
    seed_admin_iniciales: str = "ADM"

    # Origenes permitidos por CORS (separados por coma).
    cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Devuelve los origenes CORS como lista de cadenas."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()