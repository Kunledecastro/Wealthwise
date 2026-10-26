# Decision log

Format: ID · status · decision · why · alternatives rejected. "Proposed" items need product-owner approval.

| ID | Status | Decision | Why | Rejected |
|---|---|---|---|---|
| D-001 | **Accepted** (26 Oct 2026) | Modular monolith: one FastAPI service + one Next.js service + Postgres | Smallest thing that meets every requirement; easy to self-host | Microservices (operational cost with no benefit at this scale) |
| D-002 | **Accepted** (26 Oct 2026) | Single origin via reverse proxy; Next.js `rewrites` in dev, Caddy in prod | First-party cookies, no CORS, simpler CSRF | Separate API domain with CORS + bearer tokens |
| D-003 | **Accepted** (26 Oct 2026) | Opaque server-side sessions in Postgres, not JWT | Instant revocation ("log out everywhere"), nothing sensitive in the browser | JWT access/refresh tokens; NextAuth/Auth.js (would split auth across two runtimes) |
| D-004 | **Accepted** (26 Oct 2026) | Money = positive `BIGINT` minor units + `direction` + `currency` | Exact arithmetic; avoids bank sign-convention bugs | Signed amounts; `NUMERIC`; floats |
| D-005 | **Accepted** (26 Oct 2026) | All money calculations live in `app/ledger/` and nowhere else | One source of truth; testable in isolation | Computing totals in SQL views and in the frontend |
| D-006 | **Accepted** (26 Oct 2026) | No Redis/Celery for MVP; DB-tracked jobs + FastAPI background tasks + cron-invoked CLI for scheduled jobs | Fewer moving parts; Redis added only when PDF/email ingestion load requires it | Celery from day one |
| D-007 | **Accepted** (26 Oct 2026) | Reporting date = `transaction_date` in user's timezone | Matches how users think about "when I spent it" | Posting date |
| D-008 | **Accepted, deferred** to hardening phase | Postgres Row-Level Security as defence-in-depth | Belt-and-braces against authz bugs | — revisit in hardening phase |
| D-009 | **Accepted** (26 Oct 2026) | Package managers: **uv** (Python), **pnpm** (Node) | Fast, lockfile-based, both available in environment | pip-tools, poetry, npm |
| D-010 | **Accepted** (26 Oct 2026) | Psycopg 3 as Postgres driver | One driver for both async app code and sync Alembic migrations; SQLAlchemy's recommended Postgres driver. LGPL-3.0 permits use of the unmodified library in a self-hosted app | asyncpg (would need a second sync driver for migrations) |
| D-011 | **Accepted** (26 Oct 2026) | TypeScript pinned to the latest 5.x/6.x line supported by the chosen Next.js release, not TS 7 | TS 7.0 (native Go compiler) is the current npm `latest`; Next.js/tooling compatibility must be confirmed before adopting | Using `latest` blindly |
| D-012 | **Accepted** (26 Oct 2026) | Rate limiting implemented in-app on Postgres (`auth_attempts`) | `slowapi` last released 0.1.10 and appears lightly maintained; our needs are narrow | slowapi; Redis-backed limiter |
| D-013 | **Accepted** (26 Oct 2026) | Ollama optional (compose profile `ai`), default off; deterministic fallback always present | Requirement; workspace and many servers lack the RAM/GPU for a useful model | Mandatory LLM |
| D-014 | **Accepted** (26 Oct 2026) | Default product name **Wealthwise** (still configurable via `APP_NAME`) | Product owner decision | SpendWise |
| D-015 | **Accepted** (26 Oct 2026) | v1 audience is a small group: **invite-only registration** (admin creates single-use invite links); first user created via CLI becomes admin; public sign-up disabled by config | Product owner: small group. Removes open-registration abuse and lowers launch hardening burden | Open public sign-up with email verification |
| D-016 | **Accepted** (26 Oct 2026) | Code lives in a GitHub repository | Product owner decision | Files delivered from workspace |
| D-017 | Accepted (Phase 1) | Synchronous SQLAlchemy sessions with plain `def` endpoints | FastAPI runs them in a thread pool; simpler, fewer async pitfalls, ample for a small group. Async can be adopted per-module later | Async SQLAlchemy everywhere |
| D-018 | Accepted (Phase 1) | Invite and reset tokens travel in the URL **fragment** (`/register#invite=…`) and are removed from the address bar once read | Browsers never send fragments to servers, so tokens never appear in proxy or server access logs | Query-string tokens |
| D-019 | Accepted (Phase 1), revisit in hardening | CSP allows `'unsafe-inline'` scripts/styles | Required by Next.js without per-request nonces. Phase 13 moves to nonce-based CSP | Nonce middleware now (adds complexity before there is user content to protect) |
| D-020 | Accepted (Phase 1) | Database passwords for compose roles must be alphanumeric | The first-run init script interpolates them into SQL | Escaping logic in shell |
| D-021 | Accepted (Phase 1) | Explicit `db.commit()` in each endpoint; the request session only closes (and so rolls back) at the end | Guarantees nothing commits after an error response is chosen, and lets failed-login records persist even when the request returns 401 | Commit in dependency teardown |

