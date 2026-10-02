/* ============================================================================
   SteelNort — Esquema de la base de monitoreo
   GENERADO DESDE: database/bdSteelNort.dbml   (fuente unica de verdad)

   21 tablas / 193 columnas.
   Particion por mes solo en las 4 tablas de datos crudos.

   ---------------------------------------------------------------------------
   ADVERTENCIA
   Este archivo CREA la base `bdSteelNort`. No lo ejecutes contra el servidor
   de desarrollo sin revisar el bloque de CREATE DATABASE: tu instancia ya
   tiene `bd_steelNort` (OLTP, con venta/factura/kardex), que es OTRA base
   y no se toca aqui. Para probarlo sobre una copia, cambia el nombre o
   levanta antes un SQLCMD :r con otro destino.
   ---------------------------------------------------------------------------

   DECISIONES QUE VIENEN DEL DISENO (no son detalles de SQL Server)

   1) PREDICCIONES_ML NO SE PARTICIONA, a proposito.
      Es lo que permite que prd_cod siga siendo UNICO y, con el, que las
      FK alt_prd / met_prd / eve_prd / lgs_prd existan de verdad. Si
      particionaramos predicciones_ml, SQL Server exigiria que cada FK
      leadante llevara tambien prd_ini, y habria que duplicar la columna
      de particion en 5 tablas para no perder integridad. Con ~1.200
      ventanas/dia la particion no aporta tanto como cuesta.

   2) LAS 4 TABLAS CRUDAS SI SE PARTICIONAN, porque si crecen de verdad:
      metricas (12.285 filas/dia), eventos y logs_sql (altisimo volumen) y
      estadisticas_carga. Con PK compuesta + columna de particion.

   3) UNA FK DESDE UNA TABLA PARTICIONADA HACIA UNA NO PARTICIONADA SI SE
      PERMITE. Lo que no se permite es al reves: una tabla particionada no
      puede ser referenciada por una FK que no incluya la columna de
      particion. Por eso met_prd/eve_prd/lgs_prd siguen apuntando a
      predicciones_ml.prd_cod.

   4) hma_sev TIENE 3 NIVELES Y alt_sev TIENE 4. La correspondencia no es
      identidad, esta en el trigger TR_alertas_hma_rollup:
        alt_sev  C (critica) -> hma_sev A (alta)
        alt_sev  A (alta)    -> hma_sev A (alta)
        alt_sev  M (media)   -> hma_sev B (baja)
        alt_sev  B (baja)    -> hma_sev B (baja)
      Asi el mapa de calor no puede mostrar mas contraste del que la
      deteccion realmente tiene.

   5) TIMESTAMP EN EL DBML = DATETIME2 EN SQL SERVER. El tipo `timestamp`
      de T-SQL es rowversion (un contador binario), no una fecha; usarlo
      como fecha habria sido un error silencioso.
   ============================================================================ */

USE master;
GO

IF DB_ID('bdSteelNort') IS NULL
BEGIN
    PRINT 'Creando base bdSteelNort...';
    EXEC ('CREATE DATABASE bdSteelNort');
END
ELSE
    PRINT 'La base bdSteelNort ya existe: no se crea ni se modifica.';
GO

USE bdSteelNort;
GO

SET NOCOUNT ON;
GO

/* ============================================================================
   1. PARTICIONAMIENTO
   ============================================================================ */

-- Un unico rango por mes. El ultimo MAXVALUE es la red de seguridad: si
-- el collector se cae un mes y nadie roda el particionado, los INSERT
-- siguen entrando en vez de rebotar con error.
CREATE PARTITION FUNCTION PF_Mes (datetime2(3))
AS RANGE RIGHT FOR VALUES
(
    '2026-01-01T00:00:00.000', '2026-02-01T00:00:00.000',
    '2026-03-01T00:00:00.000', '2026-04-01T00:00:00.000',
    '2026-05-01T00:00:00.000', '2026-06-01T00:00:00.000',
    '2026-07-01T00:00:00.000', '2026-08-01T00:00:00.000',
    '2026-09-01T00:00:00.000', '2026-10-01T00:00:00.000',
    '2026-11-01T00:00:00.000', '2026-12-01T00:00:00.000'
);
GO

CREATE PARTITION SCHEME PS_Mes
AS PARTITION PF_Mes ALL TO ([PRIMARY]);
GO


/* ============================================================================
   2. ACCESO
   Estas 4 tablas conservan la auditoria completa (reg_usu / fec_reg /
   eli_usu / fec_eli). Aqui la baja logica es real y hace falta saber
   quien y cuando. `usuario` va primero en el grafo porque `rol` no
   depende de nadie: se crea rol -> permiso -> usuario -> rol_permiso.
   ============================================================================ */

CREATE TABLE dbo.rol (
    rol_cod  int           IDENTITY(1,1) NOT NULL,
    rol_nom  varchar(50)   NOT NULL,
    rol_est  char(1)       NOT NULL CONSTRAINT DF_rol_est      DEFAULT 'A',
    reg_usu  int           NULL,
    fec_reg  datetime2(3)  NOT NULL CONSTRAINT DF_rol_fec_reg  DEFAULT SYSUTCDATETIME(),
    eli_usu  int           NULL,
    fec_eli  datetime2(3)  NULL,
    CONSTRAINT PK_rol PRIMARY KEY CLUSTERED (rol_cod),
    CONSTRAINT UQ_rol_nom UNIQUE (rol_nom),
    CONSTRAINT CK_rol_est CHECK (rol_est IN ('A','I'))
);
GO

CREATE TABLE dbo.permiso (
    per_cod  int           IDENTITY(1,1) NOT NULL,
    per_acc  varchar(30)   NOT NULL,
    per_mod  varchar(30)   NOT NULL,
    per_est  char(1)       NOT NULL CONSTRAINT DF_per_est      DEFAULT 'A',
    reg_usu  int           NULL,
    fec_reg  datetime2(3)  NOT NULL CONSTRAINT DF_per_fec_reg  DEFAULT SYSUTCDATETIME(),
    eli_usu  int           NULL,
    fec_eli  datetime2(3)  NULL,
    CONSTRAINT PK_permiso PRIMARY KEY CLUSTERED (per_cod),
    CONSTRAINT UQ_permiso UNIQUE (per_mod, per_acc),
    CONSTRAINT CK_per_est CHECK (per_est IN ('A','I'))
);
GO

