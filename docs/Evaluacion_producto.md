# Producto acreditable al 100%: cómo obtener el máximo puntaje

**Asignatura:** Seminario de Tesis I (USAT, 2026-II)
**Producto:** Sistema inteligente con aprendizaje automático para observabilidad y diagnóstico de anomalías de rendimiento en un sistema OLTP de Steel Nort
**Fuente:** sílabo, rúbrica del producto acreditable (14 puntos) y rúbrica de sustentación (IND5)

> Las rúbricas del sílabo están redactadas por niveles. Para sacar el puntaje más alto de cada criterio tienes que cumplir **todas las viñetas del nivel "Bueno"**, no solo algunas. Lo que está entre [corchetes] o marcado "confirma" debes verificarlo en tu producto real antes de afirmarlo.

> **Nota de cifras vigentes (2026-10-13).** La fuente válida de métricas del modelo es
> `backend/app/tools/output/modelado/indicadores/honesto.json` (protocolo dejar-una-corrida-fuera +
> normalización por corrida, etiquetas nativas). Modelo desplegado: **`ENSEMBLE_LOF_ELL`** (LOF +
> Elliptic), **F1 0.964 / recall 100 % / FPR ventana 2.74 %** en q01. Los archivos
> `output/modelado/validacion/{metrics.json, freeze.json}` son **legacy** (dicen `ENSEMBLE_Z`) y no
> deben usarse. No reportar F1 de ventana ni los z de Elliptic como "precisión": ver caveats en
> `docs/HALLAZGOS_VALIDACION.md:180-182`.

---

## 1. Cómo se califica el producto al 100%

| Indicador | Qué se evalúa | Evidencia | Instrumento | Peso en RA1 |
|---|---|---|---|---|
| IND1 | Producto al 50% | Producto al 50% | Lista de cotejo (20 ítems) | 25% |
| IND2 | Pre informe al 50% | Pre informe al 50% | Lista de cotejo | 25% |
| **IND3** | **Producto al 100%** | Producto al 100% | **Rúbrica (14 puntos)** | 25% |
| IND4 | Pre informe al 100% | Pre informe al 100% | Rúbrica (6 puntos) | 25% |
| **IND5** | **Sustentación técnico-académica** | Demostración del producto + pre informe | **Rúbrica (14 + 6 puntos)** | 100% de RA2 |

**Nota final:** `NF = RA1 × 0.60 + RA2 × 0.40`, con `RA1 = promedio(IND1…IND4)` y `RA2 = IND5`.

Por lo tanto, **el producto te evalúa dos veces**: en la rúbrica de 14 puntos (IND3) y en la sustentación, donde vale otros 14 puntos (IND5). Un producto sólido que no sabes explicar pierde puntos en la segunda.

Las rúbricas de producto (14) y pre informe (6) suman 20 puntos, lo que sugiere conversión directa a la escala vigesimal. Confírmalo con tu docente.

---

## 2. Resumen de puntajes de la rúbrica del producto (14 puntos)

| # | Criterio | Máximo | Deficiente | Malo | Debe mejorar | **Bueno** |
|---|---|---|---|---|---|---|
| 1 | Adecuación funcional | **1.50** | 0 – 0.2 | >0.2 – 0.5 | >0.5 – 0.9 | **>0.9 – 1.5** |
| 2 | Eficiencia de desempeño | **2.00** | 0 – 0.2 | >0.2 – 0.7 | >0.7 – 1.2 | **>1.2 – 2.0** |
| 3 | Capacidad de interacción | **2.50** | 0 – 0.4 | >0.4 – 0.8 | >0.8 – 1.5 | **>1.5 – 2.5** |
| 4 | Fiabilidad | **1.50** | 0 – 0.2 | >0.2 – 0.5 | >0.5 – 0.9 | **>0.9 – 1.5** |
| 5 | Seguridad | **2.50** | 0 – 0.4 | >0.4 – 0.8 | >0.8 – 1.5 | **>1.5 – 2.5** |
| 6 | Flexibilidad | **1.50** | 0 – 0.2 | >0.2 – 0.5 | >0.5 – 0.9 | **>0.9 – 1.5** |
| 7 | Protección | **2.50** | 0 – 0.4 | >0.4 – 0.8 | >0.8 – 1.5 | **>1.5 – 2.5** |
| | **Total** | **14.00** | | | | |

