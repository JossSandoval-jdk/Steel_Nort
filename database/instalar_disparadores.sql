/* ============================================================================
   SteelNort — Instalacion de triggers y procedimientos sobre una base v2 ya
   poblada.

   POR QUE EXISTE ESTE ARCHIVO
   ---------------------------------------------------------------------------
   database/schema_bdsteelnort.sql es el canonico: crea la base completa con
   particiones, triggers y procedimientos. Pero la base de desarrollo
   (bdSteelNort_v2) se creo con Base.metadata.create_all, que solo hace CREATE
   TABLE: las 21 tablas existen y los datos de acceso estan, pero NO hay
   triggers ni procedimientos. Sin ellos:

     - heatmap_anomalias nunca se llena (TR_alertas_hma_rollup no existe)
     - nada protege prd_ini, prd_feats ni la coherencia de alt_ins
     - proc_retencion_datos no se puede correr

   Este script instala SOLO los objetos de las secciones 9 y 10 del canonico.
   No crea, no altera y no borra ninguna tabla: los usuarios, roles, permisos
   y sesiones que ya estan se quedan como estan.

   Los cuerpos son copia literal del canonico. Si se cambia uno, hay que
   cambiarlo en los dos archivos. Se ejecutan con CREATE OR ALTER, asi que
   correrlo de nuevo actualiza en sitio sin error.

   USO
   ---------------------------------------------------------------------------
   El script NO lleva USE: se aplica a la base con la que se abre la conexion.
   Desde el backend:

       sqlcmd -S localhost,1433 -d bdSteelNort_v2 -E -i instalar_disparadores.sql

   O con Python:

       python -c "import sys; ...ejecutar archivo..."

   QUE NO HACE, A PROPOSITO
   ---------------------------------------------------------------------------
   No pone las tablas sobre PS_Mes. Eso exigiria rehacer las claves
   compuestas (PK_metricas es (met_cod, met_fec)) y no se puede hacer con
   ALTER sobre tablas que ya tienen datos. Con la persistencia selectiva de
   app/v2/services/anomalia_v2.py el volumen ya no lo exige: solo se guardan
   las muestras de las ventanas anomalias.

   proc_retencion_datos sigue siendo seguro sin particionado: su cursor de
   DROP PARTITION busca sys.partitions con partition_number > 1, y una tabla
   no particionada solo tiene la 1, asi que no encuentra nada que dropear.
   ============================================================================ */

SET NOCOUNT ON;
GO

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
--     Nota: si las tablas no estan sobre PS_Mes, este proc da error al
--     ejecutarse. Es inocuo mientras tanto y sirve en cuanto se particionen.
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

PRINT 'Triggers y procedimientos instalados sobre la base actual.';
GO