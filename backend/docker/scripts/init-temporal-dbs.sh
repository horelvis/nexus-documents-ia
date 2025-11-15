#!/usr/bin/env bash
set -euo pipefail

# This script ensures the Temporal databases (temporal, temporal_visibility)
# exist before the Temporal auto-setup container runs schema migrations.

# Create databases (idempotent; ignore errors if already exist)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE DATABASE temporal" || true
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE DATABASE temporal_visibility" || true

# Note: Temporal's auto-setup container runs the full schema migrations.
# We only need databases to exist; the server will manage schema_version tables.
echo "Temporal databases ensured (temporal, temporal_visibility)."