-- Sin FK en reg_usu/eli_usu a proposito: el primer usuario no tendria a
-- quien apuntar, y una auto-FK bloquearia el bootstrap.
CREATE TABLE dbo.usuario (
    usu_cod  int           IDENTITY(1,1) NOT NULL,
    usu_nom  varchar(100)  NOT NULL,
    usu_log  varchar(50)   NOT NULL,
    usu_cla  varchar(255)  NOT NULL,
    usu_ema  varchar(100)  NULL,
    usu_dni  char(12)      NOT NULL,
    usu_tel  varchar(20)   NULL,
    usu_est  char(1)       NOT NULL CONSTRAINT DF_usu_est      DEFAULT 'A',
    rol_cod  int           NOT NULL,
    reg_usu  int           NULL,
    fec_reg  datetime2(3)  NOT NULL CONSTRAINT DF_usu_fec_reg  DEFAULT SYSUTCDATETIME(),
    eli_usu  int           NULL,
    fec_eli  datetime2(3)  NULL,
    CONSTRAINT PK_usuario PRIMARY KEY CLUSTERED (usu_cod),
    CONSTRAINT UQ_usu_log UNIQUE (usu_log),
    CONSTRAINT UQ_usu_dni UNIQUE (usu_dni),
    CONSTRAINT CK_usu_est CHECK (usu_est IN ('A','I')),
    CONSTRAINT FK_usuario_rol FOREIGN KEY (rol_cod) REFERENCES dbo.rol (rol_cod)
);
GO

CREATE TABLE dbo.rol_permiso (
    rp_cod   int           IDENTITY(1,1) NOT NULL,
    rol_cod  int           NOT NULL,
    per_cod  int           NOT NULL,
    rp_est   char(1)       NOT NULL CONSTRAINT DF_rp_est       DEFAULT 'A',
    reg_usu  int           NULL,
    fec_reg  datetime2(3)  NOT NULL CONSTRAINT DF_rp_fec_reg   DEFAULT SYSUTCDATETIME(),
    eli_usu  int           NULL,
    fec_eli  datetime2(3)  NULL,
    CONSTRAINT PK_rol_permiso PRIMARY KEY CLUSTERED (rp_cod),
    CONSTRAINT UQ_rol_permiso UNIQUE (rol_cod, per_cod),
    CONSTRAINT CK_rp_est  CHECK (rp_est  IN ('A','I')),
    CONSTRAINT FK_rp_rol  FOREIGN KEY (rol_cod) REFERENCES dbo.rol     (rol_cod),
    CONSTRAINT FK_rp_per  FOREIGN KEY (per_cod) REFERENCES dbo.permiso (per_cod),
    CONSTRAINT FK_rp_reg  FOREIGN KEY (reg_usu) REFERENCES dbo.usuario (usu_cod),
    CONSTRAINT FK_rp_eli  FOREIGN KEY (eli_usu) REFERENCES dbo.usuario (usu_cod)
);
GO

-- ses_usr_agt eliminado: se guardaba pero no se leia en ningun lado.
CREATE TABLE dbo.sesiones (
    ses_cod     int           IDENTITY(1,1) NOT NULL,
    ses_usu     int           NOT NULL,
    ses_fec_ini datetime2(3)  NOT NULL CONSTRAINT DF_ses_fec_ini DEFAULT SYSUTCDATETIME(),
    ses_fec_fin datetime2(3)  NULL,
    ses_ip      varchar(45)   NULL,
    ses_est     char(1)       NOT NULL CONSTRAINT DF_ses_est    DEFAULT 'A',
    fec_reg     datetime2(3)  NOT NULL CONSTRAINT DF_ses_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_sesiones PRIMARY KEY CLUSTERED (ses_cod),
    CONSTRAINT CK_ses_est  CHECK (ses_est  IN ('A','C','E')),
    CONSTRAINT CK_ses_vent CHECK (ses_fec_fin IS NULL OR ses_fec_fin >= ses_fec_ini),
    CONSTRAINT FK_ses_usu FOREIGN KEY (ses_usu) REFERENCES dbo.usuario (usu_cod)
);
GO

CREATE INDEX IX_ses_usu ON dbo.sesiones (ses_usu);
CREATE INDEX IX_ses_est  ON dbo.sesiones (ses_est);
GO


/* ============================================================================
   3. QUE SE MONITOREA Y DESDE DONDE SE ORIGINA LA CARGA
   ============================================================================ */

CREATE TABLE dbo.instancias (
    ins_cod      int           IDENTITY(1,1) NOT NULL,
    ins_nom      varchar(100)  NOT NULL,
    ins_host     varchar(150)  NOT NULL,
    ins_puerto   int           NOT NULL CONSTRAINT DF_ins_puerto    DEFAULT 1433,
    ins_fec_alta datetime2(3)  NULL,
    ins_est      char(1)       NOT NULL CONSTRAINT DF_ins_est       DEFAULT 'A',
    fec_reg      datetime2(3)  NOT NULL CONSTRAINT DF_ins_fec_reg   DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_instancias PRIMARY KEY CLUSTERED (ins_cod),
    CONSTRAINT UQ_instancia UNIQUE (ins_host, ins_puerto),
    CONSTRAINT CK_ins_est CHECK (ins_est IN ('A','I')),
    CONSTRAINT CK_ins_puerto CHECK (ins_puerto BETWEEN 1 AND 65535)
);
GO

-- ssq_host y ssq_prog son los unicos campos que sirven: se verifico que
-- las conexiones usaban el mismo login, asi que ssq_usr solo produce
-- filas identicas. Host y program_name si las distinguen.
CREATE TABLE dbo.sesiones_sql (
    ssq_cod     int           IDENTITY(1,1) NOT NULL,
    ssq_ins     int           NOT NULL,
    ssq_sid     int           NOT NULL,
    ssq_usr     varchar(128)  NULL,
    ssq_host    varchar(150)  NULL,
    ssq_prog    varchar(100)  NULL,
    ssq_fec_ini datetime2(3)  NOT NULL,
    ssq_fec_fin datetime2(3)  NULL,
    ssq_est     char(1)       NOT NULL CONSTRAINT DF_ssq_est     DEFAULT 'A',
    fec_reg     datetime2(3)  NOT NULL CONSTRAINT DF_ssq_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_sesiones_sql PRIMARY KEY CLUSTERED (ssq_cod),
    CONSTRAINT UQ_ssq UNIQUE (ssq_ins, ssq_sid, ssq_fec_ini),
    CONSTRAINT CK_ssq_est  CHECK (ssq_est  IN ('A','C')),
    CONSTRAINT CK_ssq_vent CHECK (ssq_fec_fin IS NULL OR ssq_fec_fin >= ssq_fec_ini),
    CONSTRAINT FK_ssq_ins FOREIGN KEY (ssq_ins) REFERENCES dbo.instancias (ins_cod)
);
GO


