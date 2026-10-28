# Wealthwise

*Spend wisely. Grow steadily.*

Personal finance and spending intelligence web app for the Nigerian market (NGN default, Africa/Lagos timezone), built so that transaction accuracy comes before AI. v1 is for a small, invite-only group on a self-hosted server. Product name is configurable via `APP_NAME`.

## Status

**Phase 6 complete (awaiting product-owner review).** Sign-in and invites (1); accounts, transactions and the ledger engine (2); bank statement import with duplicate detection and balance checks (3); automatic categories with reasons, your own rules, a review queue and spending by category (4); a dashboard with period comparisons and trend charts, reports with CSV export, and a printable summary (5); monthly budgets with alert levels, pace estimates, suggestions and carry-over (6). See [`docs/PHASE_STATUS.md`](docs/PHASE_STATUS.md).

## Run it with Docker (recommended)

Requires Docker with Compose v2.

```bash
cp .env.example .env
# edit .env: set the three database passwords (letters and digits only) and SECRET_KEY
docker compose up --build -d
docker compose run --rm -it api python -m app.cli create-admin --email you@example.com --name "Your Name"
```

Open http://localhost:3000 and sign in. Create invites from **Admin** in the app, or with
`docker compose run --rm api python -m app.cli invite`.

In development, password-reset emails are printed in the API log: `docker compose logs api`.
If someone is locked out, `docker compose run --rm api python -m app.cli reset-link --email them@example.com` prints a one-time reset link.

## Run it without Docker (development)

Requires PostgreSQL 16, Python 3.13 with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm.

```bash
make dev-db            # creates local roles/databases (dev password "devpass") and migrates
cd api && uv sync && cd ../web && pnpm install && cd ..
make dev-api           # terminal 1 — http://localhost:8000/api/docs
make dev-web           # terminal 2 — http://localhost:3000
cd api && uv run python -m app.cli create-admin --email you@example.com --name "You"
```

## Checks

```bash
make lint            # ruff, mypy, eslint, tsc
make test            # pytest (needs the local test database) + vitest
make migrate-check   # upgrade → downgrade → upgrade + drift check
make audit           # pip-audit + pnpm audit
```

CI runs the same checks on every push (`.github/workflows/ci.yml`).

## Production (self-hosted Linux)

Set `APP_ENV=production`, `COOKIE_SECURE=true`, `APP_BASE_URL=https://your.domain`, `DOMAIN=your.domain`, a strong `SECRET_KEY`, and SMTP settings, then
`docker compose --profile prod up -d`. Caddy obtains TLS certificates automatically. Port 3000 is bound to localhost by default, so outside traffic can only arrive through Caddy. The API refuses to start with unsafe production settings. A full deployment and backup guide comes in the hardening phase.

## Documentation

| Doc | Contents |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | System shape, modules, ingestion pipeline, AI layer |
| [DATABASE](docs/DATABASE.md) | Data model, money conventions, dedupe, calculation rules |
| [SECURITY](docs/SECURITY.md) | Threat model, controls and their status, regulatory review list |
| [TESTING](docs/TESTING.md) | Test layers, how to run, latest results |
| [DECISIONS](docs/DECISIONS.md) | Decision log |
| [PHASE_STATUS](docs/PHASE_STATUS.md) | Roadmap and per-phase reports |
| [MANUAL_TESTS](docs/MANUAL_TESTS.md) | Step-by-step manual checks for the current phase |
