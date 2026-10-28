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

## Latest results (Phase 2, 26 Oct 2026)

| Check | Result |
|---|---|
| pytest (all backend) | 158 passed |
| Ledger engine branch coverage | **100%** (CI fails below 100%) |
| Property tests (Hypothesis, 200 cases each) | 5 properties: order independence, transfers neutral, reversal = never happened, balance = opening + signed posted, period split adds up |
| vitest | 10 passed (incl. exact naira→kobo parsing) |
| ruff / mypy --strict / eslint / tsc / next build | clean |
| migrate-check incl. drift | OK |
| Manual end-to-end via web origin | balances and monthly totals match hand calculation |

## Latest results (Phase 3, 28 Oct 2026)

| Check | Result |
|---|---|
| pytest (all backend) | 286 passed |
| Ledger engine branch coverage | 100% (incl. new rule B5) |
| Ingestion package coverage | 92% |
| Statement layouts tested end to end | CSV debit/credit (preamble, newest-first), CSV signed amount, CSV semicolon + DR/CR, .xlsx money in/out, .xls withdrawals/lodgements |
| vitest / eslint / tsc / next build | clean |
| migrate-check incl. drift | OK |
| pip-audit | no known vulnerabilities |
| Live run via web origin | GTBank-style CSV → 9 rows, statement balance matched; same statement as .xlsx → 9 duplicates; Kuda credit matched as transfer; simulated events reconciled; 11 MB upload → clear 413 |
| CI | now also imports a sample statement through the running Docker stack (`scripts/smoke_import.sh`) |

## Latest results (Phase 4, 28 Oct 2026)

| Check | Result |
|---|---|
| pytest (all backend) | 360 passed |
| Ledger engine branch coverage | 100% (incl. R13–R14 spending by category, plus a property test that categories always add up to totals) |
| Categorisation package coverage | 90% (engine 96%) |
| vitest / eslint / tsc / next build | clean |
| migrate-check incl. drift | OK |
| Upgrade backfill on dev data | 50 existing transactions categorised; 4 sent to review; categories summed exactly to the month's net spending |

## Latest results (Phase 5, 28 Oct 2026)

| Check | Result |
|---|---|
| pytest (all backend) | 402 passed |
| Ledger engine branch coverage | 100% (incl. R15–R18: trend buckets, merchants, comparison period, % change; property tests that buckets and merchants add up to the period totals) |
| vitest | 14 passed (incl. period presets, URL parsing, labels, compact axis values) |
| eslint / tsc / next build | clean |
| Chart palette | spending/income pair passes every check of the dataviz validator against #ffffff (light) and #161d1a (dark) |
| Visual check | headless Chromium screenshots of Home, Reports and Print at 1280px and 390px, light and dark; print view rendered to a one-page A4 PDF |
| Live run via web origin | after the sample import, October series, categories and merchants each summed to ₦126,056.94; CSV figures matched the screen |

## Latest results (Phase 6, 28 Oct 2026)

| Check | Result |
|---|---|
| pytest (all backend) | 431 passed |
| Ledger engine branch coverage | 100% (incl. R19–R24; property tests that budget lines + unbudgeted = total spending and that line figures stay consistent for any amounts and dates) |
| vitest | 16 passed (incl. month names and strict threshold parsing) |
| eslint / tsc / next build | clean |
| migrate-check incl. drift | OK (0005 up/down/up) |
| Live UI flow (headless Chromium) | seeded Jul–Oct spending → 5 suggestions matching hand calculation (e.g. ₦62,000 · ₦71,500 · ₦58,000 → ₦64,000) → created from suggestions, added ₦150,000 overall limit, saved; screenshots at 1280px and 390px, light and dark; Home budget card |