**Dónde están los puntos:** Interacción, Seguridad y Protección valen 7.5 de los 14 (54%). Súmales Eficiencia (2.0) y tienes 9.5 puntos en cuatro criterios. Prioriza ahí.

**Regla práctica (criterio mío, no de la rúbrica):** el evaluador elige un valor dentro del rango del nivel. Para acercarte al tope necesitas que *cada* viñeta del nivel Bueno sea demostrable en vivo. Si una falla, es probable que bajes hacia la parte baja del rango.

---

## 3. Criterio por criterio

### 3.1 Adecuación funcional (máximo 1.50)

**Qué mide:** si el producto hace lo que necesita la organización, con exactitud.

| Nivel | Puntos | Qué dice la rúbrica |
|---|---|---|
| Deficiente | 0 – 0.2 | No cubre las funciones necesarias; sin precisión requerida; no responde a necesidades reales |
| Malo | >0.2 – 0.5 | Cubre las funciones pero con errores; poca precisión; responde mínimamente a necesidades |
| Debe mejorar | >0.5 – 0.9 | Cubre las funciones; la mayoría con la precisión requerida; responde a necesidades reales |
| **Bueno** | **>0.9 – 1.5** | Cubre **todas** las funciones sin errores **y ofrece capacidades adicionales de valor**; resultados fiables y exactos; funciones que facilitan las tareas del usuario |

**Para llegar al tope necesitas:**

- [ ] Cada requisito funcional del proyecto (RF1 a RF7) implementado y demostrable. En tu pre informe aparece además un RF10 (gestión de usuarios) que no está en el proyecto aprobado: alinéalo o explícalo.
- [ ] El flujo completo en vivo: recolección → modelo → alerta → diagnóstico → dashboard → reporte. Hoy tu sección de interfaces no describe alertas ni reportes (RF5 y RF7).
- [ ] Resultados exactos y respaldados: **F1 de 0.964, Recall de 100 % (13/13 corridas) y FPR de 2.74 % por ventana** en q01 normalizado (`honesto.json`, modelo desplegado `ENSEMBLE_LOF_ELL`). *(Corregido 2026-10-14: las cifras 0.982 / 4.8 % provienen de una prueba con 108 ventanas pre-seleccionadas y no están respaldadas por ninguna evaluación válida del repositorio.)*
- [ ] Al menos 2 o 3 **capacidades adicionales** claras. Candidatas, si las tienes en el producto (confirma): capa anti falsos positivos (histéresis y consenso 2 de 3), monitor de deriva, atribución de variables afectadas en el diagnóstico, mapa de calor por hora.
- [ ] Validación con Steel Nort de que responde a necesidades reales (acta o entrevista con el gerente y el encargado de TI).

**Evidencia a llevar:** matriz RF → módulo → prueba → resultado; capturas por módulo; acta de validación.

**Lo que te baja de nivel:** funciones que solo existen como script y no están integradas a la plataforma; errores visibles durante la demo; una función "pendiente de implementar" en un escenario de la demo.

---

### 3.2 Eficiencia de desempeño (máximo 2.00)

**Qué mide:** tiempos de respuesta y uso de recursos bajo carga real.

| Nivel | Puntos | Qué dice la rúbrica |
|---|---|---|
| Deficiente | 0 – 0.2 | Demoras críticas de más de 7 s; uso ineficiente; inestable |
| Malo | >0.2 – 0.7 | Demoras críticas hasta 7 s; poco uso eficiente; poca estabilidad |
| Debe mejorar | >0.7 – 1.2 | Demoras críticas hasta 5 s; uso eficiente; estabilidad requerida |
| **Bueno** | **>1.2 – 2.0** | **Menos de 5 s**; uso eficiente y equilibrado; alta estabilidad; **soporta la carga de trabajo real en escenarios exigentes** |

**Para llegar al tope necesitas:**

