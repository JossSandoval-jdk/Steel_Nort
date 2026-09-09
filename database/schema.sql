-- ============================================================
-- SteelNort — SQL Server Schema
-- Sistema SCADA Industrial — Monitoreo y deteccion de anomalias
-- Motor: Microsoft SQL Server
--
-- DISENO CLAVE (streaming, sin sobrecarga de recursos):
--  * La telemetria cruda (~55 metricas cada 7s) NO se persiste.
--    El modelo de ML corre en el navegador (tiempo real) y cada
--    muestra se evalua en memoria y se descarta.
--  * A la BD solo llega LO CLAVE para el negocio: eventos de
--    anomalia y alertas. Se evita guardar logs/metricas/eventos
--    masivos que consumirian demasiados recursos.
--  * El dataset de entrenamiento es EXTERNO (CSV/notebook), NO
--    se almacena en esta base operativa.
--
-- CONVENCION DE NOMBRES:
--  * Nombres de tablas COMPLETOS: Usuarios, Sesiones,
--    Eventos_Sesion, Nodos_SCADA, Servicios, Alertas,
--    Causas_Raiz, Heatmap_Anomalias, Configuracion_Sistema,
--    Modelos_ML, Reportes, Predicciones_ML.
--  * Cada columna lleva el prefijo de 3 letras de su tabla mas
--    una abreviatura corta (ej: usu_cod, usu_nom, usu_ema).
--  * Las 4 ultimas columnas de cada tabla son la auditoria de
--    baja logica (uniformes en todas las tablas):
--      - reg_usu : quien creo el registro
--      - fec_reg : cuando se creo
--      - eli_usu : quien elimino (baja logica)
--      - fec_eli : cuando se elimino (NULL = activo)
-- ============================================================

IF DB_ID('SteelNort') IS NULL
    CREATE DATABASE SteelNort;
GO

USE SteelNort;
GO

-- ============================================================
-- 1. USUARIOS (prefijo usu)
-- ============================================================
CREATE TABLE Usuarios (
    usu_cod         INT IDENTITY(1,1) PRIMARY KEY,
    usu_nom         NVARCHAR(100)   NOT NULL,
    usu_ema         NVARCHAR(150)   NOT NULL UNIQUE,
    usu_pwd         NVARCHAR(256)   NOT NULL,
    usu_rol         NVARCHAR(30)    NOT NULL CHECK (usu_rol IN ('Administrador','Supervisor','Operador')),
    usu_ini         NVARCHAR(4)     NOT NULL,
    usu_act         BIT             NOT NULL DEFAULT 1,
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL
);
GO

-- ============================================================
-- 2. SESIONES (prefijo ses)
-- ============================================================
CREATE TABLE Sesiones (
    ses_cod         INT IDENTITY(1,1) PRIMARY KEY,
    ses_usu         INT             NOT NULL,
    ses_fec_ini     DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    ses_fec_fin     DATETIME2       NULL,
    ses_ip          NVARCHAR(45)    NULL,
    ses_usr_agt     NVARCHAR(500)   NULL,
    ses_est         NVARCHAR(15)    NOT NULL DEFAULT 'activa'
                        CHECK (ses_est IN ('activa','cerrada','expirada')),
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL,
    FOREIGN KEY (ses_usu) REFERENCES Usuarios(usu_cod)
);
GO

-- ============================================================
-- 3. EVENTOS_SESION (prefijo evt)
-- Eventos relevantes de una sesion (alimenta HistoriaSesion).
-- Volumen bajo: solo eventos, no trazas masivas.
-- ============================================================
CREATE TABLE Eventos_Sesion (
    evt_cod         INT IDENTITY(1,1) PRIMARY KEY,
    evt_ses         INT             NOT NULL,
    evt_min         INT             NOT NULL,
    evt_tip         NVARCHAR(30)    NOT NULL
                        CHECK (evt_tip IN ('login','lectura','api','advertencia','error','cierre')),
    evt_desc        NVARCHAR(200)   NOT NULL,
    evt_color       NVARCHAR(7)     NOT NULL,
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL,
    FOREIGN KEY (evt_ses) REFERENCES Sesiones(ses_cod)
);
GO

-- ============================================================
-- 4. NODOS_SCADA (prefijo ndo)
-- ============================================================
CREATE TABLE Nodos_SCADA (
    ndo_cod         INT IDENTITY(1,1) PRIMARY KEY,
    ndo_nom         NVARCHAR(100)   NOT NULL,
    ndo_ubic        NVARCHAR(150)   NULL,
    ndo_ip          NVARCHAR(45)    NOT NULL,
    ndo_tipo        NVARCHAR(50)    NOT NULL DEFAULT 'scada'
                        CHECK (ndo_tipo IN ('scada','servidor','edge','plc')),
    ndo_est         NVARCHAR(20)    NOT NULL DEFAULT 'operativo'
                        CHECK (ndo_est IN ('operativo','degradado','offline','mantenimiento')),
    ndo_uptime      BIGINT          NOT NULL DEFAULT 0,
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL
);
GO

