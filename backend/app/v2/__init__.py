"""SteelNort - version 2 del backend.

API paralela a la de ``app/`` sobre el esquema canonico
``database/schema_bdsteelnort.sql`` (21 tablas). No cambia el comportamiento de
v1: ambas coexisten.

Organizacion:

    config.py      valores ``V2_*`` (hereda los de ``app.config``)
    database.py    ``Base`` propia, engine, ``get_db`` e ``init_db``
    models/        los 21 modelos SQLAlchemy, agrupados en seis familias
    schemas/       schemas Pydantic, uno por familia
    services/      la logica de cada familia + ``crud`` con lo comun
    seguridad.py   dependencias de JWT y de permiso
    routers/       un router por familia, mas ``auth``
    main.py        la app FastAPI y su arranque

Familias: acceso, nodos, modelo, deteccion, datos y sistema. Las tablas de alta
frecuencia (``metricas``, ``eventos``, ``logs_sql``, ``estadisticas_carga``) las
escribe el collector por POST y las borra ``proc_retencion_datos``, asi que la
API no ofrece edicion ni borrado de ellas.

Uso:  uvicorn app.v2.main:app --port 8200
"""

__version__ = "2.0.0"