/* ============================================================================
   4. MODELO
   ============================================================================ */

CREATE TABLE dbo.modelos_ml (
    mdl_cod      int           IDENTITY(1,1) NOT NULL,
    mdl_nom      varchar(100)  NOT NULL,
    mdl_tipo     varchar(30)   NOT NULL CONSTRAINT DF_mdl_tipo   DEFAULT 'ensemble_z',
    mdl_cuantil  decimal(4,3)  NOT NULL CONSTRAINT DF_mdl_cuantil DEFAULT 0.010,
    mdl_umbral   decimal(10,6) NULL,
    mdl_vars     nvarchar(max) NULL,
    mdl_hparms   nvarchar(max) NULL,
    mdl_ruta_art varchar(500)  NULL,
    mdl_est      char(1)       NOT NULL CONSTRAINT DF_mdl_est    DEFAULT 'C',
    mdl_fec_entr datetime2(3)  NULL,
    reg_usu      int           NULL,
    fec_reg      datetime2(3)  NOT NULL CONSTRAINT DF_mdl_fec_reg DEFAULT SYSUTCDATETIME(),
    eli_usu      int           NULL,
    fec_eli      datetime2(3)  NULL,
    CONSTRAINT PK_modelos_ml PRIMARY KEY CLUSTERED (mdl_cod),
    CONSTRAINT CK_mdl_est    CHECK (mdl_est IN ('A','C','I')),
    CONSTRAINT CK_mdl_tipo   CHECK (mdl_tipo IN ('isolation_forest','copod','ensemble_z','lof','ocsvm','elliptic')),
    CONSTRAINT CK_mdl_cuantil CHECK (mdl_cuantil > 0 AND mdl_cuantil < 1),
    CONSTRAINT CK_mdl_vent  CHECK (eli_usu IS NULL AND fec_eli IS NULL OR mdl_est = 'I')
);
GO

CREATE INDEX IX_mdl_est ON dbo.modelos_ml (mdl_est);
GO

-- Un solo modelo en produccion a la vez. El indice filtrado no necesita
-- columna calculada: solo indexa las filas mdl_est='A', y al ser UNIQUE
-- no admite dos.
CREATE UNIQUE INDEX UX_mdl_produccion
    ON dbo.modelos_ml (mdl_est) WHERE mdl_est = 'A';
GO


/* ============================================================================
   5. DETECCION
   ======================================================================== */

-- UNA fila por ventana evaluada, no solo por anomalia: es el historico que
-- permite recalcular umbrales y medir la tasa de falsos positivos.
-- prd_expl eliminado: la explicacion real vive en alerta_variable.
CREATE TABLE dbo.predicciones_ml (
    prd_cod     bigint        IDENTITY(1,1) NOT NULL,
    prd_mdl     int           NOT NULL,
    prd_ins     int           NOT NULL,
    prd_ini     datetime2(3)  NOT NULL,
    prd_fin     datetime2(3)  NOT NULL,
    prd_sco_iso decimal(10,6) NULL,
    prd_sco_cop decimal(10,6) NULL,
    prd_sco_ens decimal(10,6) NOT NULL,
    prd_umbral  decimal(10,6) NOT NULL,
    prd_zona    char(1)       NOT NULL CONSTRAINT DF_prd_zona    DEFAULT 'N',
    prd_es_anom bit           NOT NULL CONSTRAINT DF_prd_es_anom DEFAULT 0,
    prd_feats   nvarchar(max) NULL,
    fec_reg     datetime2(3)  NOT NULL CONSTRAINT DF_prd_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_predicciones_ml PRIMARY KEY CLUSTERED (prd_cod),
    CONSTRAINT CK_prd_zona CHECK (prd_zona IN ('N','V','A')),
    CONSTRAINT CK_prd_vent CHECK (prd_fin > prd_ini),
    -- prd_zona y prd_es_anom NO son redundantes: prd_zona es la capa
    -- (N/V/A) y prd_es_anom la decision ya estabilizada tras N-de-M y
    -- anti-flap. Un detector sin anti-flap pondria zona='A' con
    -- es_anom=0.
    CONSTRAINT CK_prd_zona_anom CHECK (prd_zona <> 'A' OR prd_es_anom = 1),
    CONSTRAINT FK_prd_mdl FOREIGN KEY (prd_mdl) REFERENCES dbo.modelos_ml  (mdl_cod),
    CONSTRAINT FK_prd_ins FOREIGN KEY (prd_ins) REFERENCES dbo.instancias (ins_cod)
);
GO

CREATE INDEX IX_prd_ins_fec ON dbo.predicciones_ml (prd_ins, prd_ini);
CREATE INDEX IX_prd_mdl_fec ON dbo.predicciones_ml (prd_mdl, prd_ini);
CREATE INDEX IX_prd_anom_fec ON dbo.predicciones_ml (prd_es_anom, prd_ini);
GO

CREATE TABLE dbo.alertas (
    alt_cod      int           IDENTITY(1,1) NOT NULL,
    alt_prd      bigint        NULL,
    alt_ins      int           NULL,
    alt_usu      int           NULL,
    alt_tipo     varchar(50)   NOT NULL,
    alt_sev      char(1)       NOT NULL,
    alt_titulo   varchar(200)  NOT NULL,
    alt_diag     varchar(500)  NULL,
    alt_est      char(1)       NOT NULL CONSTRAINT DF_alt_est     DEFAULT 'A',
    alt_fec      datetime2(3)  NOT NULL CONSTRAINT DF_alt_fec     DEFAULT SYSUTCDATETIME(),
    alt_fec_resu datetime2(3)  NULL,
    fec_reg      datetime2(3)  NOT NULL CONSTRAINT DF_alt_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_alertas PRIMARY KEY CLUSTERED (alt_cod),
    CONSTRAINT CK_alt_est  CHECK (alt_est  IN ('A','R','S','F')),
    CONSTRAINT CK_alt_sev  CHECK (alt_sev  IN ('C','A','M','B')),
    CONSTRAINT CK_alt_resu CHECK (alt_est IN ('S','F') OR (alt_fec_resu IS NULL AND alt_usu IS NULL)),
    CONSTRAINT FK_alt_prd FOREIGN KEY (alt_prd) REFERENCES dbo.predicciones_ml (prd_cod),
    CONSTRAINT FK_alt_ins FOREIGN KEY (alt_ins) REFERENCES dbo.instancias   (ins_cod),
    CONSTRAINT FK_alt_usu FOREIGN KEY (alt_usu) REFERENCES dbo.usuario       (usu_cod)
);
GO