-- ============================================================
-- 5. SERVICIOS (prefijo svc)
-- ============================================================
CREATE TABLE Servicios (
    svc_cod         INT IDENTITY(1,1) PRIMARY KEY,
    svc_ndo         INT             NOT NULL,
    svc_nom         NVARCHAR(100)   NOT NULL,
    svc_desc        NVARCHAR(200)   NULL,
    svc_est         NVARCHAR(20)    NOT NULL DEFAULT 'operativo'
                        CHECK (svc_est IN ('operativo','degradado','detenido','programado')),
    svc_uptime_pct  DECIMAL(5,2)    NOT NULL DEFAULT 100.00,
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL,
    FOREIGN KEY (svc_ndo) REFERENCES Nodos_SCADA(ndo_cod)
);
GO

-- ============================================================
-- 6. ALERTAS (prefijo alt)
-- Historia CENTRAL y permanente del negocio: cada anomalia
-- confirmada desde el navegador se convierte en una alerta con
-- severidad y diagnostico. Se conserva completo (historico).
-- ============================================================
CREATE TABLE Alertas (
    alt_cod         INT IDENTITY(1,1) PRIMARY KEY,
    alt_ndo         INT             NULL,
    alt_svc         INT             NULL,
    alt_usu         INT             NULL,
    alt_prd         INT             NULL,
    alt_tipo        NVARCHAR(50)    NOT NULL,
    alt_sev         NVARCHAR(15)    NOT NULL
                        CHECK (alt_sev IN ('critica','alta','media','baja')),
    alt_titulo      NVARCHAR(200)   NOT NULL,
    alt_diag        NVARCHAR(500)   NULL,
    alt_fec         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    alt_resu        BIT             NOT NULL DEFAULT 0,
    alt_fec_resu    DATETIME2       NULL,
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL,
    FOREIGN KEY (alt_ndo) REFERENCES Nodos_SCADA(ndo_cod),
    FOREIGN KEY (alt_svc) REFERENCES Servicios(svc_cod),
    FOREIGN KEY (alt_usu) REFERENCES Usuarios(usu_cod)
);
GO

-- ============================================================
-- 7. CAUSAS_RAIZ (prefijo cra)
-- Arbol de diagnosis por alerta (alimenta CorrelacionRaiz).
-- ============================================================
CREATE TABLE Causas_Raiz (
    cra_cod         INT IDENTITY(1,1) PRIMARY KEY,
    cra_alt         INT             NOT NULL,
    cra_padre       INT             NULL,
    cra_nivel       NVARCHAR(10)    NOT NULL
                        CHECK (cra_nivel IN ('root','warn','leaf')),
    cra_etiq        NVARCHAR(200)   NOT NULL,
    cra_tono        NVARCHAR(10)    NOT NULL,
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL,
    FOREIGN KEY (cra_alt)   REFERENCES Alertas(alt_cod),
    FOREIGN KEY (cra_padre) REFERENCES Causas_Raiz(cra_cod)
);
GO

-- ============================================================
-- 8. HEATMAP_ANOMALIAS (prefijo hma)
-- Agregado ligero dia/hora/severidad, alimentado solo por el
-- conteo de anomalias (NO por telemetria). Permite el Mapa de
-- anomalias del Dashboard sin persistir la telemetria cruda.
-- ============================================================
CREATE TABLE Heatmap_Anomalias (
    hma_cod         INT IDENTITY(1,1) PRIMARY KEY,
    hma_fec         DATE            NOT NULL,
    hma_hora        TINYINT         NOT NULL CHECK (hma_hora BETWEEN 0 AND 23),
    hma_sev         NVARCHAR(15)    NOT NULL
                        CHECK (hma_sev IN ('normal','alerta_baja','alerta_alta')),
    hma_cant        INT             NOT NULL DEFAULT 0,
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL,
    CONSTRAINT UQ_hma UNIQUE (hma_fec, hma_hora, hma_sev)
);
GO

-- ============================================================
-- 9. CONFIGURACION_SISTEMA (prefijo cfg)
-- Parametros del sistema (alimenta Configuracion): umbral,
-- modelo activo, host de logs, etc.
-- ============================================================
CREATE TABLE Configuracion_Sistema (
    cfg_cod         INT IDENTITY(1,1) PRIMARY KEY,
    cfg_clave       NVARCHAR(100)   NOT NULL UNIQUE,
    cfg_valor       NVARCHAR(500)   NOT NULL,
    cfg_desc        NVARCHAR(200)   NULL,
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL
);
GO

