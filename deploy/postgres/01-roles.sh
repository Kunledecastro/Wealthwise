#!/bin/sh
# Runs once, on first start of an empty Postgres volume.
# Creates separate roles: migrator (owns schema, runs DDL) and app (DML only).
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE wealthwise_migrator LOGIN PASSWORD '${WW_MIGRATOR_PASSWORD}';
CREATE ROLE wealthwise_app LOGIN PASSWORD '${WW_APP_PASSWORD}';
ALTER DATABASE "$POSTGRES_DB" OWNER TO wealthwise_migrator;
GRANT ALL ON SCHEMA public TO wealthwise_migrator;
GRANT USAGE ON SCHEMA public TO wealthwise_app;
CREATE EXTENSION IF NOT EXISTS citext;
SQL