- [ ] Una **tabla de mediciones** con evidencia, no solo "se ve rápido". Meta recomendada: **≤ 3 s**, que es tu RNF2 del proyecto y además cumple el "menos de 5 s" de la rúbrica.

| Operación | Meta | n | Promedio | p95 | Cumple |
|---|---|---|---|---|---|
| Inicio de sesión | ≤ 3 s | [ ] | [ ] | [ ] | [ ] |
| Carga del dashboard | ≤ 3 s | [ ] | [ ] | [ ] | [ ] |
| Consulta de anomalías | ≤ 3 s | [ ] | [ ] | [ ] | [ ] |
| Detección → alerta visible | ≤ 3 s | [ ] | [ ] | [ ] | [ ] |
| Generación de reporte | ≤ 3 s | [ ] | [ ] | [ ] | [ ] |

- [ ] **Una prueba de carga** con varios usuarios concurrentes (herramientas como k6, Locust o JMeter) que muestre que el tiempo se mantiene bajo carga.
- [ ] **Consumo de recursos del propio recolector** sobre el servidor de Steel Nort (CPU y memoria). Un monitor que degrada el sistema que vigila resta credibilidad.
- [ ] Estabilidad sostenida: una corrida larga (varias horas) sin degradación.

**Evidencia a llevar:** tabla de tiempos, capturas del resultado de la prueba de carga, gráfico de consumo de recursos.

**Lo que te baja de nivel:** medir una sola vez; medir solo en tu máquina sin carga; no medir el recolector.

---

### 3.3 Capacidad de interacción (máximo 2.50, el criterio más pesado)

**Qué mide:** si el usuario puede usar el producto con facilidad, sin ayuda y sin cometer errores graves.

| Nivel | Puntos | Qué dice la rúbrica |
|---|---|---|
| Deficiente | 0 – 0.4 | No es agradable; no permite tareas complejas ni comprensión autónoma; no previene errores |
| Malo | >0.4 – 0.8 | Poco agradable; solo tareas básicas; previene errores parcialmente |
| Debe mejorar | >0.8 – 1.5 | Agradable; permite tareas complejas pero no comprensión autónoma; previene errores |
| **Bueno** | **>1.5 – 2.5** | **Estético, satisfactorio, intuitivo, accesible y motivador**; tareas complejas con facilidad y **sin capacitación extensa**; previene errores, da **retroalimentación oportuna y clara** y ofrece **ayuda y documentación detallada** |

**Para llegar al tope necesitas, punto por punto:**

- [ ] **Estético e intuitivo:** diseño consistente (colores, tipografía, espaciado), navegación clara, jerarquía visual de las alertas por severidad.
- [ ] **Accesible:** contraste suficiente (relación mínima de 4.5:1 para texto normal), navegación por teclado, etiquetas en formularios, no depender solo del color para indicar severidad (usa también texto o íconos), diseño responsive.
- [ ] **Tareas complejas fáciles:** define una tarea compleja y pruébala, por ejemplo "encontrar la causa de la anomalía de ayer a las 3 pm" en menos de 2 minutos y sin ayuda.
- [ ] **Prevención de errores:** validación de formularios, confirmación antes de acciones destructivas (eliminar usuario, cambiar umbral), restricción de valores inválidos.
- [ ] **Retroalimentación:** estados de carga, mensajes de éxito y error comprensibles (no "Error 500"), estados vacíos ("no hay anomalías en este periodo").
- [ ] **Ayuda y documentación:** manual de usuario (tu RNF5 lo exige), tooltips o ayuda contextual en métricas técnicas (explica qué significa "page life expectancy").
- [ ] **Motivador y satisfactorio:** respáldalo con una **encuesta de satisfacción** (tu criterio de éxito es ≥ 80%) aplicada al gerente, al encargado de TI y al administrador.

**Evidencia a llevar:** manual de usuario, resultados de la encuesta, capturas de validaciones y mensajes, video corto de una tarea compleja.

**Lo que te baja de nivel:** no tener manual; mensajes técnicos incomprensibles; ninguna evidencia de que los usuarios reales lo probaron.

