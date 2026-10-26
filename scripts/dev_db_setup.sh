#!/usr/bin/env bash
# One-time local Postgres setup for running the API and tests outside Docker.
# Requires a local PostgreSQL 16 server and permission to run psql as the postgres superuser.
set -euo pipefail
PSQL=(psql -v ON_ERROR_STOP=1)
if [ "$(id -un)" != "postgres" ]; then PSQL=(sudo -u postgres psql -v ON_ERROR_STOP=1); fi
"${PSQL[@]}" <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'wealthwise_migrator') THEN
    CREATE ROLE wealthwise_migrator LOGIN PASSWORD 'devpass'; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'wealthwise_app') THEN
    CREATE ROLE wealthwise_app LOGIN PASSWORD 'devpass'; END IF;
END $$;
SQL
for db in wealthwise wealthwise_test; do
  "${PSQL[@]}" -tc "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1 \
    || "${PSQL[@]}" -c "CREATE DATABASE $db OWNER wealthwise_migrator"
  "${PSQL[@]}" -d "$db" -c "CREATE EXTENSION IF NOT EXISTS citext; GRANT USAGE ON SCHEMA public TO wealthwise_app; GRANT ALL ON SCHEMA public TO wealthwise_migrator;"
done
echo "Local databases ready (dev password: devpass — local use only)."
