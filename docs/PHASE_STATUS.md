# Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 | Discovery, architecture, data model, security design, dependencies, acceptance criteria | **Approved** (26 Oct 2026) |
| 1 | Repo scaffold, Docker Compose, CI, FastAPI + Next.js skeleton, Postgres + Alembic, **authentication & user preferences** | **Complete — awaiting review** (26 Oct 2026) |
| 2 | Financial accounts, transactions (manual entry, edit with revisions, filters, statuses), **ledger engine + full unit tests**, data export and account deletion | Not started |
| 3 | Ingestion framework + CSV/XLSX adapter, dedupe, import review screen, simulated bank events | Not started |
| 4 | Categories, rules engine, review queue, learn-from-correction | Not started |
| 5 | Dashboard and reports (CSV export, printable summary) | Not started |
| 6 | Budgets, thresholds, projections, suggested budgets | Not started |
| 7 | Savings goals and surplus calculation | Not started |
| 8 | Spending intelligence: recurring detection, duplicates, spikes, insights | Not started |
| 9 | In-app notifications | Not started |
| 10 | AI layer: Ollama client, tool layer, assistant, AI categorisation fallback | Not started |
| 11 | PDF statement adapter | Not started |
| 12 | Educational investment guidance | Not started |
| 13 | Security hardening, RLS, backup/restore drill, deployment guide, pre-launch regulatory checklist | Not started |
| Later | Email alerts ingestion; Open Banking (after regulatory/consent verification) | Deferred |

Ordering rationale: correctness of money (Phase 2) before ingestion volume (3) before anything that interprets money (5+). AI comes late on purpose — every AI feature depends on the ledger and tool layer being right.

---

## Phase 0 — findings

**Done**: environment inspected (see `ARCHITECTURE.md §7`); architecture, data model, security design, testing strategy and decision log written; dependency licences checked against npm and PyPI on 26 Oct 2026.

**Commands executed**: runtime/version checks, `docker info` (daemon not running), `pg_lsclusters` (cluster down), Ollama probe (not reachable), npm/PyPI metadata lookups. No tests exist yet; none were run.

### Dependency licences (latest versions observed 26 Oct 2026)