-- ============================================================
-- 10. MODELOS_ML (prefijo mdl)
-- Metadatos del modelo de deteccion de anomalias.
-- NOTA: el dataset de entrenamiento es EXTERNO (CSV/notebook);
-- aqui solo se registran la configuracion y el artefacto usado.
-- ============================================================
CREATE TABLE Modelos_ML (
    mdl_cod         INT IDENTITY(1,1) PRIMARY KEY,
    mdl_nom         NVARCHAR(100)   NOT NULL,
    mdl_tipo        NVARCHAR(50)    NOT NULL DEFAULT 'isolation_forest'
                        CHECK (mdl_tipo IN ('isolation_forest','autoencoder','lstm','random_forest','xgboost','otro')),
    mdl_umbral_pct  DECIMAL(5,2)    NOT NULL DEFAULT 85.00,
    mdl_vars        NVARCHAR(MAX)   NULL,
    mdl_hparms      NVARCHAR(MAX)   NULL,
    mdl_ruta_art    NVARCHAR(500)   NULL,
    mdl_act         BIT             NOT NULL DEFAULT 0,
    mdl_fec_entr    DATETIME2       NULL,
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL
);
GO

-- ============================================================
-- 11. REPORTES (prefijo rpt)
-- Reportes generados para el negocio.
-- ============================================================
CREATE TABLE Reportes (
    rpt_cod         INT IDENTITY(1,1) PRIMARY KEY,
    rpt_usu         INT             NOT NULL,
    rpt_tipo        NVARCHAR(50)    NOT NULL
                        CHECK (rpt_tipo IN ('alertas','metricas','disponibilidad','anomalias','sesiones','general')),
    rpt_titulo      NVARCHAR(200)   NOT NULL,
    rpt_params      NVARCHAR(MAX)   NULL,
    rpt_ruta_arch   NVARCHAR(500)   NULL,
    rpt_est         NVARCHAR(20)    NOT NULL DEFAULT 'generando'
                        CHECK (rpt_est IN ('generando','completado','error')),
    rpt_fec_gen     DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL,
    FOREIGN KEY (rpt_usu) REFERENCES Usuarios(usu_cod)
);
GO

-- ============================================================
-- 12. PREDICCIONES_ML (prefijo prd) — SOLO ANOMALIAS
-- Resultado del detector que corre en tiempo real en el
-- navegador. SOLO se persisten las muestras marcadas como
-- anomalia (es_anomalia = 1), descartando la telemetria normal
-- para no consumir recursos.
-- ============================================================
CREATE TABLE Predicciones_ML (
    prd_cod         INT IDENTITY(1,1) PRIMARY KEY,
    prd_mdl         INT             NOT NULL,
    prd_ndo         INT             NOT NULL,
    prd_fec         DATETIME2       NOT NULL,
    prd_es_anom     BIT             NOT NULL,
    prd_score       DECIMAL(6,4)    NOT NULL,
    prd_umbral      DECIMAL(5,2)    NOT NULL,
    prd_feats       NVARCHAR(MAX)   NULL,
    prd_expl        NVARCHAR(MAX)   NULL,
    reg_usu         NVARCHAR(60)    NULL,
    fec_reg         DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    eli_usu         NVARCHAR(60)    NULL,
    fec_eli         DATETIME2       NULL,
    FOREIGN KEY (prd_mdl) REFERENCES Modelos_ML(mdl_cod),
    FOREIGN KEY (prd_ndo) REFERENCES Nodos_SCADA(ndo_cod)
);
GO

-- ============================================================
-- Correccion: FK de Alertas.alt_prd
-- (se agrega despues de crear Predicciones_ML)
-- ============================================================
ALTER TABLE Alertas
    WITH CHECK ADD CONSTRAINT FK_alt_prd
    FOREIGN KEY (alt_prd) REFERENCES Predicciones_ML(prd_cod);
GO

-- ============================================================
-- INDICES
-- ============================================================

-- Sesiones
CREATE INDEX IX_ses_usu    ON Sesiones(ses_usu);
CREATE INDEX IX_ses_est    ON Sesiones(ses_est);

-- Eventos_Sesion
CREATE INDEX IX_evt_ses    ON Eventos_Sesion(evt_ses);

-- Alertas (historico permanente, consultas frecuentes)
CREATE INDEX IX_alt_ndo    ON Alertas(alt_ndo);
CREATE INDEX IX_alt_sev    ON Alertas(alt_sev);
CREATE INDEX IX_alt_fec    ON Alertas(alt_fec);
CREATE INDEX IX_alt_resu   ON Alertas(alt_resu);

-- Causas_Raiz
CREATE INDEX IX_cra_alt    ON Causas_Raiz(cra_alt);

-- Heatmap_Anomalias
CREATE INDEX IX_hma_fec    ON Heatmap_Anomalias(hma_fec);

-- Predicciones_ML (solo anomalias, consultas por modelo/nodo/rango)
CREATE INDEX IX_prd_mdl    ON Predicciones_ML(prd_mdl, prd_fec);
CREATE INDEX IX_prd_ndo    ON Predicciones_ML(prd_ndo, prd_fec);
CREATE INDEX IX_prd_es     ON Predicciones_ML(prd_es_anom);

-- Modelos_ML
CREATE INDEX IX_mdl_act    ON Modelos_ML(mdl_act);

-- Reportes
CREATE INDEX IX_rpt_usu    ON Reportes(rpt_usu);
CREATE INDEX IX_rpt_tipo   ON Reportes(rpt_tipo);
GO