CREATE INDEX IX_alt_fec  ON dbo.alertas (alt_fec);
CREATE INDEX IX_alt_est  ON dbo.alertas (alt_est);
CREATE INDEX IX_alt_sev  ON dbo.alertas (alt_sev);
CREATE INDEX IX_alt_prd  ON dbo.alertas (alt_prd) WHERE alt_prd IS NOT NULL;
GO

-- Que variables explican cada alerta (PCA: T2 / SPE). Volumen bajo: solo
-- hay fila si hay alerta, asi que aqui si vale la pena normalizar.
CREATE TABLE dbo.alerta_variable (
    alv_cod     int           IDENTITY(1,1) NOT NULL,
    alv_alt     int           NOT NULL,
    alv_var     varchar(100)  NOT NULL,
    alv_valor   decimal(18,4) NULL,
    alv_z       decimal(10,4) NULL,
    alv_contrib decimal(10,6) NULL,
    alv_rank    tinyint       NULL,
    fec_reg     datetime2(3)  NOT NULL CONSTRAINT DF_alv_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_alerta_variable PRIMARY KEY CLUSTERED (alv_cod),
    CONSTRAINT UQ_alv UNIQUE (alv_alt, alv_rank),
    CONSTRAINT CK_alv_rank CHECK (alv_rank IS NULL OR alv_rank BETWEEN 1 AND 15),
    CONSTRAINT FK_alv_alt FOREIGN KEY (alv_alt) REFERENCES dbo.alertas (alt_cod)
);
GO

-- cra_tono eliminado: los 3 call-sites escribian "rojo" literal.
CREATE TABLE dbo.causas_raiz (
    cra_cod   int          IDENTITY(1,1) NOT NULL,
    cra_alt   int          NOT NULL,
    cra_padre int          NULL,
    cra_nivel char(1)      NOT NULL,
    cra_etiq  varchar(200) NOT NULL,
    fec_reg   datetime2(3) NOT NULL CONSTRAINT DF_cra_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_causas_raiz PRIMARY KEY CLUSTERED (cra_cod),
    CONSTRAINT CK_cra_nivel CHECK (cra_nivel IN ('R','W','L')),
    CONSTRAINT CK_cra_no_self CHECK (cra_padre IS NULL OR cra_padre <> cra_cod),
    CONSTRAINT FK_cra_alt   FOREIGN KEY (cra_alt)   REFERENCES dbo.alertas (alt_cod),
    CONSTRAINT FK_cra_padre FOREIGN KEY (cra_padre) REFERENCES dbo.causas_raiz (cra_cod)
);
GO

-- NO se particiona: 24 h x 3 severidades = 72 filas/dia como maximo, y
-- particionar por CONVERT(datetime2, hma_fec) impediria crear UQ_hma
-- (SQL Server exige que toda clave unica de una tabla particionada
-- contenga la columna de particion, y aqui no hay datetime2 real).
CREATE TABLE dbo.heatmap_anomalias (
    hma_cod  int         IDENTITY(1,1) NOT NULL,
    hma_fec  date        NOT NULL,
    hma_hora tinyint     NOT NULL,
    hma_sev  char(1)     NOT NULL,
    hma_cant int         NOT NULL CONSTRAINT DF_hma_cant DEFAULT 0,
    fec_reg  datetime2(3) NOT NULL CONSTRAINT DF_hma_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_heatmap_anomalias PRIMARY KEY CLUSTERED (hma_cod),
    CONSTRAINT UQ_hma UNIQUE (hma_fec, hma_hora, hma_sev),
    CONSTRAINT CK_hma_hora CHECK (hma_hora BETWEEN 0 AND 23),
    CONSTRAINT CK_hma_sev  CHECK (hma_sev  IN ('N','B','A')),
    CONSTRAINT CK_hma_cant CHECK (hma_cant >= 0)
);
GO


/* ============================================================================
   6. DATOS CRUDOS
   Las 4 van particionadas por mes. Por eso TODA clave unica y TODA FK
   indexada de aqui incluye la columna de particion: es un requisito de
   SQL Server, no un capricho.
   ============================================================================ */

-- metrics.log. RETENCION CORTA: 7 dias (proc_retencion_datos).
-- El historico util ya esta en prd_feats, que guarda las 15 variables por
-- ventana. A ~1,2 KB por fila son ~5,4 GB/ano por nodo si no se purga.
CREATE TABLE dbo.metricas (
    met_cod bigint       IDENTITY(1,1) NOT NULL,
    met_ins int          NOT NULL,
    met_prd bigint       NULL,
    met_fec datetime2(3) NOT NULL,
    met_json nvarchar(max) NOT NULL,
    fec_reg datetime2(3) NOT NULL CONSTRAINT DF_met_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_metricas PRIMARY KEY CLUSTERED (met_cod, met_fec)
) ON PS_Mes (met_fec);
GO

CREATE INDEX IX_met_ins_fec ON dbo.metricas (met_ins, met_fec);
CREATE INDEX IX_met_prd      ON dbo.metricas (met_prd, met_fec) WHERE met_prd IS NOT NULL;
GO

-- events.log. OJO CON EL VOLUMEN: no se persiste una fila por
-- sql_batch_completed (11 conexiones x 10 lotes/s = ~864.000 filas/dia).
-- REGLA DE ENTRADA en el collector: solo el evento que explica una
-- anomalia — dura sobre el umbral, logical_reads sobre el percentil, o
-- hubo error. eve_writes eliminado: logical_writes es ~0 en read committed.
CREATE TABLE dbo.eventos (
    eve_cod    bigint        IDENTITY(1,1) NOT NULL,
    eve_ins    int           NOT NULL,
    eve_prd    bigint        NULL,
    eve_sid    int           NULL,
    eve_fec    datetime2(3)  NOT NULL,
    eve_dur    bigint        NULL,
    eve_cpu    bigint        NULL,
    eve_lreads bigint        NULL,
    eve_wait   varchar(60)   NULL,
    eve_sql    varchar(500)  NULL,
    fec_reg    datetime2(3)  NOT NULL CONSTRAINT DF_eve_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_eventos PRIMARY KEY CLUSTERED (eve_cod, eve_fec)
) ON PS_Mes (eve_fec);
GO

