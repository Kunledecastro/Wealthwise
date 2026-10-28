# Architecture (Phase 0 proposal)

Status: **Approved.** Implemented so far: auth (Phase 1), ledger and transactions (Phase 2), statement ingestion and reconciliation (Phase 3). Later sections describe planned work.

## 1. Guiding constraints

- Transaction accuracy over AI output. All money figures come from deterministic Python on database records.
- The core app must work with AI switched off, with no paid API, and fully self-hosted on one Linux server.
- Smallest architecture that can grow: one backend service, one frontend service, one database. Everything else is optional and added only when a phase justifies it.

## 2. Recommended shape: a modular monolith

```
                 Browser (desktop / tablet / mobile)
                               │  HTTPS (single origin)
                    ┌──────────▼───────────┐
                    │  Reverse proxy       │  Caddy (prod: TLS, headers)
                    └───┬──────────────┬───┘
               /        │              │  /api/*
          ┌─────────────▼───┐   ┌──────▼─────────────────────────────┐
          │ Next.js (web)   │   │ FastAPI (api) — modular monolith   │
          │ UI only, no     │   │  auth · accounts · transactions    │
          │ business logic, │   │  ingestion · categorisation        │
          │ no DB access    │   │  ledger (calc engine) · budgets    │
          └─────────────────┘   │  goals · insights · notifications  │
                                │  reports · assistant(tool layer)   │
                                └──────┬───────────────────┬─────────┘
                                       │                   │ optional
                               ┌───────▼──────┐   ┌────────▼────────┐
                               │ PostgreSQL 16│   │ Ollama (local)  │
                               └──────────────┘   └─────────────────┘
```

Key decisions (full rationale in `DECISIONS.md`):

1. **Single origin.** The browser only ever talks to one host. The proxy routes `/api/*` to FastAPI and everything else to Next.js. Session cookies are first-party, `SameSite=Lax`, no CORS needed. In local dev, Next.js `rewrites` play the proxy's role.
2. **FastAPI owns all business logic and all data access.** Next.js is a UI layer; it never connects to PostgreSQL and never computes a financial total.
3. **One calculation module (`app/ledger/`)** is the single source of truth (Phase 5: `app/reports/` serves the dashboard and reports by calling `summarize`, `time_series`, `by_category`, `by_merchant` and `previous_period`, with no sums of its own) for income, expense, net cash flow, balances, budget usage and projections. Dashboard, reports, budgets, insights and the AI assistant all call it. Nothing else sums money.
4. **No Redis/Celery in the MVP.** Imports run as tracked jobs (`import_batches` table) executed by FastAPI background tasks; scheduled work (recurring-bill detection, budget alerts) runs via a small in-process scheduler or a cron-invoked CLI command. Revisit when statement volume or recurring jobs justify a queue (decision D-006).
5. **Ollama is optional** and behind an interface with a deterministic fallback. The model never touches the database; it only receives results from whitelisted backend tool functions.

## 3. Backend module layout (planned)

```
api/
  app/
    core/          config, security (hashing, sessions, CSRF), logging/redaction, errors
    db/            SQLAlchemy engine/session, base model, Alembic env
    auth/          registration, login, logout, password reset, sessions
    users/         profile, preferences, export, deletion
    accounts/      financial accounts, opening balances, reconciliation points
    transactions/  CRUD, filters, revisions (audit), status lifecycle
    ingestion/     common interface + adapters: manual, csv/xlsx, pdf, simulated, (email), (open banking)
    categorisation/ categories, rules engine, AI fallback, review queue
    ledger/        *** single source of truth for money calculations ***
    budgets/  goals/  insights/  notifications/  reports/
    assistant/     tool registry, LLM client (Ollama), fallback responder
    audit/         audit event writer
  migrations/      Alembic
  tests/           unit (ledger heavy), integration (API + Postgres), security (authz)
```

Each module follows `router → service → repository`. **Every repository function takes `user_id` as a required argument** and filters on it; there is no "fetch by id" without an owner. This is the main defence against broken access control (see `SECURITY.md`).

## 4. Ingestion pipeline

```
Adapter (manual | csv/xlsx | pdf | simulated | email* | open banking*)
   └─► RawRecord[]  ──► normalise ──► NormalisedTransaction (one schema)
          ──► validate (currency, precision, dates, sign)
          ──► dedupe (external_ref, then fingerprint)
          ──► categorise (rules → optional AI → "needs review")
          ──► staged in import_rows  ──► user reviews  ──► commit in one DB transaction
```

- Imports are **idempotent**: re-uploading the same file produces zero new transactions.
- *Phase 3 status:* manual, CSV, XLSX, XLS and simulated adapters are implemented in `api/app/ingestion/` (readers → detect → normalise → service). PDF, email alerts and Open Banking remain planned.
- Nothing from a file is committed without passing through the review screen (manual entry is the exception).
- `*` email alerts and Open Banking are deferred until the core engine is stable and the regulatory/consent position is verified. No screen scraping, no bank credentials — ever.

## 5. AI layer

- `assistant/tools.py` exposes a fixed set of read-only functions (e.g. `spend_by_category(period)`, `compare_periods(a, b)`, `affordability(amount)`), each validated with Pydantic and bound to the authenticated `user_id` server-side — the model cannot pass a user id.
- The LLM only phrases answers around tool outputs; figures shown to the user come from the tool result, not the model's text.
- If Ollama is down or disabled, a deterministic templated responder answers the same tool-backed questions.
- External models: off by default; enabling requires explicit, recorded user consent.

## 6. Deployment

- Local dev: `docker compose up` → `db`, `api`, `web` (+ `ollama` under an opt-in compose profile).
- Production (self-hosted Linux): same compose file plus `caddy` for TLS, Postgres on an encrypted volume, nightly encrypted `pg_dump` backups.
- Configuration only via environment variables (`.env.example`).

## 7. Environment findings (Phase 0 inspection, 26 Oct 2026)

| Item | Found in this workspace | Note |
|---|---|---|
| OS | Ubuntu 24.04.5, x86_64, 2 vCPU, 7.8 GB RAM | Fine for dev; too small to run a useful local LLM alongside Postgres |
| Python | 3.13.17, pip, uv 0.11, poetry 2.4 | Recommend **uv** for dependency management |
| Node | 22.23 (LTS), npm 10.9, pnpm 10.28 | Recommend **pnpm** |
| PostgreSQL | 16.15 installed, cluster stopped | Can be started for tests |
| Redis | 7.0 binary present | Not needed for MVP |
| Docker | CLI 29.9 + Compose v5.6 present, **daemon not running** | Compose files can be written but not run here; must be verified on your machine |
| Ollama | Not installed / not reachable | AI features must be tested on your hardware or skipped with the fallback |
| Repository | **None** — empty home directory, no git repo | Phase 1 starts from a fresh repo |
