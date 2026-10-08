# SteelNort — Funcionalidades Principales del Sistema

Manual funcional de los cinco módulos primarios de la plataforma SteelNort
(detección de anomalías de rendimiento OLTP): **Inicio de Sesión, Inicio,
Dashboard, Roles y Permisos**, y **Configuración**.

---

## 1. Inicio de Sesión (Login)

Vista pública de acceso a la plataforma.

### Funcionalidades

| Función | Descripción |
|---------|-------------|
| Autenticación | Valida correo electrónico y contraseña contra el backend (`POST /auth/login`). |
| Manejo de errores | Muestra el error en pantalla si falla la autenticación (credenciales inválidas, cuenta inactiva, etc.) y **no** redirige. |
| Redirección | Solo cuando la autenticación es exitosa, el usuario pasa a la vista **Inicio**. |
| Validación de formulario | Verifica en el cliente que correo y contraseña no estén vacíos. |
| Enlaces complementarios | "¿Olvidaste tu contraseña?", "Recordar contraseña" y redes sociales (Facebook, Instagram, WhatsApp). *(Placeholders/Mock en la versión actual)*. |

### Seguridad de la sesión (doble token)

- **JWT (access_token)**: se envía en el header `Authorization: Bearer` y se
  mantiene **solo en memoria** (al recargar la página se pierde y se debe volver
  a autenticar).
- **CSRF token**: se envía como cookie y en el header `X-CSRF-Token` en todo
  request de escritura (doble coincidencia; si no coincide, el backend responde 403).
- **Logout**: notifica al backend (`POST /auth/logout`), revoca la sesión y
  limpia el estado local del navegador.

---

## 2. Inicio (Vista Principal)

Pantalla de bienvenida tras iniciar sesión. Incluye encabezado con el **nombre y
rol del usuario** conectado y la barra lateral de navegación.

### Funcionalidades

| Widget | Descripción |
|--------|-------------|
| Tarjetas de indicadores (KPI) | **CPU** (última lectura %), **Memoria** (usada/total en MB), **Anomalías detectadas** (hoy) y **Sesiones activas**. |
| Telemetría en vivo | Lecturas de CPU y memoria actualizadas **cada 3 segundos** con un historial de 80 puntos. |
| Gráfico de uso de CPU | Línea de área con promedio del período y marca de la última lectura. |
| Gráfico de uso de memoria | Línea de área con promedio y tendencia de las últimas muestras. |
| Anomalías del día | Gráfico que resalta el **pico máximo de anomalías** por hora, con su valor y hora. |
| Alertas recientes | Listado de alertas ordenadas por severidad (Crítica, Alta, Media, Baja) con hora. *(Datos de ejemplo en la versión actual)*. |
| Estado del sistema | Estado de los servicios: Operativo, Degradado o Programado, con breve descripción. |
| Manejo de errores | Si no se puede conectar con las métricas, se muestra un aviso sin interrumpir la vista. |

---

## 3. Dashboard

Panel analítico de monitoreo del sistema OLTP.

### Funcionalidades

| Indicador | Descripción |
|-----------|-------------|
| Disponibilidad del sistema | Porcentaje de disponibilidad de los **últimos 7 días**, con gráfico por día (Lun–Dom). |
| Tasa de anomalías | Anomalías por minuto en la **hora actual**. |
| Rendimiento por consultas | **Duración promedio** de las consultas (ms) y gráfico de barras por día. |
| Sesiones transaccionales | Conteo de sesiones **activas / inactivas** en el momento. |
| Uso de recursos detallado | Comparativa en vivo de **CPU vs. Memoria** con leyenda y porcentaje actual. |
| Mapa de anomalías temporales | Heatmap del día (24 horas) en tres niveles de severidad: **Normal, Alerta baja, Alerta alta**. |

### Comportamiento de actualización

- CPU/Memoria: cada 3 segundos (historial 80 pts).
- Telemetría de nodo: cada 3 segundos.
- Heatmap de anomalías: cada 60 segundos.
- Disponibilidad: cada 5 minutos.
- Resumen de anomalías: cada 30 segundos.

---

## 4. Roles y Permisos

Gestión de roles de usuario y sus permisos por módulo.

### Funcionalidades

| Función | Descripción |
|---------|-------------|
| Listado de roles | Tabla con nombre, descripción y cantidad de permisos por rol; se selecciona un rol haciendo clic. |
| Crear rol | Modal "Nuevo rol" (nombre y descripción) → `POST /roles`. |
| Editar rol | Edición en línea de nombre y descripción → `PATCH /roles/{id}`. |
| Eliminar rol | Con confirmación previa → `DELETE /roles/{id}`. |
| Detalle del rol | Descripción, permisos asignados (x de total) y estado **Activo/Inactivo**. |
| Matriz de permisos | Permisos **agrupados por módulo**, cada uno con su clave y nombre. |
| Asignar / quitar permisos | Cada permiso es una casilla; al marcarla/desmarcarla se envía la lista completa (`POST /roles/{id}/permisos`). Si el guardado falla, la interfaz revierte y recarga los permisos del rol. |

---

## 5. Configuración

Parámetros administrativos de la plataforma.

### 5.1 Gestión de usuarios

- Tabla de **usuarios registrados**: avatar, nombre, correo y rol.
- **Crear usuario** mediante modal (`POST /usuarios`).
- Acciones de visualización y eliminación por usuario (el usuario con rol
  **Administrador** no muestra acciones de eliminación).

### 5.2 Conexión SQL Server (OLTP)

- Estado de conexión al servidor SQL y del **servidor de logs** (indicadores
  "Conectado" y "En línea").
- Botón **"Probar conexión"** contra el servidor configurado.

### 5.3 Modelo de aprendizaje

- Modelo de entrenamiento: **Isolation Forest**.
- Campo para indicar el modelo y botón **"Reentrenar modelo"**.
- **Umbral de anomalía** configurable (porcentaje).
- Opción para **ver las variables** de entrenamiento del modelo.

### 5.4 Importar carga de trabajo

| Elemento | Descripción |
|----------|-------------|
| Archivo CSV | Carga con las columnas de las variables del modelo (`nodo` y `fec` opcionales). |
| Nodo destino | Nodo al que se asigna la carga (opcional si el CSV trae la columna `nodo`). |
| Importar y separar | Envía el archivo (`POST /telemetria/import/csv`); el detector separa **normal vs. anomalía**. |
| Reporte de importación | Muestra total recibidas, evaluadas, **normales** y **anomalías**, además del detalle por nodo (descartadas en la primera ventana). |
| Reentrenamiento | Las muestras clasificadas como **normales** se usan para alimentar el reentrenamiento del modelo. |

---

## Resumen de módulos disponibles

| Módulo | Acceso | Módulos asociados |
|--------|--------|-------------------|
| Login | Público | Autenticación (JWT + CSRF) |
| Inicio | Logeado | KPIs, telemetría en vivo, alertas, estado del sistema |
| Dashboard | Logeado | Disponibilidad, rendimiento, sesiones, recursos, heatmap |
| Roles y Permisos | Logeado (Admin) | CRUD de roles y matriz de permisos |
| Configuración | Logeado (Admin) | Usuarios, conexión SQL, modelo ML, importación de cargas |