IF COL_LENGTH('dbo.eventos', 'eve_sid') IS NULL
    ALTER TABLE dbo.eventos ADD eve_sid int NULL;
GO

CREATE INDEX IX_eve_ins_fec ON dbo.eventos (eve_ins, eve_fec);
CREATE INDEX IX_eve_prd      ON dbo.eventos (eve_prd, eve_fec) WHERE eve_prd IS NOT NULL;
GO

CREATE TABLE dbo.logs_sql (
    lgs_cod bigint       IDENTITY(1,1) NOT NULL,
    lgs_ins int          NOT NULL,
    lgs_prd bigint       NULL,
    lgs_fec datetime2(3) NOT NULL,
    lgs_niv char(1)      NULL,
    lgs_msg nvarchar(max) NULL,
    fec_reg datetime2(3) NOT NULL CONSTRAINT DF_lgs_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_logs_sql PRIMARY KEY CLUSTERED (lgs_cod, lgs_fec),
    CONSTRAINT CK_lgs_niv CHECK (lgs_niv IS NULL OR lgs_niv IN ('I','W','E')),
    CONSTRAINT FK_lgs_ins FOREIGN KEY (lgs_ins) REFERENCES dbo.instancias (ins_cod)
) ON PS_Mes (lgs_fec);
GO

CREATE INDEX IX_lgs_ins_fec ON dbo.logs_sql (lgs_ins, lgs_fec);
CREATE INDEX IX_lgs_prd      ON dbo.logs_sql (lgs_prd, lgs_fec) WHERE lgs_prd IS NOT NULL;
GO

-- wks_prd eliminado: foto agregada por intervalo, no una ventana evaluada,
-- y era el unico *_prd sin indice.
CREATE TABLE dbo.estadisticas_carga (
    wks_cod  bigint        IDENTITY(1,1) NOT NULL,
    wks_ins  int           NOT NULL,
    wks_fec  datetime2(3)  NOT NULL,
    wks_json nvarchar(max) NOT NULL,
    fec_reg  datetime2(3)  NOT NULL CONSTRAINT DF_wks_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_estadisticas_carga PRIMARY KEY CLUSTERED (wks_cod, wks_fec),
    CONSTRAINT FK_wks_ins FOREIGN KEY (wks_ins) REFERENCES dbo.instancias (ins_cod)
) ON PS_Mes (wks_fec);
GO

CREATE INDEX IX_wks_ins_fec ON dbo.estadisticas_carga (wks_ins, wks_fec);
GO


/* ============================================================================
   7. DERIVA Y REENTRENAMIENTO
   Las 3 conservan fec_reg; modelos_ml y reentrenamiento conservan ademas la
   auditoria completa.
   ============================================================================ */

CREATE TABLE dbo.deriva_monitor (
    drv_cod     int           IDENTITY(1,1) NOT NULL,
    drv_mdl     int           NOT NULL,
    drv_fec     datetime2(3)  NOT NULL CONSTRAINT DF_drv_fec     DEFAULT SYSUTCDATETIME(),
    drv_var     varchar(100)  NOT NULL,
    drv_metrica char(1)       NOT NULL CONSTRAINT DF_drv_metrica DEFAULT 'P',
    drv_valor   decimal(10,6) NOT NULL,
    drv_est     char(1)       NOT NULL CONSTRAINT DF_drv_est     DEFAULT 'E',
    fec_reg     datetime2(3)  NOT NULL CONSTRAINT DF_drv_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_deriva_monitor PRIMARY KEY CLUSTERED (drv_cod),
    CONSTRAINT CK_drv_metrica CHECK (drv_metrica IN ('P','K')),
    CONSTRAINT CK_drv_est     CHECK (drv_est     IN ('E','A','D')),
    CONSTRAINT CK_drv_valor   CHECK (drv_valor >= 0),
    CONSTRAINT FK_drv_mdl FOREIGN KEY (drv_mdl) REFERENCES dbo.modelos_ml (mdl_cod)
);
GO

CREATE INDEX IX_drv_mdl_fec ON dbo.deriva_monitor (drv_mdl, drv_fec);
GO

-- ren_fec_ini / ren_fec_fin (MIN/MAX de los pasos), ren_n_test (va en el
-- rep_detalle de validacion_holdout) y ren_ruta_copia (el path es
-- deterministico desde ren_fec_sol) se eliminaron por ser derivables.
CREATE TABLE dbo.reentrenamiento (
    ren_cod        int           IDENTITY(1,1) NOT NULL,
    ren_mdl_origen int           NOT NULL,
    ren_mdl_nuevo  int           NULL,
    ren_disparo    char(1)       NOT NULL,
    ren_motivo     varchar(200)  NULL,
    ren_usu_sol    int           NULL,
    ren_fec_sol    datetime2(3)  NOT NULL CONSTRAINT DF_ren_fec_sol DEFAULT SYSUTCDATETIME(),
    ren_dat_ini    datetime2(3)  NULL,
    ren_dat_fin    datetime2(3)  NULL,
    ren_criterio   varchar(500)  NULL,
    ren_n_train    int           NULL,
    ren_params     nvarchar(max) NULL,
    ren_f1_antes   decimal(5,4)  NULL,
    ren_f1_desp    decimal(5,4)  NULL,
    ren_fpr_antes  decimal(5,2)  NULL,
    ren_fpr_desp   decimal(5,2)  NULL,
    ren_est        char(1)       NOT NULL CONSTRAINT DF_ren_est    DEFAULT 'P',
    ren_usu_apr    int           NULL,
    ren_fec_apr    datetime2(3)  NULL,
    ren_obs        varchar(500)  NULL,
    reg_usu        int           NULL,
    fec_reg        datetime2(3)  NOT NULL CONSTRAINT DF_ren_fec_reg DEFAULT SYSUTCDATETIME(),
    eli_usu        int           NULL,
    fec_eli        datetime2(3)  NULL,
    CONSTRAINT PK_reentrenamiento PRIMARY KEY CLUSTERED (ren_cod),
    CONSTRAINT CK_ren_disparo CHECK (ren_disparo IN ('D','F','P','M')),
    CONSTRAINT CK_ren_est     CHECK (ren_est     IN ('P','E','V','A','R','X')),
    CONSTRAINT CK_ren_dat     CHECK (ren_dat_ini IS NULL OR ren_dat_fin IS NULL OR ren_dat_fin > ren_dat_ini),
    CONSTRAINT CK_ren_f1      CHECK ((ren_f1_antes IS NULL OR ren_f1_antes BETWEEN 0 AND 1)
                                  AND (ren_f1_desp  IS NULL OR ren_f1_desp  BETWEEN 0 AND 1)),
    CONSTRAINT CK_ren_fpr     CHECK ((ren_fpr_antes IS NULL OR ren_fpr_antes BETWEEN 0 AND 1)
                                  AND (ren_fpr_desp  IS NULL OR ren_fpr_desp  BETWEEN 0 AND 1)),
    CONSTRAINT CK_ren_apr     CHECK (ren_est NOT IN ('A','R') OR (ren_fec_apr IS NOT NULL AND ren_usu_apr IS NOT NULL)),
    CONSTRAINT FK_ren_origen FOREIGN KEY (ren_mdl_origen) REFERENCES dbo.modelos_ml (mdl_cod),
    CONSTRAINT FK_ren_nuevo  FOREIGN KEY (ren_mdl_nuevo)  REFERENCES dbo.modelos_ml (mdl_cod),
    CONSTRAINT FK_ren_usu_sol FOREIGN KEY (ren_usu_sol)    REFERENCES dbo.usuario     (usu_cod),
    CONSTRAINT FK_ren_usu_apr FOREIGN KEY (ren_usu_apr)    REFERENCES dbo.usuario     (usu_cod),
    CONSTRAINT FK_ren_reg     FOREIGN KEY (reg_usu)        REFERENCES dbo.usuario     (usu_cod),
    CONSTRAINT FK_ren_eli     FOREIGN KEY (eli_usu)        REFERENCES dbo.usuario     (usu_cod)
);
GO

