# Decision log

Format: ID · status · decision · why · alternatives rejected. "Proposed" items need product-owner approval.

| ID | Status | Decision | Why | Rejected |
|---|---|---|---|---|
| D-001 | Proposed | Modular monolith: one FastAPI service + one Next.js service + Postgres | Smallest thing that meets every requirement; easy to self-host | Microservices (operational cost with no benefit at this scale) |
| D-002 | Proposed | Single origin via reverse proxy; Next.js `rewrites` in dev, Caddy in prod | First-party cookies, no CORS, simpler CSRF | Separate API domain with CORS + bearer tokens |
| D-003 | Proposed | Opaque server-side sessions in Postgres, not JWT | Instant revocation ("log out everywhere"), nothing sensitive in the browser | JWT access/refresh tokens; NextAuth/Auth.js (would split auth across two runtimes) |
| D-004 | Proposed | Money = positive `BIGINT` minor units + `direction` + `currency` | Exact arithmetic; avoids bank sign-convention bugs | Signed amounts; `NUMERIC`; floats |
| D-005 | Proposed | All money calculations live in `app/ledger/` and nowhere else | One source of truth; testable in isolation | Computing totals in SQL views and in the frontend |
| D-006 | Proposed | No Redis/Celery for MVP; DB-tracked jobs + FastAPI background tasks + cron-invoked CLI for scheduled jobs | Fewer moving parts; Redis added only when PDF/email ingestion load requires it | Celery from day one |
| D-007 | Proposed | Reporting date = `transaction_date` in user's timezone | Matches how users think about "when I spent it" | Posting date |
| D-008 | Proposed (deferred) | Postgres Row-Level Security as defence-in-depth | Belt-and-braces against authz bugs | — revisit in hardening phase |
| D-009 | Proposed | Package managers: **uv** (Python), **pnpm** (Node) | Fast, lockfile-based, both available in environment | pip-tools, poetry, npm |
| D-010 | Proposed | Psycopg 3 as Postgres driver | Mature, async-capable. Licence is **LGPL-3.0**: fine to use unmodified as a library in a self-hosted/SaaS app; flagged for your awareness | asyncpg (Apache-2.0) is the alternative if LGPL is unacceptable to you |
| D-011 | Proposed | TypeScript pinned to the latest 5.x/6.x line supported by the chosen Next.js release, not TS 7 | TS 7.0 (native Go compiler) is the current npm `latest`; Next.js/tooling compatibility must be confirmed before adopting | Using `latest` blindly |
| D-012 | Proposed | Rate limiting implemented in-app on Postgres (`auth_attempts`) | `slowapi` last released 0.1.10 and appears lightly maintained; our needs are narrow | slowapi; Redis-backed limiter |
| D-013 | Proposed | Ollama optional (compose profile `ai`), default off; deterministic fallback always present | Requirement; workspace and many servers lack the RAM/GPU for a useful model | Mandatory LLM |
| D-014 | Open question | Product name default: "SpendWise" (brief) vs "Wealthwise" (project name) | Both configurable via `APP_NAME`; need your choice for default branding | — |