---

### 3.4 Fiabilidad (máximo 1.50)

**Qué mide:** estabilidad, tolerancia a fallos y recuperación sin perder datos.

| Nivel | Puntos | Qué dice la rúbrica |
|---|---|---|
| Deficiente | 0 – 0.2 | Muy inestable; no tolera ni gestiona fallos |
| Malo | >0.2 – 0.5 | Poco estable; gestiona fallos con dificultad |
| Debe mejorar | >0.5 – 0.9 | Estable, pocos fallos; gestiona fallos adecuadamente |
| **Bueno** | **>0.9 – 1.5** | Muy estable, **sin fallos**; gestiona fallos **sin impacto visible**; **se recupera rápidamente sin pérdida de datos ni interrupciones** |

**Para llegar al tope necesitas probar estos escenarios de falla, con evidencia:**

| Prueba de falla | Resultado esperado |
|---|---|
| Se detiene el recolector | Se reinicia solo (pm2, systemd o política de reinicio de contenedor); no se pierden datos |
| SQL Server deja de responder | El sistema reintenta y muestra un estado claro; al volver, retoma sin intervención |
| La API tarda o falla | La interfaz muestra mensaje claro y reintenta; no se cae |
| Corrida continua de varias horas | Sin errores críticos; conteo de registros coherente |

- [ ] **Revisa cómo registras las fallas.** En tu recolector, cuando una consulta falla guardas el valor `"0"` (latencia, estado de la API, etc.). Un cero falso se confunde con una señal real del sistema y contamina el modelo. Usa un valor nulo más un campo de estado de error, y registra el fallo en un log.
- [ ] Un endpoint de salud (health check) y logs estructurados.
- [ ] Verificación de que no se perdieron datos tras una falla: compara el conteo de registros antes y después.

**Evidencia a llevar:** video o capturas de la prueba de falla y recuperación, logs, conteo de registros.

**Lo que te baja de nivel:** la demo se cae; no puedes mostrar qué pasa si algo falla.

---

### 3.5 Seguridad (máximo 2.50)

**Qué mide:** que solo accedan quienes deben, con autenticación segura, roles y trazabilidad.

| Nivel | Puntos | Qué dice la rúbrica |
|---|---|---|
| Deficiente | 0 – 0.4 | No garantiza accesos, datos ni autenticación; no define roles |
| Malo | >0.4 – 0.8 | Garantiza poco; define roles pero responsabilidades indefinidas |
| Debe mejorar | >0.8 – 1.5 | Garantiza mayoritariamente; define roles y responsabilidades |
| **Bueno** | **>1.5 – 2.5** | Garantiza accesos, datos y autenticación y **alta resistencia a amenazas avanzadas**; roles y responsabilidades **y registro de las acciones de los usuarios para identificar responsables** |

**Para llegar al tope necesitas:**

- [x] **Autenticación segura:** JWT en memoria, contraseñas con **bcrypt**, expiración del token (120 min), **bloqueo temporal tras 5 intentos fallidos** (429 + `Retry-After`) y **CSRF por doble-envío** (cookie `csrf_token` + cabecera `X-CSRF-Token`, 403 si no coinciden) como defensa en profundidad (S1-8). Nota honesta: la v2 no usa cookies de sesión, así que CSRF es redundante en el diseño actual; se deja implementado y probado por si las credenciales pasaran a cookies. Falta la **renovación** (refresh token). Evidencia: `docs/Evidencia_seguridad.md` §3 y §7.
- [ ] **Comunicación segura:** HTTPS (tu RNF1 lo exige).
- [ ] **Roles y permisos:** una matriz clara.

| Función | Gerente general | Encargado de TI | Administrador |
|---|---|---|---|
| Ver dashboard | [ ] | [ ] | [ ] |
| Ver alertas y diagnóstico | [ ] | [ ] | [ ] |
| Generar reportes | [ ] | [ ] | [ ] |
| Configurar umbrales | [ ] | [ ] | [ ] |
| Gestionar usuarios | [ ] | [ ] | [ ] |

