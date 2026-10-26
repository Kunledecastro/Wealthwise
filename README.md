# Wealthwise

*Spend wisely. Grow steadily.*

Personal finance and spending intelligence web app for the Nigerian market (NGN default, Africa/Lagos timezone), built so that transaction accuracy comes before AI. v1 is for a small, invite-only group on a self-hosted server. Product name is configurable via `APP_NAME`.

## Status

**Phase 0 — design only.** No application code yet. See [`docs/PHASE_STATUS.md`](docs/PHASE_STATUS.md).

## Stack (proposed)

Next.js + TypeScript + Tailwind + shadcn/ui + Recharts · FastAPI + Pydantic + SQLAlchemy + Alembic · PostgreSQL 16 · optional Ollama · Docker Compose · Caddy (production TLS).

## Documentation

| Doc | Contents |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | System shape, modules, ingestion pipeline, AI layer, environment findings |
| [DATABASE](docs/DATABASE.md) | Data model, money conventions, dedupe, calculation rules |
| [SECURITY](docs/SECURITY.md) | Threat model, controls, regulatory review list |
| [TESTING](docs/TESTING.md) | Test layers and rules |
| [DECISIONS](docs/DECISIONS.md) | Decision log |
| [PHASE_STATUS](docs/PHASE_STATUS.md) | Roadmap, Phase 0 findings, dependency licences, Phase 1 acceptance criteria |

## Running locally

Available from Phase 1 (`cp .env.example .env && docker compose up`).
