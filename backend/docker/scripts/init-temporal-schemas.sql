-- Ensure dedicated schemas for Temporal exist within nexus_db
CREATE SCHEMA IF NOT EXISTS temporal AUTHORIZATION postgres;
CREATE SCHEMA IF NOT EXISTS temporal_visibility AUTHORIZATION postgres;

-- Optional: grant privileges (adjust as needed)
GRANT ALL ON SCHEMA temporal TO postgres;
GRANT ALL ON SCHEMA temporal_visibility TO postgres;

-- Optional: set default privileges for future tables (for postgres role)
ALTER DEFAULT PRIVILEGES IN SCHEMA temporal GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA temporal_visibility GRANT ALL ON TABLES TO postgres;