CREATE INDEX IX_ren_est    ON dbo.reentrenamiento (ren_est);
CREATE INDEX IX_ren_fec_sol ON dbo.reentrenamiento (ren_fec_sol);
GO

-- Bitacora paso a paso. rep_cod eliminado: (rep_ren, rep_orden) ya es
-- unico y es lo que se consulta siempre.
CREATE TABLE dbo.reentrenamiento_paso (
    rep_ren     int          NOT NULL,
    rep_orden   tinyint      NOT NULL,
    rep_paso    varchar(50)  NOT NULL,
    rep_est     char(1)      NOT NULL CONSTRAINT DF_rep_est     DEFAULT 'P',
    rep_fec_ini datetime2(3) NULL,
    rep_fec_fin datetime2(3) NULL,
    rep_detalle varchar(500) NULL,
    fec_reg     datetime2(3) NOT NULL CONSTRAINT DF_rep_fec_reg DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_reentrenamiento_paso PRIMARY KEY CLUSTERED (rep_ren, rep_orden),
    CONSTRAINT CK_rep_orden CHECK (rep_orden BETWEEN 1 AND 99),
    CONSTRAINT CK_rep_est   CHECK (rep_est   IN ('P','E','O','X')),
    CONSTRAINT CK_rep_vent  CHECK (rep_fec_ini IS NULL OR rep_fec_fin IS NULL OR rep_fec_fin >= rep_fec_ini),
    CONSTRAINT FK_rep_ren FOREIGN KEY (rep_ren) REFERENCES dbo.reentrenamiento (ren_cod)
);
GO


/* ============================================================================
   8. CONFIGURACION
   cfg_cod y cfg_desc eliminados: cfg_clave ya era la clave natural y la
   documentacion pertenece al codigo. La auditoria se conserva completa
   porque deshabilitar un parametro es una baja logica real.
   ============================================================================ */

CREATE TABLE dbo.configuracion_sistema (
    cfg_clave varchar(100) NOT NULL,
    cfg_valor varchar(500) NOT NULL,
    reg_usu   int          NULL,
    fec_reg   datetime2(3) NOT NULL CONSTRAINT DF_cfg_fec_reg DEFAULT SYSUTCDATETIME(),
    eli_usu   int          NULL,
    fec_eli   datetime2(3) NULL,
    CONSTRAINT PK_configuracion_sistema PRIMARY KEY CLUSTERED (cfg_clave),
    CONSTRAINT CK_cfg_vacia CHECK (LEN(LTRIM(RTRIM(cfg_clave))) > 0),
    CONSTRAINT FK_cfg_reg FOREIGN KEY (reg_usu) REFERENCES dbo.usuario (usu_cod),
    CONSTRAINT FK_cfg_eli FOREIGN KEY (eli_usu) REFERENCES dbo.usuario (usu_cod)
);
GO

/* ========================================================================
   Las FK que quedaron SIN declarar a proposito
   ---------------------------------------------------------------------
   metricas.met_prd  y  eventos.eve_prd  ->  predicciones_ml.prd_cod
   logs_sql.lgs_prd                     ->  predicciones_ml.prd_cod

   No se pueden declarar: la tabla referenciada (metricas, eventos,
   logs_sql) es particionada, y SQL Server no permite que una tabla
   particionada sea referenciada por una FK que no incluya la columna de
   particion. Habria que anadir met_fec / eve_fec / lgs_fec a cada FK, lo
   cual duplicaria la columna de particion y, con ella, el riesgo de que
   la ventana y la captura no coincidan.

   Es el precio de particionar y, a cambio, el indice IX_*_prd queda
   alineado con el particionado y la purga por mes sigue sirviendo.
   Si se prefiere elBindings: quitar ON PS_Mes de las 4 tablas crudas y
   entonces si se pueden declarar las 3 FK.
   ======================================================================== */


/* ============================================================================
   9. TRIGGERS
   ============================================================================ */

-- 9.1 La instancia de la prediccion tiene que existir, y la ventana no
--     puede empezar antes de que se pusiera en produccion. Sin esto
--     el detector puede "descubrir" anomalias en un periodo que nadie
--     vigilaba y contaminar el baseline.
CREATE OR ALTER TRIGGER TR_prd_instancia_valida
ON dbo.predicciones_ml
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (
        SELECT 1
        FROM inserted i
        JOIN dbo.instancias n ON n.ins_cod = i.prd_ins
        WHERE n.ins_fec_alta IS NOT NULL
          AND i.prd_ini < n.ins_fec_alta
    )
    BEGIN
        RAISERROR ('predicciones_ml: prd_ini anterior a instancias.ins_fec_alta.', 16, 1);
        ROLLBACK TRANSACTION;
        RETURN;
    END
END
GO