- [x] **Registro de auditoría** (es lo que define el nivel Bueno): una tabla `auditoria` con usuario, acción, recurso, resultado, IP y fecha, visible en la plataforma o consultable. Demuestra que puedes responder "¿quién cambió este umbral y cuándo?". → hecho: `docs/Evidencia_seguridad.md` §1 (tabla `dbo.auditoria`, endpoint `GET /sistema/auditoria` y vista en Configuración).
- [ ] **Alta resistencia a amenazas:** ✅ consultas parametrizadas (ORM en todo el v2), validación de entradas, cabeceras de seguridad (S1-10), CORS restringido (S1-9), análisis de dependencias (`npm audit`: 0 vulnerabilidades) y escaneo básico propio (ZAP no está instalado en el equipo). ⏳ Pendiente: secretos fuera del repositorio (S1-11) y usuario SQL de **solo lectura y mínimo privilegio** para el recolector (S1-12). Evidencia: `docs/Evidencia_seguridad.md` §5 y §6.
- [ ] Revisa tus repositorios de GitHub: sin credenciales, sin datos reales de la empresa, y privados si corresponde.

**Evidencia a llevar:** matriz de roles, captura del registro de auditoría, resultado del escaneo, evidencia de que el repositorio no expone secretos.

**Lo que te baja de nivel:** no registrar acciones por usuario; credenciales en el código; roles sin diferencias reales.

---

### 3.6 Flexibilidad (máximo 1.50)

**Qué mide:** capacidad de cambiar y crecer sin romper ni degradar.

| Nivel | Puntos | Qué dice la rúbrica |
|---|---|---|
| Deficiente | 0 – 0.2 | No es flexible ni escalable |
| Malo | >0.2 – 0.5 | Parcialmente flexible, no escalable |
| Debe mejorar | >0.5 – 0.9 | Flexible; soporta cambios y crecimiento |
| **Bueno** | **>0.9 – 1.5** | **Altamente** flexible y escalable; soporta cambios y crecimiento **sin degradación de calidad** y permite incorporar herramientas y funciones más accesibles, simples o eficientes |

**Para llegar al tope necesitas:**

- [ ] **Umbrales y reglas configurables** sin tocar código (archivo de configuración o base de datos). Por ejemplo, cambiar el umbral q01 o ajustar una regla R1–R7 desde configuración.
- [ ] **Arquitectura modular** documentada: recolector, preparación, modelo, motor de reglas, API y web como componentes separados.
- [ ] **Modelo intercambiable:** que el pipeline permita reemplazar o añadir un modelo sin reescribir el resto.
- [ ] **Agregar una métrica o regla nueva** como flujo documentado y demostrable.
- [ ] Una guía breve de extensión (RNF4 y RNF6 de tu proyecto: escalabilidad y mantenibilidad).

**Esto te prepara además para la sustentación**, donde te pedirán modificaciones en tiempo limitado.

**Evidencia a llevar:** diagrama de módulos, archivo de configuración, demostración de un cambio en vivo.

**Lo que te baja de nivel:** valores fijos en el código; todo en un solo script.

---

### 3.7 Protección (máximo 2.50)

**Qué mide:** que el producto limite operaciones no autorizadas, controle el uso indebido y tenga los riesgos documentados.

| Nivel | Puntos | Qué dice la rúbrica |
|---|---|---|
| Deficiente | 0 – 0.4 | No limita operaciones no autorizadas ni controla usos indebidos |
| Malo | >0.4 – 0.8 | Limita parcialmente; no controla usos indebidos |
| Debe mejorar | >0.8 – 1.5 | Limita operaciones no autorizadas; no controla usos indebidos ni aplica restricciones adecuadas |
| **Bueno** | **>1.5 – 2.5** | Limita operaciones no autorizadas, **controla usos indebidos y aplica restricciones adecuadas**; **documenta detalladamente los riesgos con todos los escenarios adversos y la evaluación de amenazas potenciales** |

**Para llegar al tope necesitas:**

