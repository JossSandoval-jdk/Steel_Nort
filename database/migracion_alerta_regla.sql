/* ============================================================================
   SteelNort — Migración: diagnóstico por reglas (R1-R7) y eventos completos
   ----------------------------------------------------------------------------
   Idempotente: se puede ejecutar varias veces sin errores.

   Aplica sobre la base a la que apunte la API (V2_DATABASE_URL, p.ej.
   bdSteelNort_v4). NO fija USE: ejecútela con la base correcta seleccionada.

   Cambios:
     1. dbo.eventos: columnas eve_tipo (tipo de evento XE) y eve_json (evento
        crudo completo, para mostrarlo "tal cual").
     2. dbo.alerta_regla: tabla nueva con una fila por regla R1-R7 disparada.

   Tras ejecutarla, reinicie la API: el arranque valida que exista la tabla
   alerta_regla (ver app/v2/database.py::verificar_esquema).
   ============================================================================ */

SET NOCOUNT ON;
GO

/* ---------------------------------------------------------------------------
   1. dbo.eventos: guardar el tipo de evento y el evento crudo completo
   --------------------------------------------------------------------------- */

IF COL_LENGTH('dbo.eventos', 'eve_tipo') IS NULL
BEGIN
    ALTER TABLE dbo.eventos ADD eve_tipo varchar(60) NULL;
    PRINT 'Columna dbo.eventos.eve_tipo agregada.';
END
ELSE
    PRINT 'dbo.eventos.eve_tipo ya existe.';
GO

IF COL_LENGTH('dbo.eventos', 'eve_json') IS NULL
BEGIN
    ALTER TABLE dbo.eventos ADD eve_json nvarchar(max) NULL;
    PRINT 'Columna dbo.eventos.eve_json agregada.';
END
ELSE
    PRINT 'dbo.eventos.eve_json ya existe.';
GO

/* ---------------------------------------------------------------------------
   2. dbo.alerta_regla: reglas R1-R7 que se rompen o se emiten en una alerta
   --------------------------------------------------------------------------- */

IF OBJECT_ID('dbo.alerta_regla', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.alerta_regla (
        are_cod         int           IDENTITY(1,1) NOT NULL,
        are_alt         int           NOT NULL,
        are_regla       varchar(10)   NOT NULL,
        are_detonante   varchar(300)  NULL,
        are_diagnostico varchar(300)  NULL,
        are_corroborado varchar(20)   NULL,
        are_metricas    varchar(500)  NULL,
        are_evidencia   nvarchar(max) NULL,
        are_fuente      varchar(300)  NULL,
        fec_reg         datetime2(3)  NOT NULL CONSTRAINT DF_are_fec_reg DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_alerta_regla PRIMARY KEY CLUSTERED (are_cod),
        CONSTRAINT FK_are_alt FOREIGN KEY (are_alt) REFERENCES dbo.alertas (alt_cod)
    );
    PRINT 'Tabla dbo.alerta_regla creada.';
END
ELSE
    PRINT 'Tabla dbo.alerta_regla ya existe.';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_are_alt')
    CREATE INDEX IX_are_alt ON dbo.alerta_regla (are_alt, are_regla);
GO

PRINT 'Migración de diagnóstico por reglas lista.';
