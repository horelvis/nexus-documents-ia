-- Create Camunda schema for BPMN workflow engine
-- This schema is used by Camunda 7 to store process definitions, instances, and tasks

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS camunda;

-- Grant permissions to the application user
GRANT ALL PRIVILEGES ON SCHEMA camunda TO nexus_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA camunda TO nexus_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA camunda TO nexus_user;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA camunda GRANT ALL ON TABLES TO nexus_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA camunda GRANT ALL ON SEQUENCES TO nexus_user;

-- Log creation
DO $$
BEGIN
    RAISE NOTICE 'Camunda schema created successfully';
END $$;
