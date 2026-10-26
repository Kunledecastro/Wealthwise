.PHONY: help up down logs admin invite dev-db dev-api dev-web test test-api test-web lint migrate-check audit

help:
	@echo "Docker:  make up | down | logs | admin EMAIL=you@x.com NAME=You | invite"
	@echo "Local:   make dev-db | dev-api | dev-web"
	@echo "Checks:  make test | lint | migrate-check | audit"

# ---- Docker ----
up:
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f api web
admin:
	docker compose run --rm -it api python -m app.cli create-admin --email "$(EMAIL)" --name "$(NAME)"
invite:
	docker compose run --rm api python -m app.cli invite

# ---- Local development (no Docker) ----
dev-db:
	./scripts/dev_db_setup.sh
	cd api && MIGRATOR_DATABASE_URL=postgresql+psycopg://wealthwise_migrator:devpass@localhost:5432/wealthwise uv run alembic upgrade head
dev-api:
	cd api && uv run uvicorn app.main:app --reload --port 8000
dev-web:
	cd web && pnpm dev

# ---- Checks ----
test: test-api test-web
test-api:
	cd api && uv run pytest
test-web:
	cd web && pnpm test

lint:
	cd api && uv run ruff check . && uv run ruff format --check . && uv run mypy app
	cd web && pnpm lint && pnpm typecheck

migrate-check:
	./scripts/migrate_check.sh

audit:
	cd api && uv run pip-audit
	cd web && pnpm audit --prod