- [x] **Una prueba de operación no autorizada**, con evidencia: por ejemplo, un usuario con rol sin permiso intenta gestionar usuarios o cambiar un umbral y el sistema responde 403. → hecho, `docs/Evidencia_seguridad.md` §2.
- [x] **Control de uso indebido:** límite de peticiones (respuesta 429), bloqueo tras intentos fallidos, validación de rangos. → hecho, `docs/Evidencia_seguridad.md` §3 (bloqueo a los 5 fallos y límite por IP).
- [ ] **Restricciones adecuadas:** el recolector solo lee (usuario SQL de solo lectura); la API no expone consultas arbitrarias.
- [x] **Protección de datos:** `sql_text` se responde enmascarado (`***`) desde `EventoOut`, y la Ley N.° 29733 se menciona con su marco de principios en `docs/Indicadores_v2.md` → «Protección de datos personales». → `docs/Evidencia_seguridad.md` §4.2.
- [x] **Matriz de riesgos y amenazas** como anexo, cubriendo todos los escenarios adversos. Ejemplo de estructura:

| Amenaza | Escenario | Impacto | Control aplicado | Evidencia |
|---|---|---|---|---|
| Robo de token | Un atacante reutiliza un JWT | Acceso indebido | Expiración corta, almacenamiento en memoria, revocación | [ ] |
| Inyección SQL | Entrada maliciosa en un filtro | Fuga o alteración de datos | Consultas parametrizadas, validación | [ ] |
| Abuso de la API | Muchas peticiones seguidas | Degradación del servicio | Límite de peticiones (429) | [x] `Evidencia_seguridad.md` §3.2 |
| Sobrecarga del recolector | Muestreo demasiado frecuente | Degradar el OLTP | Intervalo configurable, medición de consumo | [ ] |
| Contaminación del baseline | Entrenar con datos que ya tenían fallas | Modelo sesgado | Validación de la línea base, corridas normales etiquetadas | [ ] |
| Fatiga por falsas alarmas | Demasiadas alertas | Alertas ignoradas | Histéresis, consenso 2 de 3 | [ ] |
| Fuga de datos sensibles | `sql_text` con datos de clientes | Incumplimiento de la ley de datos | Enmascaramiento, acceso por rol | [x] `Evidencia_seguridad.md` §4.2 |
| Caída de la fuente de datos | SQL Server no responde | Pérdida de monitoreo | Reintentos, buffer, estado visible | [ ] |

**Evidencia a llevar:** capturas de la prueba de operación no autorizada (403), de la prueba de límite (429), y la matriz de riesgos completa.

**Lo que te baja de nivel:** no tener riesgos documentados; limitar solo en la interfaz y no en el servidor.

---

## 4. Sustentación del producto (IND5: 14 puntos)

Además de la rúbrica anterior, en la sustentación el producto vale 14 puntos más.

| Nivel | Puntos | Qué dice la rúbrica |
|---|---|---|
| Deficiente | 0 – 3.5 | Explica deficientemente el código; no ejecuta las modificaciones pedidas; no responde o responde incoherentemente |
| Malo | >3.5 – 7 | Explica sin detalle u olvida; ejecuta modificaciones pero responden mal; respuestas parciales |
| Debe mejorar | >7 – 10.5 | Explica parcialmente; ejecuta la mayoría de las modificaciones en el tiempo; responde la mayoría coherentemente |
| **Bueno** | **>10.5 – 14** | Explica **detalladamente** el código **e interpreta la lógica**; ejecuta **eficientemente todas** las modificaciones en el tiempo del docente; responde con coherencia, **con conclusiones y relacionándolas con el proyecto y el pre informe** |

Requisitos no optativos: pre informe culminado y producto terminado según el proyecto aprobado. El docente comprueba que **lo elaboraste tú mismo**.

### Cómo prepararte

**1. Explicar el código y la lógica.** Prepara una explicación de cada módulo en 2 minutos: qué hace, por qué se diseñó así, qué entra y qué sale.

