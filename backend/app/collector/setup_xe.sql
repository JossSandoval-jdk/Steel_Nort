-- ============================================================
-- SteelNort - Extended Events Session Setup
-- Ejecutar UNA SOLA VEZ. La sesion persiste con SQL Server.
-- ============================================================

-- 1. Verificar si la sesion ya existe
IF NOT EXISTS (
    SELECT 1 FROM sys.server_event_sessions WHERE name = 'SteelNortMonitor'
)
BEGIN
    -- 2. Crear sesion de Extended Events
    CREATE EVENT SESSION [SteelNortMonitor] ON SERVER

    -- Batch completado (cada query con metricas reales)
    ADD EVENT sqlserver.sql_batch_completed(
        ACTION(
            sqlserver.sql_text,
            sqlserver.database_name,
            sqlserver.session_id,
            sqlserver.username,
            sqlserver.client_hostname,
            sqlserver.client_app_name
        )
        WHERE sqlserver.database_name = N'SteelNort'
    ),

    -- Llamadas RPC (stored procedures)
    ADD EVENT sqlserver.rpc_completed(
        ACTION(
            sqlserver.sql_text,
            sqlserver.database_name,
            sqlserver.session_id,
            sqlserver.username
        )
        WHERE sqlserver.database_name = N'SteelNort'
    ),

    -- Errores
    ADD EVENT sqlserver.error_reported(
        ACTION(
            sqlserver.sql_text,
            sqlserver.session_id,
            sqlserver.database_name
        )
        WHERE sqlserver.database_name = N'SteelNort'
    ),

    -- Deadlocks
    ADD EVENT sqlserver.xml_deadlock_report,

    -- Login/Logout
    ADD EVENT sqlserver.login,
    ADD EVENT sqlserver.logout

    -- Target: archivos .xel
    ADD TARGET package0.event_file(
        SET filename = N'/var/opt/mssql/log/steel_events.xel',
            max_file_size = 500,
            max_rollover_files = 5
    )

    WITH (
        MAX_MEMORY = 4096 KB,
        EVENT_RETENTION_MODE = ALLOW_SINGLE_LOSS,
        MAX_DISPATCH_LATENCY = 1 SECONDS,
        MAX_EVENT_SIZE = 0 KB,
        MEMORY_PARTITION_MODE = NONE,
        TRACK_CAUSALITY = OFF,
        STARTUP_STATE = ON
    );

    PRINT 'Sesion SteelNortMonitor creada.';
END
ELSE
BEGIN
    PRINT 'Sesion SteelNortMonitor ya existe.';
END
GO

-- 3. Iniciar sesion si no esta activa
IF EXISTS (
    SELECT 1 FROM sys.server_event_sessions
    WHERE name = 'SteelNortMonitor'
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM sys.dm_xe_sessions WHERE name = 'SteelNortMonitor'
    )
    BEGIN
        ALTER EVENT SESSION [SteelNortMonitor] ON SERVER STATE = START;
        PRINT 'Sesion SteelNortMonitor iniciada.';
    END
    ELSE
    BEGIN
        PRINT 'Sesion SteelNortMonitor ya esta activa.';
    END
END
GO
