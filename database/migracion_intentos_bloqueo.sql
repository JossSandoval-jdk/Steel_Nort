/* ============================================================================
   SteelNort — Migración: bloqueo por intentos fallidos de login
   ----------------------------------------------------------------------------
   Idempotente: se puede ejecutar varias veces sin errores.

   Aplica sobre la base a la que apunte la API (V2_DATABASE_URL, p.ej.
   bdSteelNort_v4). NO fija USE: ejecútela con la base correcta seleccionada.

   Cambio:
     dbo.usuario: columnas usu_intentos (fallos seguidos) y usu_bloqueo_hasta
     (fin del bloqueo). Las lleva el servicio de acceso: tras N fallos la
     cuenta responde 429 hasta que pase el plazo.

   Tras ejecutarla, reinicie la API.
   ============================================================================ */

SET NOCOUNT ON;
GO

IF COL_LENGTH('dbo.usuario', 'usu_intentos') IS NULL
BEGIN
    ALTER TABLE dbo.usuario
        ADD usu_intentos int NOT NULL CONSTRAINT DF_usu_intentos DEFAULT 0;
    PRINT 'Columna dbo.usuario.usu_intentos agregada.';
END
ELSE
    PRINT 'dbo.usuario.usu_intentos ya existe.';
GO

IF COL_LENGTH('dbo.usuario', 'usu_bloqueo_hasta') IS NULL
BEGIN
    ALTER TABLE dbo.usuario ADD usu_bloqueo_hasta datetime2(3) NULL;
    PRINT 'Columna dbo.usuario.usu_bloqueo_hasta agregada.';
END
ELSE
    PRINT 'dbo.usuario.usu_bloqueo_hasta ya existe.';
GO

PRINT 'Migración de bloqueo por intentos lista.';
GO
