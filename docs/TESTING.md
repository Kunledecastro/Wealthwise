# Testing strategy (Phase 0 proposal)

## Layers

| Layer | Tooling | Focus |
|---|---|---|
| Ledger unit tests | pytest (+ Hypothesis property tests) | Every rule in `DATABASE.md §5`: transfers, refunds, reversals, pending→posted, failed, multi-currency rejection, rounding. Target **100% branch coverage of `app/ledger/`** |
| Backend integration | pytest + httpx `AsyncClient` against a real Postgres (testcontainer or local cluster), each test in a rolled-back transaction | API contracts, idempotent imports, dedupe, audit rows written |
| Authorisation suite | pytest, parametrised over every route | Two users; user B gets 404 for all of user A's resources; anonymous gets 401 |
| Security checks | ruff (incl. bandit rules), pip-audit, pnpm audit, Trivy | Run in CI; findings block merge above "medium" |
| Frontend | Vitest + Testing Library | Forms, money formatting (`₦1,234.56` from kobo), empty/error states |
| End-to-end | Playwright (desktop + mobile viewport) | Register → add account → add/import transactions → dashboard totals match ledger |
| Accessibility | axe-core in Playwright | No serious/critical violations on core pages |
| Migrations | `alembic upgrade head` / `downgrade -1` / `upgrade head` on empty DB | Every phase |

## Fixtures

- Golden statement files (synthetic, no real customer data) for CSV/XLSX/PDF adapters, each with a hand-calculated expected-totals file.
- A fixed seed generator for demo data, always flagged `is_demo = true`.

## Rules

- No phase is declared complete unless the commands were actually run; results are pasted into `PHASE_STATUS.md` with date.
- Any bug in a financial figure gets a regression test before the fix.

## Commands

```
make test        # backend + frontend unit/integration
make lint        # ruff, mypy, eslint, tsc --noEmit
make migrate-check
make e2e         # Playwright (requires stack running)
```

## Local test database

Backend tests run against a real PostgreSQL database `wealthwise_test`, as the real app role. Create it once with `make dev-db`. Tests run all migrations from scratch at the start of each session and clean the tables after each test.

## Latest results (Phase 1, 26 Oct 2026)

| Check | Result |
|---|---|
| pytest | 60 passed |
| vitest | 6 passed |
| ruff check / ruff format / mypy --strict | 0 issues |
| eslint / tsc --noEmit | 0 issues |
| next build | success |
| migrate-check (incl. `alembic check` drift) | OK |
| pip-audit / pnpm audit --prod | no known vulnerabilities |
| Mutation spot-check: CSRF middleware removed | 3 tests fail as expected |
| Playwright e2e / axe | **Not run** — browser download blocked in build workspace; planned for CI in a later phase |