-- 9.2 prd_feats es el insumo del reentrenamiento: si se puede reescribir
--     despues, el modelo se entreno sobre datos que ya no coinciden con
--     la fila, y el problema aparece meses despues sin rastro.
CREATE OR ALTER TRIGGER TR_prd_features_inmutable
ON dbo.predicciones_ml
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF UPDATE(prd_feats)
    BEGIN
        RAISERROR ('predicciones_ml.prd_feats es inmutable: es el insumo del reentrenamiento.', 16, 1);
        ROLLBACK TRANSACTION;
        RETURN;
    END
END
GO

-- 9.3 Si la alerta viene de una prediccion, la instancia tiene que ser la
--     misma. Sin esta FK cruzada se podria colgar una alerta de la
--     instancia equivocada y el mapa de calor mezclaria nodos.
CREATE OR ALTER TRIGGER TR_alt_instancia_coherente
ON dbo.alertas
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (
        SELECT 1
        FROM inserted a
        JOIN dbo.predicciones_ml p ON p.prd_cod = a.alt_prd
        WHERE a.alt_ins IS NULL OR a.alt_ins <> p.prd_ins
    )
    BEGIN
        RAISERROR ('alertas: alt_ins no coincide con la instancia de la prediccion de origen.', 16, 1);
        ROLLBACK TRANSACTION;
        RETURN;
    END
END
GO

-- 9.4 hma_sev se deriva de alt_sev (4 niveles -> 3). Ademas excluye los
--     falsos positivos: una alerta marcada 'F' no debe ensuciar el mapa.
--     Es lo que hoy esta hardcodeado a 'alerta_alta' en el backend.
CREATE OR ALTER TRIGGER TR_alertas_hma_rollup
ON dbo.alertas
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH claves AS (
        SELECT alt_fec, alt_sev, alt_est FROM inserted WHERE alt_est <> 'F'
        UNION
        SELECT alt_fec, alt_sev, alt_est FROM deleted  WHERE alt_est <> 'F'
    ),
    agregado AS (
        SELECT CONVERT(date, c.alt_fec)         AS d,
               CONVERT(tinyint, DATEPART(HOUR, c.alt_fec)) AS hh,
               CASE WHEN c.alt_sev IN ('C','A') THEN 'A' ELSE 'B' END AS sev,
               COUNT_BIG(*)                      AS cant
        FROM claves c
        WHERE c.alt_sev IS NOT NULL
        GROUP BY CONVERT(date, c.alt_fec),
                 CONVERT(tinyint, DATEPART(HOUR, c.alt_fec)),
                 CASE WHEN c.alt_sev IN ('C','A') THEN 'A' ELSE 'B' END
    )
    MERGE dbo.heatmap_anomalias WITH (HOLDLOCK) AS t
    USING agregado AS a
      ON t.hma_fec = a.d AND t.hma_hora = a.hh AND t.hma_sev = a.sev
    -- Acumula, no reemplaza: el MERGE solo ve las filas del statement en
    -- curso, asi que poner t.hma_cant = a.cant dejaria el contador en el
    -- numero de alertas del ultimo INSERT, no el total de la celda. Con
    -- deleted en el UNION, un DELETE resta y un UPDATE que no cambia
    -- severidad ni fecha suma y resta.
    WHEN MATCHED
        THEN UPDATE SET t.hma_cant = t.hma_cant + a.cant
    WHEN NOT MATCHED BY TARGET
        THEN INSERT (hma_fec, hma_hora, hma_sev, hma_cant) VALUES (a.d, a.hh, a.sev, a.cant);
END
GO

-- 9.5 El arbol de causa raiz no puede tener ciclos. Sin esto, una
--     correccion de "esta causa es hija de aquella" puede dejar el
--     recorrido infinito y tumbar el endpoint que lo expone.
CREATE OR ALTER TRIGGER TR_cra_sin_ciclo
ON dbo.causas_raiz
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (
        SELECT 1
        FROM inserted i
        JOIN dbo.causas_raiz p ON p.cra_cod = i.cra_padre
        WHERE i.cra_padre IS NOT NULL
          AND (p.cra_padre = i.cra_cod OR p.cra_padre = i.cra_padre)
    )
    BEGIN
        RAISERROR ('causas_raiz: el padre indicado crearia un ciclo en el arbol.', 16, 1);
        ROLLBACK TRANSACTION;
        RETURN;
    END
END
GO


/* ============================================================================
   10. MANTENIMIENTO
   ============================================================================ */

-- 10.1 Anade cortes de particion hacia adelante.
--     Se apoya en la fecha MAX real de la tabla, no en GETDATE(), para no
--     dejar un hueco si el collector estuvo caido: si nadie escribio en
--     marzo, el corte de abril se crea igual y marzo cae entero en el
--     MAXVALUE, que luego proc_retencion_datos puede purgar.
--     Solo avanza: nunca agrega un corte en el pasado.
CREATE OR ALTER PROCEDURE dbo.proc_roll_particiones
    @meses_adelanto int = 3,
    @tabla         sysname = NULL      -- NULL = las 4 crudas
