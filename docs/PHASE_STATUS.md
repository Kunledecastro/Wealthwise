# Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 | Discovery, architecture, data model, security design, dependencies, acceptance criteria | **Complete — awaiting approval** (26 Oct 2026) |
| 1 | Repo scaffold, Docker Compose, CI, FastAPI + Next.js skeleton, Postgres + Alembic, **authentication & user preferences** | Not started |
| 2 | Financial accounts, transactions (manual entry, edit with revisions, filters, statuses), **ledger engine + full unit tests** | Not started |
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

### Still needed before Phase 1

1. Approval of D-001 to D-013 and D-015.
2. The GitHub repository (owner/name) to push to.
