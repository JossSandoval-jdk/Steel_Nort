-- ============================================================================
-- 1. ROLES
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM dbo.rol WHERE rol_nom = 'Administrador')
    INSERT INTO dbo.rol (rol_nom) VALUES ('Administrador');

IF NOT EXISTS (SELECT 1 FROM dbo.rol WHERE rol_nom = 'Operador')
    INSERT INTO dbo.rol (rol_nom) VALUES ('Operador');

IF NOT EXISTS (SELECT 1 FROM dbo.rol WHERE rol_nom = 'Gerente general')
    INSERT INTO dbo.rol (rol_nom) VALUES ('Gerente general');

IF NOT EXISTS (SELECT 1 FROM dbo.rol WHERE rol_nom = 'Encargado')
    INSERT INTO dbo.rol (rol_nom) VALUES ('Encargado');
GO

USE bdSteelNort;
GO

SET NOCOUNT ON;

-- ============================================================================
-- 1. ROLES
-- ============================================================================
IF NOT EXISTS (SELECT 1 FROM dbo.rol WHERE rol_nom = 'Administrador')
    INSERT INTO dbo.rol (rol_nom) VALUES ('Administrador');

IF NOT EXISTS (SELECT 1 FROM dbo.rol WHERE rol_nom = 'Operador')
    INSERT INTO dbo.rol (rol_nom) VALUES ('Operador');

IF NOT EXISTS (SELECT 1 FROM dbo.rol WHERE rol_nom = 'Gerente general')
    INSERT INTO dbo.rol (rol_nom) VALUES ('Gerente general');

IF NOT EXISTS (SELECT 1 FROM dbo.rol WHERE rol_nom = 'Encargado')
    INSERT INTO dbo.rol (rol_nom) VALUES ('Encargado');
GO


-- ============================================================================
-- 2. PERMISOS  (módulo:acción)
-- ============================================================================
-- Módulos: acceso, nodos, modelo, deteccion, datos, sistema, tablero, auth
-- Acciones: leer, crear, editar, eliminar
-- ============================================================================

DECLARE permiso TABLE (per_mod varchar(30), per_acc varchar(30));

INSERT INTO permiso (per_mod, per_acc) VALUES
    ('acceso',    'leer'),
    ('acceso',    'crear'),
    ('acceso',    'editar'),
    ('acceso',    'eliminar'),
    ('nodos',     'leer'),
    ('nodos',     'crear'),
    ('nodos',     'editar'),
    ('nodos',     'eliminar'),
    ('modelo',    'leer'),
    ('modelo',    'crear'),
    ('modelo',    'editar'),
    ('modelo',    'eliminar'),
    ('deteccion', 'leer'),
    ('deteccion', 'crear'),
    ('deteccion', 'editar'),
    ('deteccion', 'eliminar'),
    ('datos',     'leer'),
    ('datos',     'crear'),
    ('datos',     'editar'),
    ('datos',     'eliminar'),
    ('sistema',   'leer'),
    ('sistema',   'crear'),
    ('sistema',   'editar'),
    ('sistema',   'eliminar'),
    ('tablero',   'leer'),
    ('tablero',   'crear'),
    ('tablero',   'editar'),
    ('tablero',   'eliminar'),
    ('auth',      'login');

INSERT INTO dbo.permiso (per_mod, per_acc)
SELECT p.per_mod, p.per_acc
  FROM permiso p
 WHERE NOT EXISTS (
     SELECT 1 FROM dbo.permiso x
      WHERE x.per_mod = p.per_mod
        AND x.per_acc = p.per_acc
 );
GO


-- ============================================================================
-- 3. ASIGNACIÓN DE PERMISOS POR ROL
-- ============================================================================
-- Roles:
--   Administrador   -> TODOS los permisos
--   Operador        -> solo leer + login
--   Gerente general -> leer + crear + editar (sin eliminar) + login
--   Encargado       -> leer + crear + editar en datos/tablero, leer en el resto
-- ============================================================================

