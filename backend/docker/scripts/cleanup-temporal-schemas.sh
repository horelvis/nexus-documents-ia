#!/usr/bin/env bash
set -euo pipefail

# Clean up Temporal schemas inside a specific database (default: nexus_db).
# Useful if an earlier setup used schemas (temporal, temporal_visibility) inside nexus_db.
#
# Usage (from backend/docker/):
#   docker compose exec db bash /docker-entrypoint-initdb.d/cleanup-temporal-schemas.sh            # drop only
#   docker compose exec db bash /docker-entrypoint-initdb.d/cleanup-temporal-schemas.sh recreate   # drop + recreate empty
#   TARGET_DB=mydb docker compose exec db bash /docker-entrypoint-initdb.d/cleanup-temporal-schemas.sh

ACTION_RECREATE=${1:-}
PGUSER=${POSTGRES_USER:-postgres}
TARGET_DB=${TARGET_DB:-nexus_db}

drop_schema() {
  local schema="$1"
  echo "Dropping schema ${schema} in ${TARGET_DB} (if exists)..."
  psql -v ON_ERROR_STOP=1 --username "$PGUSER" --dbname "$TARGET_DB" -c "DROP SCHEMA IF EXISTS ${schema} CASCADE;"
}

create_schema() {
  local schema="$1"
  echo "Creating schema ${schema} in ${TARGET_DB}..."
  psql -v ON_ERROR_STOP=1 --username "$PGUSER" --dbname "$TARGET_DB" -c "CREATE SCHEMA IF NOT EXISTS ${schema} AUTHORIZATION ${PGUSER};"
}

echo "[cleanup-temporal-schemas] Target DB: ${TARGET_DB}"

drop_schema temporal || true
drop_schema temporal_visibility || true

if [[ "${ACTION_RECREATE}" == "recreate" ]]; then
  create_schema temporal
  create_schema temporal_visibility
fi

echo "[cleanup-temporal-schemas] Done."

