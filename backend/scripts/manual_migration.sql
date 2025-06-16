-- Script manual para establecer la versión de Alembic
-- Ejecutar si la migración automática falla

-- Crear tabla alembic_version si no existe
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Limpiar cualquier versión existente
DELETE FROM alembic_version;

-- Insertar la versión actual
INSERT INTO alembic_version (version_num) VALUES ('unified_20250615');

-- Verificar
SELECT 'Alembic version set to: ' || version_num AS status FROM alembic_version;