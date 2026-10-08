# SteelNort — Plataforma de Detección de Anomalías de Rendimiento OLTP

Monitoreo y detección de anomalías de rendimiento dirigido a sistemas
**OLTP sobre SQL Server** (Steel Nort). Captura telemetría de la máquina, del
motor de base de datos y de las sesiones de aplicación; la prepara siguiendo
**CRISP-DM**; entrena un modelo de detección **no supervisado** (Isolation
Forest + reglas de umbral); y lo despliega para detectar anomalías en tiempo
real, visualizándolas en un dashboard web.

> La fase de **Preparación de Datos** vive además como repositorio standalone
> autocontenido (`Fase_2_Prepacion _datos`) con sus datos y documentación, como
> evidencia de la fase 2 del ciclo CRISP-DM.

---

## Arquitectura

```
SteelNort_web/
├── backend/              # Python 3.12 + FastAPI
│   ├── app/
│   │   ├── v2/               # API v2 (unica expuesta, prefijo /api/v2)
│   │   │   ├── main.py       #   arranque + lifespan (esquema, semilla, detector)
│   │   │   ├── routers/      #   auth, acceso, nodos, modelo, deteccion,
│   │   │   │                 #   datos, sistema, estado, telemetria
│   │   │   ├── services/     #   logica de negocio
│   │   │   ├── models/       #   ORM (21 tablas: usuarios, alertas, modelos_ml...)
│   │   │   └── schemas/      #   DTOs Pydantic
│   │   ├── collector/        # telemetria: metrics, log_event, xe, stream_daemon
│   │   ├── ml/               # detector/decisor/ensamble online
│   │   └── security.py       # bcrypt, JWT y CSRF
│   ├── training/
│   │   ├── nucleo/
│   │   │   ├── data_preparation/   # pipeline 00→04 (inventario, selección,
│   │   │   │                       # limpieza, transformación, integración)
│   │   │   └── modeling/           # pipeline 01→05 (muestras, correlación,
│   │   │                           # Isolation Forest, reglas motor, diagnóstico)
│   │   ├── captures/         # capturas de telemetría por corrida + spool
│   │   ├── output/           # inventario/limpio/integrado/modelado + corridas
│   │   ├── entrenar.bat      # reentreno end-to-end (captura live → promover)
│   │   └── *.py              # capturar_live, construir_dataset, generar_copod,
│   │                         # promover, reentrenar_capturas
│   ├── ml/artifacts/         # artefactos desplegados (modelo, scaler, features)
│   ├── tests/                # pytest + simular_telemetria (end-to-end)
│   └── tools/                # menu_pipeline, menu_laboratorio, generar_carga,
│                             # inyectar_anomalias, limpieza
├── frontend/             # React 19 + Vite (dashboard) + Express proxy + Socket.IO
├── database/             # Maestro: schema.sql + diccionario_datos.sql (SQL Server)
├── docs/                 # ARQUITECTURA.md, FUNCIONALIDADES_PRINCIPALES.md
└── README.md             # este documento
```

## Componentes

| Módulo | Tecnología | Descripción |
|--------|-----------|-------------|
| `backend/` | Python 3.12, FastAPI, SQLAlchemy, scikit-learn | API REST (auth de doble token, telemetría, anomalías, reentrenamiento), colectores de telemetría y detección online |
| `frontend/` | React 19, Vite, Express, Socket.IO | Dashboard de monitoreo y consumo de la API |
| `database/` | Microsoft SQL Server | Esquema maestro: alertas, modelos ML, nodos SCADA, usuarios, configuración |
| `Fase_2_Prepacion _datos` | Python / pandas | **Preparación de datos standalone** (evidencia fase 2 CRISP-DM) |

## Cómo funciona

1. **Captura** — Los colectores leen métricas del sistema, del motor SQL Server
   y de eventos de sesiones; la telemetría cruda se evalúa en memoria y solo lo
   relevante para el negocio persiste en la BD (alertas, eventos, predicciones).
2. **Preparación de datos (CRISP-DM 2)** — `data_preparation/` convierte los
   logs crudos de cada corrida en un dataset integrado y depurado de las
   **22 variables principales** del dominio OLTP.
3. **Modelado (CRISP-DM 3)** — `modeling/` construye las muestras, analiza
   correlación/VIF, entrena un **Isolation Forest** con ventanas de 5 minutos y
   reglas de umbral, y diagnostica las corridas (baseline vs. anomalías).
4. **Despliegue (CRISP-DM 4)** — Los artefactos (modelo, scaler, features,
   reglas) se copian a `ml/artifacts/` y `app/ml/detector.py` evalúa las
   corridas en línea contra ese modelo dinámico.
5. **Visualización** — El dashboard muestra alertas, ventanas anómalas y el
   timeline de cada corrida.

## Estado del pipeline (núcleo de entrenamiento)

- Preparación: **00 inventario → 01 selección → 02 limpieza → 03 transformación → 04 integración**.
- Modelado: **01 muestras → 02 correlación → 03 detección (Isolation Forest)
  → 04 reglas del motor → 05 diagnóstico de resultados**.
- Orquestación por menú: `python tools/menu_pipeline.py`.

## Requisitos

- **Python 3.12** (recomendado para la pila FastAPI/pydantic).
- **SQL Server** con driver ODBC 17/18.
- **Node.js** para el frontend.

## Puesta en marcha

```bash
# Base de datos
#  · ejecutar database/schema.sql en SQL Server

# Backend (API v2 en :8200; requiere SQL Server con bdSteelNort_v2)
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # ajustar DATABASE_URL, SECRET_KEY, STREAM_*
python crear_admin_v2.py      # crea el usuario administrador (una sola vez)
run_backend.bat               # API: http://127.0.0.1:8200/api/v2 · docs: /docs

# Frontend
cd frontend
npm install
npm run dev
```

## Documentación por módulo

- [Arquitectura y navegación](docs/ARQUITECTURA.md) — índice del repositorio:
  API v2, flujo de telemetría, pipeline CRISP-DM y artefactos.
- [Backend (API)](backend/README.md) — instalación, configuración, endpoints y
  notas de seguridad.
- [Preparación de datos (núcleo)](backend/training/nucleo/data_preparation/README.md)
  — pipeline 00→04, variables, fuentes y decisiones.
- Preparación de datos standalone (fase 2): repositorio `Fase_2_Prepacion _datos`
  (autocontenido, con datos y reportes CRISP-DM).
