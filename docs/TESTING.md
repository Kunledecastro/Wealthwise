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

## Commands (to exist from Phase 1)

```
make test        # backend + frontend unit/integration
make lint        # ruff, mypy, eslint, tsc --noEmit
make migrate-check
make e2e         # Playwright (requires stack running)
```
