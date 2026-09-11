import os

# Rutas base del proyecto web (se resuelven relativas al archivo).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGS_DIR = os.getenv("LOG_DIR", os.path.join(BASE_DIR, "logs"))
SPOOL_DIR = os.getenv("SPOOL_DIR", os.path.join(BASE_DIR, "training", "captures", "spool"))

API_URL = os.getenv("API_URL", "http://localhost:7070")
SQL_HOST = os.getenv("SQL_HOST", "127.0.0.1")
SQL_PORT = os.getenv("SQL_PORT", "1434")
SQL_USER = os.getenv("SQL_USER", "sa")
SQL_PASSWORD = os.getenv("SQL_PASSWORD", "SteelNort2026")
SQL_DATABASE = os.getenv("SQL_DATABASE", "SteelNort")

DURATION = int(os.getenv("DURATION", "900"))
WORKERS = int(os.getenv("WORKERS", "10"))
METRICS_INTERVAL = int(os.getenv("METRICS_INTERVAL", "5"))
LOG_TAIL_INTERVAL = int(os.getenv("LOG_TAIL_INTERVAL", "2"))
AUDIT_POLL_INTERVAL = int(os.getenv("AUDIT_POLL_INTERVAL", "5"))

# ---------------------------------------------------------------------
# STREAM: coleccion continua hacia la API web (daemon de streaming).
# ---------------------------------------------------------------------
STREAM_API_URL = os.getenv("STREAM_API_URL", "http://localhost:8089")
STREAM_USER = os.getenv("STREAM_USER", "")
STREAM_PASSWORD = os.getenv("STREAM_PASSWORD", "")
STREAM_INTERVAL = int(os.getenv("STREAM_INTERVAL", "7"))
STREAM_NDO_IP = os.getenv("STREAM_NDO_IP", "127.0.0.1")
STREAM_NDO_NOM = os.getenv("STREAM_NDO_NOM", "Servidor Negocio")

# Ruta de los archivos .xel del monitor Extended Events (igual que en
# el entorno de entrenamiento; ajustable por variable de entorno).
XE_FILE_PATH = os.getenv(
    "XE_FILE_PATH", "/var/opt/mssql/log/steel_events*.xel"
)

OUTPUT_BASE = os.getenv(
    "OUTPUT_BASE", os.path.join(BASE_DIR, "training", "captures")
)
DATASET_NAME = os.getenv("DATASET_NAME", "baseline")
OUTPUT_DIR = os.path.join(OUTPUT_BASE, DATASET_NAME)

DEFAULT_USER_ID = 5
DEFAULT_USER_LOGIN = "pedro"
DEFAULT_USER_PASSWORD = "super123"

SQL_SERVER_CONN_STR = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={SQL_HOST},{SQL_PORT};"
    f"DATABASE={SQL_DATABASE};"
    f"UID={SQL_USER};PWD={SQL_PASSWORD};"
    f"Encrypt=yes;TrustServerCertificate=yes;"
)