| Módulo | Qué debes poder explicar |
|---|---|
| Recolector | De dónde salen las métricas (DMVs, Extended Events, psutil), cada cuánto, cómo maneja errores |
| Preparación | Limpieza, tasas por segundo, `merge_asof`, ventanas, normalización |
| Modelo | Por qué Isolation Forest + COPOD, por qué entrenar solo con datos normales, qué significa q01 |
| Motor de reglas | Cómo se asigna tipo y severidad; de dónde sale cada regla R1–R7 |
| API | Endpoints, formato de la respuesta, autenticación |
| Plataforma web | Flujo de login, roles, cómo se actualiza el dashboard |

**2. Modificaciones en vivo.** Ensaya con cronómetro cambios típicos:

- Cambiar un umbral o el nivel de percentil
- Agregar una regla nueva
- Agregar una tarjeta o gráfico al dashboard
- Agregar una métrica nueva
- Cambiar un rol o permiso
- Añadir un filtro al reporte

**3. Preguntas probables y cómo responder con conclusiones.**

| Pregunta | Qué debe incluir tu respuesta |
|---|---|
| ¿Por qué ese modelo y no otro? | Resultados comparados (incluye LOF y OCSVM), criterios de decisión, limitaciones |
| ¿Por qué solo datos normales para entrenar? | Aprendizaje no supervisado, pocos casos etiquetados, riesgo de fuga de datos |
| ¿Cómo evitaste fuga de datos entre corridas? | Separación por corridas, aclarar las corridas duplicadas (run1 = carga1, etc.) |
| ¿Qué pasa si falla el recolector o SQL Server? | Reintentos, estado visible, sin pérdida de datos |
| ¿Cómo garantizas la alerta en 3 s? | Tabla de mediciones y de dónde sale cada tiempo |
| ¿Quién puede hacer qué? ¿Cómo sabes quién hizo un cambio? | Matriz de roles y registro de auditoría |
| ¿Cómo se relaciona con tus objetivos? | Matriz objetivo → funcionalidad → evidencia → resultado |
| ¿Qué limitaciones tiene? | Dataset pequeño, escenarios simulados, escenarios no ejecutados, ventanas autocorrelacionadas |

**Cierra cada respuesta con una conclusión** ("por eso el modelo cumple F1 ≥ 85% y puede usarse en producción con estas limitaciones") y enlázala al proyecto y al pre informe. Eso es exactamente lo que la rúbrica premia en el nivel Bueno.

---

## 5. Referencia: lista de cotejo del 50% (ya fuiste evaluado con esto)

Son 20 ítems de 1 punto, organizados en 7 dimensiones. El 100% sube la exigencia, pero los mismos temas reaparecen:

| Dimensión | Ítems | Qué verificaban |
|---|---|---|
| Adecuación funcional | 3 | Núcleo corresponde al objetivo; flujo completo; resultados coherentes |
| Interacción y usabilidad | 3 | Acciones claras; retroalimentación; escenario sin dificultades |
| Fiabilidad | 3 | Estabilidad; control de errores previsibles; persistencia de datos |
| Desempeño | 2 | Tiempo de respuesta aceptable; sin bloqueos críticos |
| Seguridad y protección | 3 | Acceso controlado; protección de datos; evita operaciones no autorizadas |
| Evidencia de desarrollo | 3 | Versión ejecutable; organización técnica; trazabilidad a artefactos |
| IA o componente inteligente | 3 | Integrado y operativo; resultados validados; riesgos gestionados |

La dimensión de **IA** también te conviene preparar para el 100%: demuestra entrada → procesamiento → salida del modelo, casos de prueba con resultados validados y los riesgos (falsos positivos, deriva, línea base contaminada).

---

## 6. Matriz de evidencias a preparar

