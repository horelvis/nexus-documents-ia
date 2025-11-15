#!/usr/bin/env bash
set -euo pipefail

# Clean up ONLY Temporal databases in the Postgres container (not the whole volume).
# - Drops databases: temporal, temporal_visibility
# - Optionally recreates them empty (pass arg: recreate)
# - Optionally bootstraps minimal schema_version (pass arg: bootstrap)
#
# Usage (from backend/docker/):
#   docker compose exec db bash /docker-entrypoint-initdb.d/cleanup-temporal-dbs.sh
#   docker compose exec db bash /docker-entrypoint-initdb.d/cleanup-temporal-dbs.sh recreate
#   docker compose exec db bash /docker-entrypoint-initdb.d/cleanup-temporal-dbs.sh recreate bootstrap

ACTION_RECREATE=${1:-}
ACTION_BOOTSTRAP=${2:-}

PGUSER=${POSTGRES_USER:-postgres}
PGDB=${POSTGRES_DB:-postgres}

terminate_conns() {
  local dbname="$1"
  echo "Terminating connections to ${dbname}..."
  psql -v ON_ERROR_STOP=1 --username "$PGUSER" --dbname "$PGDB" \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${dbname}' AND pid <> pg_backend_pid();" || true
}

drop_db() {
  local dbname="$1"
  echo "Dropping database ${dbname} (if exists)..."
  psql -v ON_ERROR_STOP=1 --username "$PGUSER" --dbname "$PGDB" -c "DROP DATABASE IF EXISTS ${dbname};"
}

create_db() {
  local dbname="$1"
  echo "Creating database ${dbname}..."
  psql -v ON_ERROR_STOP=1 --username "$PGUSER" --dbname "$PGDB" -c "CREATE DATABASE ${dbname};"
}

bootstrap_minimal() {
  local dbname="$1";
  local label="$2";
  echo "Bootstrapping minimal schema_version in ${dbname} (db_name='${label}')..."
  psql -v ON_ERROR_STOP=1 --username "$PGUSER" --dbname "$dbname" <<SQL
CREATE TABLE IF NOT EXISTS schema_version (
    version_partition INT NOT NULL,
    db_name VARCHAR(255) NOT NULL,
    creation_time TIMESTAMP,
    curr_version VARCHAR(64),
    min_compatible_version VARCHAR(64),
    PRIMARY KEY (version_partition, db_name)
);
INSERT INTO schema_version (version_partition, db_name, creation_time, curr_version, min_compatible_version)
VALUES (0, '${label}', NOW(), '1.0.0', '1.0.0')
ON CONFLICT (version_partition, db_name) DO NOTHING;
SQL
}

echo "[cleanup-temporal-dbs] Starting..."

# Stop active connections and drop
terminate_conns temporal || true
terminate_conns temporal_visibility || true
drop_db temporal
drop_db temporal_visibility

if [[ "${ACTION_RECREATE}" == "recreate" ]]; then
  create_db temporal
  create_db temporal_visibility

  if [[ "${ACTION_BOOTSTRAP}" == "bootstrap" ]]; then
    bootstrap_minimal temporal temporal
    bootstrap_minimal temporal_visibility temporal_visibility
  fi
fi

echo "[cleanup-temporal-dbs] Done."

