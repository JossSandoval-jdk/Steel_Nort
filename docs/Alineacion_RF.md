# Alineación de requisitos funcionales (RF1–RF7 + RF10)

**Proyecto:** Sistema inteligente con aprendizaje automático para observabilidad y diagnóstico de anomalías de rendimiento en el OLTP de Steel Nort
**Fecha:** 2026-10-13
**Motivo:** el pre informe menciona un **RF10 (gestión de usuarios)** que no aparece en la lista RF1–RF7 del proyecto aprobado. Este documento justifica por qué existe y cómo se presenta ante el evaluador.

> **Fuente de la lista aprobada:** `docs/Indicadores_v2.md` §"Requisitos del sistema" (RF1–RF7).

---

## 1. Los siete requisitos aprobados y su módulo real

| Cód. | Requisito | Módulo / artefacto real | Punto de entrada | Estado |
|---|---|---|---|---|
| RF1 | Autenticación de usuarios | `routers/auth.py`, `routers/acceso.py`, `services/acceso.py`, `security.py` | `/api/v2/auth/login`, `/api/v2/acceso/usuarios` | Implementado |
| RF2 | Recopilar métricas, logs y eventos | `tools/collector/{metrics,eventos,stream}.py` | `POST /api/v2/telemetria/push` | Implementado |
| RF3 | Procesamiento de datos | `tools/pipeline/01_selecction.py`, `02_limpieza.py`, `03_preparacion.py` | scripts CRISP-DM (por lotes) | Implementado |
| RF4 | Detección de anomalías | `tools/motor/{detector,decisor}.py` + bundle `output/modelado/produccion/` | `detector.evaluar` en `telemetria.py` | Implementado |
| RF5 | Alertas y diagnóstico de apoyo | `services/anomalia_v2.py`, `services/clasificador_tipo.py` | `/deteccion/alertas`, `/deteccion/alertas/{cod}/informe` | Implementado |
| RF6 | Visualización de indicadores | `pages/Dashboard.jsx`, `services/sistema.py` | `/sistema/resumen`, `/sistema/heatmap` | Implementado |
| RF7 | Generación de reportes | `services/informes.py` | `/informes/resumen|anomalias|alertas|generar|exportados` | Implementado |

---

## 2. Caso del RF10 (gestión de usuarios)

**Qué es:** alta, edición, baja y asignación de roles/permisos de usuarios de la plataforma.

**Por qué aparece:** el backend v2 implementa un módulo de administración de usuarios/roles/permisos
(`routers/acceso.py`, tablas `usuario`, `rol`, `permiso`, `rol_permiso`) y una pantalla de
Configuración que lo expone (`pages/Configuracion.jsx`, pestañas de Usuarios y Roles/Permisos).

**Cómo se justifica (dos argumentos válidos, usar el que el docente prefiera):**

1. **Ya está contemplado dentro de RF1.** La descripción aprobada de RF1 dice textualmente:
   *"Gestionar los permisos de usuarios autorizados mediante autenticación y funcionalidades según su
   rol, salvaguardando la seguridad e integridad del sistema"*. La gestión de usuarios y la asignación
   de roles son, por tanto, **parte de RF1**, no un requisito nuevo: RF10 es un desglose de RF1.
2. **Es una capacidad adicional de valor** (útil para el criterio de Adecuación funcional): administrar
   usuarios sin tocar la base de datos es un plus que facilita la tarea del encargado de TI. Se puede
   presentar como **extensión** del alcance, siempre declarándolo como tal.

**Recomendación:** en el pre informe final, **renombrar RF10 como "RF1.2 — Gestión de usuarios"** (sub-requisito
de RF1) o moverlo a una sección de "capacidades adicionales". Evita que el evaluador lo lea como un
requisito aprobado que no está en el proyecto.

---

## 3. Trazabilidad con los indicadores

| Req. | Indicador asociado | Valor / estado |
|---|---|---|
| RF1 / RF10 | I-4.1 (cumplimiento de requisitos) | Parcial: falta Web Push + auditoría |
| RF2 | I-1.1 (volumen), I-1.2 (calidad) | 3 330 métricas · 9 605 eventos · 2 946 logs |
| RF3 | I-1.2 | Completitud 100 % |
| RF4 | I-2.1 (F1), I-2.2 (correlación), I-5.1 (recall) | F1 0.964 · 51 pares \|r\|≥0.6 · recall 100 % |
| RF5 | I-3.1, I-3.2, I-3.3, I-4.2 | top-2 96.1 % (I-3.1); severidad sin ground truth (I-3.2); efectividad 54.2 % (I-3.3) |
| RF6 | I-4.2, I-4.3 | endpoints ≤ 0.5 s; satisfacción pendiente (encuesta) |
| RF7 | I-4.1 | export CSV/JSON operativo |

> **Honestidad:** I-3.1 (top-1 ✗), I-3.2 (sin ground truth) e I-3.3 (54.2 %) **no están en verde**.
> Declararlas como limitaciones conocidas y explicar la causa (el "fondo" de carga domina el z) antes
> que el evaluador las descubra.