;WITH pares(rol_nom, per_mod, per_acc) AS (
    SELECT * FROM (VALUES
        -- Administrador: todos
        ('Administrador',   'acceso',    'leer'),
        ('Administrador',   'acceso',    'crear'),
        ('Administrador',   'acceso',    'editar'),
        ('Administrador',   'acceso',    'eliminar'),
        ('Administrador',   'nodos',     'leer'),
        ('Administrador',   'nodos',     'crear'),
        ('Administrador',   'nodos',     'editar'),
        ('Administrador',   'nodos',     'eliminar'),
        ('Administrador',   'modelo',    'leer'),
        ('Administrador',   'modelo',    'crear'),
        ('Administrador',   'modelo',    'editar'),
        ('Administrador',   'modelo',    'eliminar'),
        ('Administrador',   'deteccion', 'leer'),
        ('Administrador',   'deteccion', 'crear'),
        ('Administrador',   'deteccion', 'editar'),
        ('Administrador',   'deteccion', 'eliminar'),
        ('Administrador',   'datos',     'leer'),
        ('Administrador',   'datos',     'crear'),
        ('Administrador',   'datos',     'editar'),
        ('Administrador',   'datos',     'eliminar'),
        ('Administrador',   'sistema',   'leer'),
        ('Administrador',   'sistema',   'crear'),
        ('Administrador',   'sistema',   'editar'),
        ('Administrador',   'sistema',   'eliminar'),
        ('Administrador',   'tablero',   'leer'),
        ('Administrador',   'tablero',   'crear'),
        ('Administrador',   'tablero',   'editar'),
        ('Administrador',   'tablero',   'eliminar'),
        ('Administrador',   'auth',      'login'),

        -- Operador: solo leer + login
        ('Operador',        'acceso',    'leer'),
        ('Operador',        'nodos',     'leer'),
        ('Operador',        'modelo',    'leer'),
        ('Operador',        'deteccion', 'leer'),
        ('Operador',        'datos',     'leer'),
        ('Operador',        'sistema',   'leer'),
        ('Operador',        'tablero',   'leer'),
        ('Operador',        'auth',      'login'),

        -- Gerente general: leer + crear + editar + login
        ('Gerente general', 'acceso',    'leer'),
        ('Gerente general', 'acceso',    'crear'),
        ('Gerente general', 'acceso',    'editar'),
        ('Gerente general', 'nodos',     'leer'),
        ('Gerente general', 'nodos',     'crear'),
        ('Gerente general', 'nodos',     'editar'),
        ('Gerente general', 'modelo',    'leer'),
        ('Gerente general', 'modelo',    'crear'),
        ('Gerente general', 'modelo',    'editar'),
        ('Gerente general', 'deteccion', 'leer'),
        ('Gerente general', 'deteccion', 'crear'),
        ('Gerente general', 'deteccion', 'editar'),
        ('Gerente general', 'datos',     'leer'),
        ('Gerente general', 'datos',     'crear'),
        ('Gerente general', 'datos',     'editar'),
        ('Gerente general', 'sistema',   'leer'),
        ('Gerente general', 'sistema',   'crear'),
        ('Gerente general', 'sistema',   'editar'),
        ('Gerente general', 'tablero',   'leer'),
        ('Gerente general', 'tablero',   'crear'),
        ('Gerente general', 'tablero',   'editar'),
        ('Gerente general', 'auth',      'login'),

        -- Encargado: leer general + crear/editar en datos y tablero
        ('Encargado',       'acceso',    'leer'),
        ('Encargado',       'nodos',     'leer'),
        ('Encargado',       'modelo',    'leer'),
        ('Encargado',       'deteccion', 'leer'),
        ('Encargado',       'datos',     'leer'),
        ('Encargado',       'datos',     'crear'),
        ('Encargado',       'datos',     'editar'),
        ('Encargado',       'sistema',   'leer'),
        ('Encargado',       'tablero',   'leer'),
        ('Encargado',       'tablero',   'crear'),
        ('Encargado',       'tablero',   'editar'),
        ('Encargado',       'auth',      'login')
    ) AS v(rol_nom, per_mod, per_acc)
)
INSERT INTO dbo.rol_permiso (rol_cod, per_cod)
SELECT r.rol_cod, p.per_cod
  FROM pares x
  JOIN dbo.rol     r ON r.rol_nom = x.rol_nom
  JOIN dbo.permiso p ON p.per_mod = x.per_mod AND p.per_acc = x.per_acc
 WHERE NOT EXISTS (
     SELECT 1 FROM dbo.rol_permiso rp
      WHERE rp.rol_cod = r.rol_cod
        AND rp.per_cod = p.per_cod
 );
GO