-- Create nouxcube database (main application database, single-tenant on-premise)
-- Executed on container first start (docker-entrypoint-initdb.d)
-- This script is idempotent: it will not fail if the database already exists

SELECT 'CREATE DATABASE nouxcube
    WITH OWNER = nexus_user
    ENCODING = ''UTF8''
    LC_COLLATE = ''C''
    LC_CTYPE = ''C''
    TEMPLATE = template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nouxcube')\gexec

GRANT ALL PRIVILEGES ON DATABASE nouxcube TO nexus_user;

\c nouxcube

ALTER DEFAULT PRIVILEGES FOR ROLE nexus_user GRANT ALL ON TABLES TO nexus_user;
ALTER DEFAULT PRIVILEGES FOR ROLE nexus_user GRANT ALL ON SEQUENCES TO nexus_user;
