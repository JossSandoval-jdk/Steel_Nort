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
│   │   ├── main.py           # Arranque de la API + routers
│   │   ├── routers/          # auth, usuarios, anomalias, metricas,
│   │   │                     # telemetria, dashboard, reentrenamiento, dominio
│   │   ├── services/         # logica de negocio (anomalias, telemetria, nodos...)
│   │   ├── collector/        # telemetria: metrics, log_event, xe, stream_daemon
│   │   ├── ml/detector.py    # evaluacion online con los artefactos del modelo
│   │   ├── models/           # ORM (Usuarios, Alertas, Modelos_ML, Nodos_SCADA...)
│   │   ├── schemas/          # DTOs Pydantic
│   │   └── middleware/       # rate limit, seguridad, protección del modelo
│   ├── training/
│   │   ├── nucleo/
│   │   │   ├── data_preparation/   # pipeline 00→04 (inventario, selección,
│   │   │   │                       # limpieza, transformación, integración)
│   │   │   └── modeling/           # pipeline 01→05 (muestras, correlación,
│   │   │                           # Isolation Forest, reglas motor, diagnóstico)
│   │   ├── captures/         # capturas de telemetría por corrida
│   │   └── output/           # corridas (baseline/anomalias) + datasets generados
│   ├── ml/artifacts/         # artefactos desplegados (modelo, scaler, features)
│   └── tools/                # menu_pipeline, simular_carga, generar_carga,
│                             # inyectar_anomalias
├── frontend/             # React 19 + Vite (dashboard) + Express proxy + Socket.IO
├── database/             # Maestro: schema.sql + diccionario_datos.sql (SQL Server)
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

# Backend
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # ajustar DATABASE_URL, SECRET_KEY, SEED_ADMIN_*
uvicorn app.main:app --reload --port 8000
# API: http://localhost:8000  ·  docs: http://localhost:8000/docs

# Frontend
cd frontend
npm install
npm run dev
```

## Documentación por módulo

- [Backend (API)](backend/README.md) — instalación, configuración, endpoints de
  autenticación/usuarios y notas de seguridad.
- [Preparación de datos (núcleo)](backend/training/nucleo/data_preparation/README.md)
  — pipeline 00→04, variables, fuentes y decisiones.
- Preparación de datos standalone (fase 2): repositorio `Fase_2_Prepacion _datos`
  (autocontenido, con datos y reportes CRISP-DM).
