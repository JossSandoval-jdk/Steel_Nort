-- ============================================================
-- SteelNort — Diccionario de Datos
-- Sistema SCADA Industrial — Monitoreo y deteccion de anomalias
-- Motor: Microsoft SQL Server
--
-- Convencion de nombres:
--  * Tablas con nombres completos (Usuarios, Sesiones, ...).
--  * Columnas con prefijo de 3 letras de su tabla (usu_*, ses_*).
--  * Auditoria (4 ultimas columnas, uniformes en TODAS las tablas):
--      reg_usu  NVARCHAR(60)  NULL      -> quien creo el registro
--      fec_reg  DATETIME2     NOT NULL  -> cuando se creo
--      eli_usu  NVARCHAR(60)  NULL      -> quien elimino (baja logica)
--      fec_eli  DATETIME2     NULL      -> cuando se elimino (NULL = activo)
--
-- Leyenda de tipos:
--   PK  = Clave primaria       FK  = Clave foranea
--   NN  = NOT NULL (obligatorio)  NU = NULL (opcional)
-- ============================================================

/* ============================================================
   1. TABLA: Usuarios (prefijo usu)
   Descripcion: Usuarios del sistema y sus roles.
   FK salientes: --
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  usu_cod       | INT IDENTITY  | PK,NN | Codigo unico del usuario (PK).
--  usu_nom       | NVARCHAR(100) | NN    | Nombre completo del usuario.
--  usu_ema       | NVARCHAR(150) | NN    | Correo electronico (UNIQUE).
--  usu_pwd       | NVARCHAR(256) | NN    | Hash de la contrasena.
--  usu_rol       | NVARCHAR(30)  | NN    | Rol: Administrador|Supervisor|Operador (CHECK).
--  usu_ini       | NVARCHAR(4)   | NN    | Iniciales del usuario (avatar).
--  usu_act       | BIT           | NN    | Usuario activo (1=si, 0=no).
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).

/* ============================================================
   2. TABLA: Sesiones (prefijo ses)
   Descripcion: Historial de inicios/cierres de sesion.
   FK salientes: ses_usu -> Usuarios(usu_cod)
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  ses_cod       | INT IDENTITY  | PK,NN | Codigo unico de la sesion (PK).
--  ses_usu       | INT           | NN    | FK -> Usuarios(usu_cod). Usuario de la sesion.
--  ses_fec_ini   | DATETIME2     | NN    | Fecha/hora de inicio de la sesion.
--  ses_fec_fin   | DATETIME2     | NU    | Fecha/hora de cierre (NULL si sigue activa).
--  ses_ip        | NVARCHAR(45)  | NU    | Direccion IP de origen.
--  ses_usr_agt   | NVARCHAR(500) | NU    | User-Agent del navegador/cliente.
--  ses_est       | NVARCHAR(15)  | NN    | Estado: activa|cerrada|expirada (CHECK).
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).
--  INDICES: IX_ses_usu(ses_usu), IX_ses_est(ses_est)

/* ============================================================
   3. TABLA: Eventos_Sesion (prefijo evt)
   Descripcion: Eventos relevantes a lo largo de una sesion
                (alimenta el modulo Historia de Sesion).
   FK salientes: evt_ses -> Sesiones(ses_cod)
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  evt_cod       | INT IDENTITY  | PK,NN | Codigo unico del evento (PK).
--  evt_ses       | INT           | NN    | FK -> Sesiones(ses_cod). Sesion del evento.
--  evt_min       | INT           | NN    | Minuto de la sesion en que ocurrio.
--  evt_tip       | NVARCHAR(30)  | NN    | Tipo: login|lectura|api|advertencia|error|cierre (CHECK).
--  evt_desc      | NVARCHAR(200) | NN    | Descripcion corta del evento.
--  evt_color     | NVARCHAR(7)   | NN    | Color hexadecimal para la visualizacion.
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).
--  INDICES: IX_evt_ses(evt_ses)

/* ============================================================
   4. TABLA: Nodos_SCADA (prefijo ndo)
   Descripcion: Nodos/servidores SCADA monitoreados.
   FK salientes: --
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  ndo_cod       | INT IDENTITY  | PK,NN | Codigo unico del nodo (PK).
--  ndo_nom       | NVARCHAR(100) | NN    | Nombre del nodo.
--  ndo_ubic      | NVARCHAR(150) | NU    | Ubicacion fisica/logica.
--  ndo_ip        | NVARCHAR(45)  | NN    | Direccion IP del nodo.
--  ndo_tipo      | NVARCHAR(50)  | NN    | Tipo: scada|servidor|edge|plc (CHECK).
--  ndo_est       | NVARCHAR(20)  | NN    | Estado: operativo|degradado|offline|mantenimiento (CHECK).
--  ndo_uptime    | BIGINT        | NN    | Tiempo activo en segundos.
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).

/* ============================================================
   5. TABLA: Servicios (prefijo svc)
   Descripcion: Servicios por nodo (SCADA, BD, API, respaldos).
   FK salientes: svc_ndo -> Nodos_SCADA(ndo_cod)
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  svc_cod       | INT IDENTITY  | PK,NN | Codigo unico del servicio (PK).
--  svc_ndo       | INT           | NN    | FK -> Nodos_SCADA(ndo_cod). Nodo del servicio.
--  svc_nom       | NVARCHAR(100) | NN    | Nombre del servicio.
--  svc_desc      | NVARCHAR(200) | NU    | Descripcion del servicio.
--  svc_est       | NVARCHAR(20)  | NN    | Estado: operativo|degradado|detenido|programado (CHECK).
--  svc_uptime_pct| DECIMAL(5,2)  | NN    | Disponibilidad porcentual (0-100).
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).

/* ============================================================
   6. TABLA: Alertas (prefijo alt)
   Descripcion: HISTORICO CENTRAL y permanente. Cada anomalia
                confirmada se convierte en una alerta con severidad
                y diagnostico. Tabla central del negocio.
   FK salientes: alt_ndo -> Nodos_SCADA, alt_svc -> Servicios,
                 alt_usu -> Usuarios, alt_prd -> Predicciones_ML
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  alt_cod       | INT IDENTITY  | PK,NN | Codigo unico de la alerta (PK).
--  alt_ndo       | INT           | NU    | FK -> Nodos_SCADA(ndo_cod). Nodo implicado.
--  alt_svc       | INT           | NU    | FK -> Servicios(svc_cod). Servicio implicado.
--  alt_usu       | INT           | NU    | FK -> Usuarios(usu_cod). Usuario que la registra.
--  alt_prd       | INT           | NU    | FK -> Predicciones_ML(prd_cod). Prediccion origen.
--  alt_tipo      | NVARCHAR(50)  | NN    | Tipo de anomalia (ej. Pico de CPU, Latencia BD).
--  alt_sev       | NVARCHAR(15)  | NN    | Severidad: critica|alta|media|baja (CHECK).
--  alt_titulo    | NVARCHAR(200) | NN    | Titulo resumido de la alerta.
--  alt_diag      | NVARCHAR(500) | NU    | Diagnostico / causa.
--  alt_fec       | DATETIME2     | NN    | Fecha/hora de la alerta.
--  alt_resu      | BIT           | NN    | Resuelta (1=si, 0=no).
--  alt_fec_resu  | DATETIME2     | NU    | Fecha/hora de resolucion.
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).
--  INDICES: IX_alt_ndo, IX_alt_sev, IX_alt_fec, IX_alt_resu

/* ============================================================
   7. TABLA: Causas_Raiz (prefijo cra)
   Descripcion: Arbol recursivo de diagnosis por alerta
                (alimenta el modulo de Correlacion de Causa Raiz).
                Self-FK para estructura de arbol.
   FK salientes: cra_alt -> Alertas(alt_cod), cra_padre -> Causas_Raiz(cra_cod)
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  cra_cod       | INT IDENTITY  | PK,NN | Codigo unico del nodo de causa (PK).
--  cra_alt       | INT           | NN    | FK -> Alertas(alt_cod). Alerta asociada.
--  cra_padre     | INT           | NU    | FK -> Causas_Raiz(cra_cod). Nodo padre (NULL=raiz raiz).
--  cra_nivel     | NVARCHAR(10)  | NN    | Nivel: root|warn|leaf (CHECK).
--  cra_etiq      | NVARCHAR(200) | NN    | Etiqueta de la causa.
--  cra_tono      | NVARCHAR(10)  | NN    | Tono/color para la visualizacion.
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).
--  INDICES: IX_cra_alt(cra_alt)

/* ============================================================
   8. TABLA: Heatmap_Anomalias (prefijo hma)
   Descripcion: Agregado ligero dia/hora/severidad alimentado
                SOLO por el conteo de anomalias (no por telemetria)
                para el Mapa de anomalias del Dashboard.
   FK salientes: --
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  hma_cod       | INT IDENTITY  | PK,NN | Codigo unico del registro (PK).
--  hma_fec       | DATE          | NN    | Fecha del agregado.
--  hma_hora      | TINYINT       | NN    | Hora (0-23) (CHECK).
--  hma_sev       | NVARCHAR(15)  | NN    | Severidad: normal|alerta_baja|alerta_alta (CHECK).
--  hma_cant      | INT           | NN    | Conteo de anomalias en esa celda.
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).
--  UNICO: UQ_hma(hma_fec, hma_hora, hma_sev)
--  INDICES: IX_hma_fec(hma_fec)

/* ============================================================
   9. TABLA: Configuracion_Sistema (prefijo cfg)
   Descripcion: Parametros clave-valor del sistema (umbral de
                anomalia, modelo activo, host de logs, etc.).
   FK salientes: --
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  cfg_cod       | INT IDENTITY  | PK,NN | Codigo unico del parametro (PK).
--  cfg_clave     | NVARCHAR(100) | NN    | Clave del parametro (UNIQUE).
--  cfg_valor     | NVARCHAR(500) | NN    | Valor del parametro.
--  cfg_desc      | NVARCHAR(200) | NU    | Descripcion opcional.
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).

/* ============================================================
   10. TABLA: Modelos_ML (prefijo mdl)
   Descripcion: Metadatos del modelo de deteccion de anomalias.
                El dataset de entrenamiento es EXTERNO (CSV/notebook),
                aqui solo se registran configuracion y artefacto.
   FK salientes: --
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  mdl_cod       | INT IDENTITY  | PK,NN | Codigo unico del modelo (PK).
--  mdl_nom       | NVARCHAR(100) | NN    | Nombre del modelo.
--  mdl_tipo      | NVARCHAR(50)  | NN    | Tipo: isolation_forest|autoencoder|lstm|random_forest|xgboost|otro (CHECK).
--  mdl_umbral_pct| DECIMAL(5,2)  | NN    | Umbral de anomalia en porcentaje (por defecto 85).
--  mdl_vars      | NVARCHAR(MAX) | NU    | JSON: lista de features usadas.
--  mdl_hparms    | NVARCHAR(MAX) | NU    | JSON: hiperparametros del modelo.
--  mdl_ruta_art  | NVARCHAR(500) | NU    | Ruta del artefacto serializado (.pkl/.joblib/.onnx).
--  mdl_act       | BIT           | NN    | Modelo activo (1=si, 0=no).
--  mdl_fec_entr  | DATETIME2     | NU    | Fecha/hora de ultimo entrenamiento.
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).
--  INDICES: IX_mdl_act(mdl_act)

/* ============================================================
   11. TABLA: Reportes (prefijo rpt)
   Descripcion: Reportes generados para el negocio.
   FK salientes: rpt_usu -> Usuarios(usu_cod)
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  rpt_cod       | INT IDENTITY  | PK,NN | Codigo unico del reporte (PK).
--  rpt_usu       | INT           | NN    | FK -> Usuarios(usu_cod). Usuario que lo solicito.
--  rpt_tipo      | NVARCHAR(50)  | NN    | Tipo: alertas|metricas|disponibilidad|anomalias|sesiones|general (CHECK).
--  rpt_titulo    | NVARCHAR(200) | NN    | Titulo del reporte.
--  rpt_params    | NVARCHAR(MAX) | NU    | JSON: parametros del reporte.
--  rpt_ruta_arch | NVARCHAR(500) | NU    | Ruta del archivo generado.
--  rpt_est       | NVARCHAR(20)  | NN    | Estado: generando|completado|error (CHECK).
--  rpt_fec_gen   | DATETIME2     | NN    | Fecha/hora de generacion.
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).
--  INDICES: IX_rpt_usu(rpt_usu), IX_rpt_tipo(rpt_tipo)

/* ============================================================
   12. TABLA: Predicciones_ML (prefijo prd) — SOLO ANOMALIAS
   Descripcion: Resultado del detector que corre en tiempo real en
                el navegador. SOLO se persisten las muestras con
                anomalia (prd_es_anom = 1), no la telemetria normal.
   FK salientes: prd_mdl -> Modelos_ML(mdl_cod), prd_ndo -> Nodos_SCADA(ndo_cod)
   ============================================================ */
