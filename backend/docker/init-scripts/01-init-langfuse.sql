-- Create Langfuse database (separate from main application)
-- Executed on container first start (docker-entrypoint-initdb.d)

CREATE DATABASE langfuse
    WITH OWNER = nexus_user
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C'
    TEMPLATE = template0;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE langfuse TO nexus_user;

\c langfuse

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES FOR ROLE nexus_user GRANT ALL ON TABLES TO nexus_user;
ALTER DEFAULT PRIVILEGES FOR ROLE nexus_user GRANT ALL ON SEQUENCES TO nexus_user;
