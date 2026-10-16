-- Login de SOLO LECTURA para el recolector (S1-12)
-- Crea el login SQL Server 'steelnort_monitor' con MÍNIMO PRIVILEGIO (db_datareader)
-- y lo mapea a la base SteelNort.
--
-- IMPORTANTE: ejecutar con un usuario con permisos de sysadmin (sa o administrador).
-- Las contraseñas deben cambiarse en el .env del recolector.
--
-- BASES: SteelNort (monitoreada) y bdSteelNort_v4 (API v2) - se le da lectura a ambas.

SET NOCOUNT ON;
GO

USE master;
GO

-- 1. Crear login (Windows Authentication = no; SQL Authentication = sí)
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'steelnort_monitor')
BEGIN
    CREATE LOGIN [steelnort_monitor] WITH PASSWORD = N'CAMBIAR_PASSWORD_SQL_LECTURA';
END
ELSE
BEGIN
    -- Actualizar contraseña si ya existe (idempotente)
    ALTER LOGIN [steelnort_monitor] WITH PASSWORD = N'CAMBIAR_PASSWORD_SQL_LECTURA';
END
GO

-- 2. Mapear a base SteelNort (db_datareader - solo lectura)
USE SteelNort;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'steelnort_monitor')
BEGIN
    CREATE USER [steelnort_monitor] FOR LOGIN [steelnort_monitor];
END
GO
ALTER ROLE db_datareader ADD MEMBER [steelnort_monitor];
GO

-- 3. Mapear a base bdSteelNort_v4 (solo lectura para consultas auxiliares)
USE bdSteelNort_v4;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'steelnort_monitor')
BEGIN
    CREATE USER [steelnort_monitor] FOR LOGIN [steelnort_monitor];
END
GO
ALTER ROLE db_datareader ADD MEMBER [steelnort_monitor];
GO

-- 4. Verificar (rollback-friendly / informe)
USE master;
GO
SELECT sp.name AS [Login], sp.type_desc AS [Tipo], dp.is_disabled AS [Deshabilitado]
FROM sys.server_principals sp
WHERE sp.name = N'steelnort_monitor';

USE SteelNort;
GO
SELECT dp.name AS [Usuario_DB], r.name AS [Rol_DB]
FROM sys.database_principals dp
LEFT JOIN sys.database_role_members drm ON dp.principal_id = drm.member_principal_id
LEFT JOIN sys.database_principals r ON drm.role_principal_id = r.principal_id
WHERE dp.name = N'steelnort_monitor';

USE bdSteelNort_v4;
GO
SELECT dp.name AS [Usuario_DB], r.name AS [Rol_DB]
FROM sys.database_principals dp
LEFT JOIN sys.database_role_members drm ON dp.principal_id = drm.member_principal_id
LEFT JOIN sys.database_principals r ON drm.role_principal_id = r.principal_id
WHERE dp.name = N'steelnort_monitor';

PRINT 'Login steelnort_monitor creado/mapeado con db_datareader (solo lectura).';
GO
