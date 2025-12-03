#!/usr/bin/env bash
set -euo pipefail

# This script ensures the Temporal databases exist before the Temporal auto-setup
# container runs schema migrations. Database names follow the docker-compose
# configuration but remain overridable via TEMPORAL_DBNAME variables.
TEMPORAL_DBNAME=${TEMPORAL_DBNAME:-temporalio-nexus}
TEMPORAL_VISIBILITY_DBNAME=${TEMPORAL_VISIBILITY_DBNAME:-temporalio-nexus_visibility}
LEGACY_TEMPORAL_ROLE=${LEGACY_TEMPORAL_ROLE:-postgres}
LEGACY_TEMPORAL_PASSWORD=${LEGACY_TEMPORAL_PASSWORD:-${POSTGRES_PASSWORD:-nexus_password}}

# Create databases (idempotent; ignore errors if already exist)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE DATABASE \"$TEMPORAL_DBNAME\"" || true
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE DATABASE \"$TEMPORAL_VISIBILITY_DBNAME\"" || true

# Ensure compatibility role for third-party images expecting the default postgres superuser.
if [[ -n "${LEGACY_TEMPORAL_ROLE}" ]]; then
  # Escape single quotes in password for safe interpolation inside SQL.
  ESCAPED_PASSWORD=${LEGACY_TEMPORAL_PASSWORD//\'/\'\'}
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
DO
\$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${LEGACY_TEMPORAL_ROLE}') THEN
        EXECUTE 'CREATE ROLE ${LEGACY_TEMPORAL_ROLE} WITH LOGIN SUPERUSER PASSWORD ''${ESCAPED_PASSWORD}''';
    ELSE
        EXECUTE 'ALTER ROLE ${LEGACY_TEMPORAL_ROLE} WITH LOGIN SUPERUSER PASSWORD ''${ESCAPED_PASSWORD}''';
    END IF;
END
\$\$;
SQL
fi

# Note: Temporal's auto-setup container runs the full schema migrations.
# We only need databases to exist; the server will manage schema_version tables.
echo "Temporal databases ensured ($TEMPORAL_DBNAME, $TEMPORAL_VISIBILITY_DBNAME)."