| Package | Version | Licence | Note |
|---|---|---|---|
| next | 16.4.3 | MIT | |
| react | 19.3.1 | MIT | |
| typescript | 7.0.2 | Apache-2.0 | Pin to version supported by Next (D-011) |
| tailwindcss | 4.3.3 | MIT | |
| shadcn/ui | (copied components) | MIT | Not an npm dependency; Radix primitives underneath |
| @radix-ui/* | 1.x | MIT | |
| recharts | 3.10.1 | MIT | |
| react-hook-form | 7.91.0 | MIT | |
| zod | 4.6.7 | MIT | |
| @hookform/resolvers | 6.0.0 | MIT | |
| lucide-react | 1.61.0 | ISC | |
| class-variance-authority | 0.7.1 | Apache-2.0 | |
| fastapi | 0.162.0 | MIT | |
| pydantic / pydantic-settings | 2.14.1 / 2.16.1 | MIT | |
| sqlalchemy | 2.1.6 | MIT | |
| alembic | 1.20.1 | MIT | |
| psycopg | 3.3.6 | **LGPL-3.0** | See D-010 |
| uvicorn | 0.54.0 | BSD-3-Clause | |
| argon2-cffi | 25.1.0 | MIT | |
| httpx | 0.28.1 | BSD-3-Clause | |
| structlog | 26.1.0 | MIT OR Apache-2.0 | |
| python-multipart | 0.0.32 | Apache-2.0 | |
| openpyxl | 3.1.5 | MIT | Phase 3 |
| pdfplumber | 0.11.10 | MIT | Phase 11 |
| pytest / pytest-asyncio | 9.1.1 / 1.4.1 | MIT / Apache-2.0 | |
| ruff / mypy | 0.17.2 / 2.4.0 | MIT | |
| celery / redis | 5.6.3 / 8.1.0 | BSD-3 / MIT | **Not used in MVP** (D-006) |
| slowapi | 0.1.10 | MIT | **Not used** (D-012) |
| PostgreSQL | 16 | PostgreSQL Licence | |
| Ollama | — | MIT | Model licences vary — check per model |
| Caddy | — | Apache-2.0 | Production proxy |

No dependency has a mandatory paid tier. External services with potential cost: SMTP provider (production password-reset emails), any hosting/VPS, optional external AI (off by default).

### Phase 1 acceptance criteria (proposed)

1. `docker compose up` on a clean Linux/macOS machine starts `db`, `api`, `web`; `GET /api/health` returns 200 with DB connectivity status.
2. `alembic upgrade head` creates users, preferences, sessions, reset tokens, auth_attempts, audit_events, currencies (NGN seeded); downgrade/upgrade round-trip passes.
3. An admin (created via CLI) can issue single-use invite links; an invited user can register, log in, log out, reset a password (email printed to console in dev), and update currency/timezone/notification preferences. Defaults: NGN, Africa/Lagos.
4. Passwords stored as Argon2id; session cookie is HttpOnly, SameSite=Lax, and Secure when `COOKIE_SECURE=true`.
5. 6th failed login within the window for the same email is rejected with 429 and logged.
6. State-changing requests without a valid CSRF token are rejected with 403.
7. User A cannot read or modify User B's profile/preferences (automated test).
8. Login, logout, password change/reset write `audit_events` rows; no password, token or email appears in plain text in logs (automated test).
9. Responsive login/register/settings pages with loading, error and success states; keyboard navigable.
10. `make lint`, `make test`, `make migrate-check` pass, with output recorded here.

### Known limitations / risks

- Docker daemon is not available in this workspace, so Compose cannot be run here. Phase 1 can be built and unit/integration-tested here (local Postgres), but **you must confirm `docker compose up` on your machine**.
- No Ollama here; AI features will be tested with the deterministic fallback unless you provide a machine with ≥16 GB RAM.
- PDF statement formats vary heavily between Nigerian banks; Phase 11 needs real (redacted) sample statements from you.
- Regulatory review (NDPA, CBN Open Banking, SEC) is out of scope for engineering and must happen before public launch.

### Decisions from product owner (26 Oct 2026)

- Name: **Wealthwise** (D-014). Driver: **Psycopg 3** (D-010). Code: **GitHub repository** (D-016). Audience: **small group** → invite-only (D-015, proposed).

All proposed decisions approved 26 Oct 2026. Repository: `Kunledecastro/Wealthwise` (public, by product-owner choice).

---

## Phase 1 — report (26 Oct 2026)

**Objective:** a runnable foundation with secure, invite-only sign-in and user preferences. No financial features.

### What was built

- **Backend (`api/`)**: FastAPI app with health check, invite-only registration, login/logout, logout on all devices, forgot/reset/change password, preferences, and admin endpoints for invites and users. There is also an admin CLI (`create-admin`, `invite`, `reset-link`).
- **Database**: Alembic migration `0001` (hand-reviewed) creates users, user_preferences, sessions, password_reset_tokens, invites, auth_attempts, audit_events and currencies (NGN seeded). It also creates the separate migrator and app roles. The app role cannot alter the audit trail or reference data.
- **Frontend (`web/`)**: Next.js 16 + TypeScript 5.9 + Tailwind 4 with shadcn-style components. Pages: sign in, register from invite, forgot password, reset password, home placeholder, settings (preferences, password, sign out everywhere) and admin (invites, people). It has light and dark themes and works on mobile.
- **Ops**: `compose.yaml` with db, one-shot migrate, api and web services, plus optional `ai` (Ollama) and `prod` (Caddy TLS) profiles. Also included: Dockerfiles running as non-root, a Makefile, and GitHub Actions CI.

### Acceptance criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | `docker compose up` starts db, api, web; health returns 200 | **Partly verified** | Images **build successfully in GitHub Actions**, and the compose file validates. Services ran successfully outside Docker with the same commands. The full stack was **not started in Docker** (base images can't be pulled in this workspace): confirm with M1. |
| 2 | Migration creates tables, NGN seeded, round-trip passes | Pass | `make migrate-check`: upgrade → downgrade → upgrade → `alembic check` (no drift) |
| 3 | Invite, register, login, logout, reset (console email), preferences with NGN / Africa/Lagos defaults | Pass | Automated tests, plus a manual walk-through over HTTP through the web origin |
| 4 | Argon2id hashes; cookie HttpOnly, SameSite=Lax, Secure when configured | Pass | `test_password_stored_as_argon2id`, `test_login_success_and_cookie_flags`, `test_secure_cookie_when_configured` |
| 5 | 6th failed login → 429 | Pass | `test_lockout_after_max_failed_attempts`; confirmed manually |
| 6 | Missing/invalid CSRF → 403 | Pass | 3 CSRF tests; removing the middleware makes them fail (checked) |
| 7 | User A cannot read/modify User B's data | Pass | Isolation test, anonymous-401 sweep, and a guard test that fails if a new route isn't classified |
| 8 | Audit rows written; no credentials/emails in logs | Pass | `test_audit_events_written`, `test_logs_do_not_contain_credentials`; manual log grep found 0 matches |
| 9 | Responsive pages with loading/error/success states, keyboard navigable | **Built; not visually verified** | Production build succeeds. A browser could not be installed here (download blocked), so layout and keyboard use need your manual check (below). |
| 10 | `make lint`, `make test`, `make migrate-check` pass | Pass | ruff, ruff format, mypy (strict), eslint and tsc: 0 issues. pytest: **60 passed**. vitest: **6 passed**. pip-audit and pnpm audit: no known vulnerabilities. |

### Bugs found and fixed during the phase

3. The first CI image build failed because corepack picked an unpinned pnpm version inside Docker. pnpm is now pinned via `packageManager`, and CI reports build errors as annotations.

1. A non-IP client address crashed requests when stored in the `inet` column. IPs are now validated first.
2. The CLI accepted emails that login rejects (e.g. `admin@x.local`), which could create an admin who can never sign in. Account creation now uses the same email validation; a regression test was added.

### How to run locally

See README → "Run it with Docker". Short version: `cp .env.example .env`, edit passwords, `docker compose up --build -d`, then create the admin with the CLI.

### Manual test cases (please run on your machine)

| # | Steps | Expected |
|---|---|---|
| M1 | `docker compose up --build -d`, then `docker compose ps` | db, api, web healthy; migrate exited 0 |
| M2 | Create admin via CLI; open http://localhost:3000 | Redirected to Sign in; sign-in lands on "Welcome, <name>" |
| M3 | Admin → Invite someone → Copy link → open in a private window | "Create your account" form; invite token no longer visible in the address bar |
| M4 | Register, then reopen the same invite link in another private window | "This invite link is invalid, expired or already used…" |
| M5 | Settings → change timezone and thresholds to `100, 70` → Save → reload | Values persist; thresholds shown as `70, 100` |
| M6 | Sign out → Forgot password → enter email → `docker compose logs api` | Reset link printed; it works once; afterwards old password fails |
| M7 | Enter a wrong password 6 times | 6th attempt says "Too many attempts…" |
| M8 | Sign in on two browsers → Settings → Sign out on all devices | Both browsers are back at Sign in |
| M9 | Phone (or browser dev tools at 375px width): all pages | No horizontal scrolling; buttons easy to tap |
| M10 | Keyboard only (Tab / Shift+Tab / Enter) through Sign in and Settings | Every control reachable, visible focus ring |

### Known limitations / risks

- Images build in CI, but the running compose stack is unverified (M1 covers this).
- Visual and keyboard testing not done here (M9, M10).
- CSP still allows inline scripts (D-019); this moves to nonces in hardening.
- Email in production needs an SMTP provider. Without one, use the CLI `reset-link` command.
- No email verification: acceptable for invite-only use, where invites can be bound to an email.
- Data export and account deletion move to Phase 2, where there is financial data to export.
- The repository is public: no secrets are committed (`.env` is git-ignored), but the security design is visible.

### Changed files (summary)

`api/` (new): `app/core` (config, logging/redaction, security, CSRF, email), `app/db` (models, session), `app/auth`, `app/users`, `app/admin`, `app/audit`, `app/cli.py`, `migrations/`, `tests/` (60 tests).
`web/` (new): `src/app/*` pages, `src/components/*`, `src/lib/*` (API client, schemas, money formatting, fragment-token hook), config files.
Root: `compose.yaml`, `.env.example`, `Makefile`, `deploy/` (Postgres init, Caddyfile), `scripts/`, `.github/workflows/ci.yml`, docs.

### Phase 2 preview (needs your approval)

Financial accounts (bank, wallet, cash, savings) with opening balances, and transactions (manual entry, edit history, statuses, filters). The **ledger engine** handles transfers, refunds, reversals and pending items, with exhaustive unit tests. Phase 2 also adds full data export and account deletion.
