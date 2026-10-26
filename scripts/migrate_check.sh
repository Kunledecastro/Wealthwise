#!/usr/bin/env bash
# Upgrade → downgrade to empty → upgrade again on the TEST database.
set -euo pipefail
cd "$(dirname "$0")/../api"
DB="${TEST_DB_NAME:-wealthwise_test}"
HOST="${TEST_PG_HOST:-localhost}"
export MIGRATOR_DATABASE_URL="postgresql+psycopg://wealthwise_migrator:devpass@${HOST}:5432/${DB}"
export DATABASE_URL="postgresql+psycopg://wealthwise_app:devpass@${HOST}:5432/${DB}"
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
uv run alembic check   # fails if models and migrations have drifted
echo "migrate-check: OK"