AS
BEGIN
    SET NOCOUNT ON;

    IF @meses_adelanto < 1
    BEGIN
        RAISERROR ('@meses_adelanto debe ser >= 1.', 16, 1);
        RETURN;
    END

    DECLARE @lista TABLE (tabla sysname PRIMARY KEY, col sysname, desde datetime2(3));
    INSERT INTO @lista (tabla, col, desde)
    VALUES ('metricas',           'met_fec', '2026-01-01'),
           ('eventos',            'eve_fec', '2026-01-01'),
           ('logs_sql',           'lgs_fec', '2026-01-01'),
           ('estadisticas_carga', 'wks_fec', '2026-01-01');

    IF @tabla IS NOT NULL
        DELETE FROM @lista WHERE tabla <> @tabla;

    IF NOT EXISTS (SELECT 1 FROM @lista)
    BEGIN
        RAISERROR ('@tabla no es una tabla particionada de este esquema.', 16, 1);
        RETURN;
    END

    DECLARE @nombre sysname, @col sysname, @desde datetime2(3),
            @maximo datetime2(3), @limite datetime2(3), @sql nvarchar(max);

    DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT tabla, col, desde FROM @lista;
    OPEN c;
    FETCH NEXT FROM c INTO @nombre, @col, @desde;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        -- El siguiente corte se calcula sobre el ultimo que YA existe en la
        -- funcion, no sobre @desde: asi el procedimiento se puede correr
        -- mil veces sin duplicar cortes.
        SELECT @maximo = MAX(CONVERT(datetime2(3), rv.value))
        FROM sys.partition_functions pf
        JOIN sys.partition_range_values rv ON rv.function_id = pf.function_id
        WHERE pf.name = 'PF_Mes';

        SET @limite = DATEADD(MONTH, @meses_adelanto,
                              DATEADD(MONTH, DATEDIFF(MONTH, 0, ISNULL(@maximo, @desde)), 0));

        WHILE @limite > ISNULL(@maximo, @desde)
        BEGIN
            SET @sql = N'ALTER PARTITION SCHEME PS_Mes NEXT FOR VALUE ('''
                     + CONVERT(char(19), @limite, 126) + N''');';
            EXEC sys.sp_executesql @sql;

            SET @maximo = @limite;
            SET @limite = DATEADD(MONTH, 1, @limite);
        END

        PRINT @nombre + ': cortes partitions hasta ' + CONVERT(varchar(19), @maximo, 120);
        FETCH NEXT FROM c INTO @nombre, @col, @desde;
    END

    CLOSE c;
    DEALLOCATE c;
END
GO

-- 10.2 Purga por retencion. Para las particionadas se borran meses
--     completos con DROP PARTITION (no DELETE fila por fila: no genera
--     log, no hace crecer el transaction log y libera el espacio de
--     inmediato). Para las que no son particionadas, DELETE por fecha.
--
--     @dias_simples aplica a las tablas de detalle. A las particionadas se
--     les corta el mes entero: si metricas guarda 7 dias, la primera
--     pasada elimina el mes previo completo y quedan 30 dias, no 7. Es
--     el precio de particionar por mes, y con 1,2 KB por fila la
--     diferencia entre 7 y 30 dias es de ~0,9 GB por nodo.
CREATE OR ALTER PROCEDURE dbo.proc_retencion_datos
    @dias_detalle int = 7,
    @dias_heatmap int = 365,
    @simular     bit = 1
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @corte_detalle datetime2(3) = DATEADD(DAY, -@dias_detalle,   SYSUTCDATETIME()),
            @corte_heatmap date        = DATEADD(DAY, -@dias_heatmap,   CONVERT(date, SYSUTCDATETIME()));

    -- Tablas particionadas: se busca el MES COMPLETO anterior al corte.
    DECLARE @mes_corte datetime2(3) = DATEADD(MONTH, DATEDIFF(MONTH, 0, @corte_detalle), 0);

    IF @simular = 1
    BEGIN
        SELECT 'DROP PARTITION' AS accion, 'dbo.metricas' AS tabla, COUNT(*) AS filas
          FROM dbo.metricas           WHERE met_fec < @mes_corte
        UNION ALL
        SELECT 'DROP PARTITION', 'dbo.eventos',  COUNT(*)
          FROM dbo.eventos            WHERE eve_fec < @mes_corte
        UNION ALL
        SELECT 'DROP PARTITION', 'dbo.logs_sql', COUNT(*)
          FROM dbo.logs_sql           WHERE lgs_fec < @mes_corte
        UNION ALL
        SELECT 'DROP PARTITION', 'dbo.estadisticas_carga', COUNT(*)
          FROM dbo.estadisticas_carga WHERE wks_fec < @mes_corte
        UNION ALL
        SELECT 'DELETE', 'dbo.heatmap_anomalias', COUNT(*)
          FROM dbo.heatmap_anomalias  WHERE hma_fec < @corte_heatmap
        UNION ALL
        SELECT 'DELETE', 'dbo.causas_raiz', COUNT(*)
          FROM dbo.causas_raiz c
         WHERE NOT EXISTS (SELECT 1 FROM dbo.alertas a WHERE a.alt_cod = c.cra_alt)
        RETURN;
    END

    -- Cada DROP PARTITION baja ahi un monton de filas, asi que van en
    -- batches: una sola transaccion con 4 millones de filas de metricas
    -- llenaria el log entero.
    --
    -- Se usa sys.dm_db_partition_stats y no sys.partitions porque en SQL
    -- Server 2025 la vista sys.partitions quedo sin partition_function_id ni
    -- boundary_id: la particion N guarda los valores menores que el corte N,
    -- asi que las que hay que tirar son las que su numero no supera la
    -- cantidad de cortes anteriores a la fecha de corte.
    DECLARE @t sysname, @part int, @sql nvarchar(max);
    DECLARE part_cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT DISTINCT t.name, ps.partition_number
        FROM sys.dm_db_partition_stats ps
        JOIN sys.tables  t ON t.object_id = ps.object_id
        JOIN sys.indexes i ON i.object_id = ps.object_id AND i.index_id = ps.index_id
        WHERE ps.index_id > 0
          AND i.name IN ('PK_metricas','PK_eventos','PK_logs_sql','PK_estadisticas_carga')
          AND ps.row_count > 0
          AND ps.partition_number > 1
          AND ps.partition_number <= (
                SELECT COUNT(*)
                FROM sys.partition_range_values rv
                WHERE rv.function_id = OBJECT_ID('PF_Mes')
                  AND CONVERT(datetime2(3), rv.value) <= @mes_corte)
        ORDER BY t.name, ps.partition_number;

    OPEN part_cur;
    FETCH NEXT FROM part_cur INTO @t, @part;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @sql = N'ALTER TABLE ' + QUOTENAME(@t) + N' DROP PARTITION ' + CAST(@part AS varchar(10)) + N';';
        EXEC sys.sp_executesql @sql;
        PRINT @t + ': particion ' + CAST(@part AS varchar(10)) + ' eliminada.';
        FETCH NEXT FROM part_cur INTO @t, @part;
    END

    CLOSE part_cur;
    DEALLOCATE part_cur;

    DELETE FROM dbo.heatmap_anomalias WHERE hma_fec < @corte_heatmap;
    -- Sin cascada declarada: las causas cuelgan de alertas de mas de un ano
    -- y se limpian cuando la alerta ya no existe.
    DELETE c
      FROM dbo.causas_raiz c
     WHERE NOT EXISTS (SELECT 1 FROM dbo.alertas a WHERE a.alt_cod = c.cra_alt);
END
GO

PRINT 'Esquema bdSteelNort listo. 21 tablas / 193 columnas.';
PRINT 'Datos seed minimos:';
PRINT '  INSERT INTO dbo.rol (rol_nom) VALUES (''Administrador''), (''Operador''), (''Observador'');';
GO
