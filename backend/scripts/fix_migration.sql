-- Script de emergencia para arreglar la migración
-- Ejecutar este script si la migración automática falla

-- 1. Actualizar la versión de alembic para que coincida con la migración actual
UPDATE alembic_version SET version_num = 'unified_20250615' WHERE version_num = '20250608_150000' OR version_num = 'add_agents_system';

-- 2. Si la tabla alembic_version está vacía, insertar la versión actual
INSERT INTO alembic_version (version_num) 
SELECT 'unified_20250615' 
WHERE NOT EXISTS (SELECT 1 FROM alembic_version);

-- 3. Eliminar tablas de agentes (ahora manejadas por LangChain)
DROP TABLE IF EXISTS agent_messages CASCADE;
DROP TABLE IF EXISTS agent_executions CASCADE;
DROP TABLE IF EXISTS agent_conversations CASCADE;
DROP TABLE IF EXISTS agents CASCADE;
DROP TABLE IF EXISTS agent_tools CASCADE;

-- 4. Eliminar tabla de suscripciones (Stripe es la fuente de verdad)
DROP TABLE IF EXISTS subscriptions CASCADE;

-- 5. Agregar columnas faltantes a users si no existen
ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT false NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255);

-- 6. Crear índice para stripe_customer_id si no existe
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_stripe_customer_id ON users(stripe_customer_id);

-- Mensaje de confirmación
SELECT 'Migration fix completed successfully!' as message;