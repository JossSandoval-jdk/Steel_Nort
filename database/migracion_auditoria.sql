/* ============================================================================
   SteelNort — Migración: registro de auditoría
   ----------------------------------------------------------------------------
   Idempotente: se puede ejecutar varias veces sin errores.

   Aplica sobre la base a la que apunte la API (V2_DATABASE_URL, p.ej.
   bdSteelNort_v4). NO fija USE: ejecútela con la base correcta seleccionada.

   Cambio:
     dbo.auditoria: tabla nueva con una fila por cada petición que cambia datos
     (POST/PUT/PATCH/DELETE), escrita por el middleware de la API
     (backend/app/v2/auditoria.py).

   Tras ejecutarla, reinicie la API: el arranque valida que exista la tabla
   auditoria (ver app/v2/database.py::verificar_esquema).
   ============================================================================ */

SET NOCOUNT ON;
GO

IF OBJECT_ID('dbo.auditoria', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.auditoria (
        aud_cod        int           IDENTITY(1,1) NOT NULL,
        aud_usu        int           NULL,
        aud_accion     varchar(10)   NOT NULL,
        aud_recurso    varchar(200)  NOT NULL,
        aud_resultado  int           NULL,
        aud_ip         varchar(45)   NULL,
        aud_fec        datetime2(3)  NOT NULL CONSTRAINT DF_aud_fec DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_auditoria PRIMARY KEY CLUSTERED (aud_cod),
        CONSTRAINT FK_aud_usu FOREIGN KEY (aud_usu) REFERENCES dbo.usuario (usu_cod)
    );
    PRINT 'Tabla dbo.auditoria creada.';
END
ELSE
    PRINT 'Tabla dbo.auditoria ya existe.';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_aud_fec')
    CREATE INDEX IX_aud_fec
        ON dbo.auditoria (aud_fec DESC)
        INCLUDE (aud_usu, aud_accion, aud_resultado);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_aud_usu_fec')
    CREATE INDEX IX_aud_usu_fec
        ON dbo.auditoria (aud_usu, aud_fec DESC);
GO

PRINT 'Migración de auditoría lista.';
GO