| Criterio | Evidencia principal | Estado actual (2026-10-13) | Falta |
|---|---|---|---|
| Adecuación funcional | Matriz RF → módulo → prueba (`Indicadores_v2.md:332-347`); métricas del modelo (`honesto.json`) | ⚠️ Parcial | Acta de validación con Steel Nort; alinear RF10 (`Alineacion_RF.md`); corrida e2e registrada |
| Eficiencia | Latencia de inferencia (`latencia.json`); etapas del detector (9.6 ms + 461.6 ms) | ⚠️ Parcial | Tabla de tiempos por operación; prueba de carga; consumo del recolector; corrida larga |
| Interacción | UI v2 (dashboard, alertas, reportes); retroalimentación y estados vacíos | ⚠️ Parcial | Manual de usuario; encuesta de satisfacción; ayuda contextual; contraste/ARIA |
| Fiabilidad | Health check (`/api/v2/salud`, `/estado/conexiones`); spool JSONL | ⚠️ Parcial | Fix del bug del `"0"`; logs estructurados; pruebas de falla; corrida larga |
| Seguridad | JWT en memoria; bcrypt; RBAC (`rol`/`permiso`/`rol_permiso`) | ⚠️ Parcial | **Registro de auditoría**; bloqueo de intentos; CORS/cabeceras; HTTPS; usuario SQL solo-lectura; secretos fuera del repo |
| Flexibilidad | Modelo intercambiable (`meta.json` + `ML_ARTIFACTS_DIR`) | ⚠️ Parcial | Umbrales/reglas configurables sin código; diagrama modular; guía de extensión |
| Protección | 403 en routers (`requiere_permiso`); rate limit en proxy Node | ⚠️ Parcial | Prueba 403/429; 429 en FastAPI; enmascarar `sql_text`; matriz de riesgos |
| Sustentación | Artefactos CRISP-DM y métricas honestas | ⚠️ Parcial | Guion por módulo; ensayo cronometrado; respuestas con conclusión |

> Detalle del plan de cierre en `docs/Plan_mejora_rubrica.md`.

---

## 7. Plan de trabajo hasta las entregas

Según tu cronograma (hoja CRISP-DM):

| Fecha | Hito | Qué entregar |
|---|---|---|
| **16 oct** | 90% (Evaluation + Deployment) | Modelo evaluado e integrado + escenario funcional completo ejecutándose de inicio a fin |
| **23 oct** | 100% (Deployment + cierre) | Producto terminado + pipeline + documentación + pruebas + evidencias + pre informe |

**Prioridad por puntos ganados:**

1. **Hasta el 16 oct:** integrar el modelo con la plataforma y poder mostrar el flujo completo (adecuación funcional); tabla de tiempos (eficiencia).
2. **Hasta el 20 oct:** registro de auditoría, matriz de roles y prueba 403/429 (seguridad y protección: 5 puntos); pruebas de falla (fiabilidad).
3. **Hasta el 23 oct:** manual de usuario y encuesta (interacción: 2.5 puntos); configuración externa (flexibilidad); matriz de riesgos (protección).
4. **Después:** ensayo de la sustentación con cronómetro.

---

## 8. Guion de demostración (10 minutos)

1. **Contexto (1 min):** problema de Steel Nort y objetivo del producto.
2. **Flujo principal en vivo (3 min):** recolección → anomalía detectada → alerta → diagnóstico en el dashboard → reporte.
3. **Seguridad y roles (2 min):** inicio de sesión con dos roles distintos; operación no permitida (403); registro de auditoría.
4. **Fiabilidad (1 min):** detener el recolector o simular una caída y mostrar la recuperación.
5. **Desempeño (1 min):** tabla de tiempos.
6. **Flexibilidad (1 min):** cambiar un umbral desde configuración y ver el efecto.
7. **Resultados y conclusión (1 min):** F1, Recall, cumplimiento de criterios, limitaciones y trazabilidad con los objetivos.

---

## 9. Observaciones sobre el sílabo

- La nota mínima aprobatoria del sílabo es **14**, pero el resumen de la rúbrica indica aprobado desde **13.5** (75.5%). Confirma cuál aplica con tu docente.
- En la rúbrica de **Flexibilidad**, el nivel "Debe mejorar" dice "flexible pero no escalable" y a la vez "soporta cambios y el crecimiento". Tiene una contradicción interna; apunta siempre al nivel Bueno y no dependas de esa redacción.
- Para la presentación final debes tener **acreditados los cuatro avances y la aprobación de tu asesor**; de lo contrario, la nota es cero.
- La rúbrica pide para Eficiencia "menos de 5 segundos", mientras tu proyecto fija ≤ 3 s (RNF2). Cumple el estándar más estricto.