--  Columna       | Tipo          | NN/NU | Descripcion
--  --------------+---------------+-------+-------------------------------------------
--  prd_cod       | INT IDENTITY  | PK,NN | Codigo unico de la prediccion (PK).
--  prd_mdl       | INT           | NN    | FK -> Modelos_ML(mdl_cod). Modelo usado.
--  prd_ndo       | INT           | NN    | FK -> Nodos_SCADA(ndo_cod). Nodo analizado.
--  prd_fec       | DATETIME2     | NN    | Fecha/hora de la muestra.
--  prd_es_anom   | BIT           | NN    | Es anomalia (siempre 1 en esta tabla).
--  prd_score     | DECIMAL(6,4)  | NN    | Score de anomalia del modelo (0-1).
--  prd_umbral    | DECIMAL(5,2)  | NN    | Umbral aplicado en porcentaje.
--  prd_feats     | NVARCHAR(MAX) | NU    | JSON: snapshot ligero de features implicadas (top N).
--  prd_expl      | NVARCHAR(MAX) | NU    | JSON: explicacion/causa de la anomalia.
--  reg_usu       | NVARCHAR(60)  | NU    | Auditoria: quien creo.
--  fec_reg       | DATETIME2     | NN    | Auditoria: cuando se creo.
--  eli_usu       | NVARCHAR(60)  | NU    | Auditoria: quien elimino (baja logica).
--  fec_eli       | DATETIME2     | NU    | Auditoria: cuando se elimino (NULL=activo).
--  INDICES: IX_prd_mdl(prd_mdl,prd_fec), IX_prd_ndo(prd_ndo,prd_fec), IX_prd_es(prd_es_anom)

/* ============================================================
   RESUMEN DE RELACIONES (FK)
   ============================================================
   Sesiones.ses_usu            -> Usuarios.usu_cod
   Eventos_Sesion.evt_ses      -> Sesiones.ses_cod
   Servicios.svc_ndo           -> Nodos_SCADA.ndo_cod
   Alertas.alt_ndo             -> Nodos_SCADA.ndo_cod
   Alertas.alt_svc             -> Servicios.svc_cod
   Alertas.alt_usu             -> Usuarios.usu_cod
   Alertas.alt_prd             -> Predicciones_ML.prd_cod   (FK diferida)
   Causas_Raiz.cra_alt         -> Alertas.alt_cod
   Causas_Raiz.cra_padre       -> Causas_Raiz.cra_cod       (self-FK)
   Reportes.rpt_usu            -> Usuarios.usu_cod
   Predicciones_ML.prd_mdl     -> Modelos_ML.mdl_cod
   Predicciones_ML.prd_ndo     -> Nodos_SCADA.ndo_cod
   ============================================================ */
