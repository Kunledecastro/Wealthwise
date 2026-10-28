# Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 | Discovery, architecture, data model, security design, dependencies, acceptance criteria | **Approved** (26 Oct 2026) |
| 1 | Repo scaffold, Docker Compose, CI, FastAPI + Next.js skeleton, Postgres + Alembic, **authentication & user preferences** | **Accepted** (26 Oct 2026) |
| 2 | Financial accounts, transactions (manual entry, edit with revisions, filters, statuses), **ledger engine + full unit tests**, data export, account deletion, email change | **Accepted** (28 Oct 2026, manual checks not reported) |
| 3 | Ingestion framework + CSV/XLSX/XLS adapters, dedupe, import review screen, transfer & reversal matching, reconciliation, undo, simulated bank events | **Accepted** (28 Oct 2026) |
| 4 | Categories, rules engine, review queue, learn-from-correction, spending by category | **Accepted** (28 Oct 2026, manual checks not reported) |
| 5 | Dashboard and reports: period selector, comparisons, trend charts, top categories and merchants, CSV export, printable summary | **Accepted** (28 Oct 2026, manual checks not reported) |
| 6 | Budgets, thresholds, projections, suggested budgets, carry-over | **Complete — awaiting your manual checks** (28 Oct 2026) |
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

### Manual test results (product owner, Windows, 26 Oct 2026)

M1–M10: **all pass.**

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
| 1 | `docker compose up` starts db, api, web; health returns 200 | Pass | CI on Linux (full stack, simulated Windows checkout) **and** the product owner's Windows PC (M1) |
| 2 | Migration creates tables, NGN seeded, round-trip passes | Pass | `make migrate-check`: upgrade → downgrade → upgrade → `alembic check` (no drift) |
| 3 | Invite, register, login, logout, reset (console email), preferences with NGN / Africa/Lagos defaults | Pass | Automated tests, plus a manual walk-through over HTTP through the web origin |
| 4 | Argon2id hashes; cookie HttpOnly, SameSite=Lax, Secure when configured | Pass | `test_password_stored_as_argon2id`, `test_login_success_and_cookie_flags`, `test_secure_cookie_when_configured` |
| 5 | 6th failed login → 429 | Pass | `test_lockout_after_max_failed_attempts`; confirmed manually |
| 6 | Missing/invalid CSRF → 403 | Pass | 3 CSRF tests; removing the middleware makes them fail (checked) |
| 7 | User A cannot read/modify User B's data | Pass | Isolation test, anonymous-401 sweep, and a guard test that fails if a new route isn't classified |
| 8 | Audit rows written; no credentials/emails in logs | Pass | `test_audit_events_written`, `test_logs_do_not_contain_credentials`; manual log grep found 0 matches |
| 9 | Responsive pages with loading/error/success states, keyboard navigable | Pass | Product owner manual checks M9 (mobile) and M10 (keyboard) |
| 10 | `make lint`, `make test`, `make migrate-check` pass | Pass | ruff, ruff format, mypy (strict), eslint and tsc: 0 issues. pytest: **60 passed**. vitest: **6 passed**. pip-audit and pnpm audit: no known vulnerabilities. |

### Bugs found and fixed during the phase

3. First-run database setup failed on Windows: Git converted the init script to CRLF line endings, and the DB health check reported "ready" during first-time initialisation, so `migrate` connected too early. Fixed with a small DB image that strips CRLF, a TCP health check, `.gitattributes`, and a CI job that now starts the whole stack.
4. The first CI image build failed because corepack picked an unpinned pnpm version inside Docker. pnpm is now pinned via `packageManager`, and CI reports build errors as annotations.

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

### Manual test results (product owner, Windows, 26 Oct 2026)

M1–M10: **all pass.**

### Known limitations / risks

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

Financial accounts (bank, wallet, cash, savings) with opening balances, changing your sign-in email from Settings, and transactions (manual entry, edit history, statuses, filters). The **ledger engine** handles transfers, refunds, reversals and pending items, with exhaustive unit tests. Phase 2 also adds full data export and account deletion.

---

## Phase 2 — report (26 Oct 2026)

**Objective:** record money accurately. You can create accounts, enter and correct transactions, and see balances and monthly totals calculated by one tested engine. This phase also covers data export, account deletion and changing your sign-in email.

### What was built

- **Ledger engine** (`api/app/ledger/`): a pure calculation module with no database access, plus `RULES.md` (R1–R12, B1–B4). It has 100% branch coverage and five property tests.
- **Migration 0002**:
  - New tables: accounts, transactions, transaction_revisions.
  - A composite foreign key means the database itself refuses to link a transaction to another user's account.
  - Database checks enforce positive amounts, valid kind/direction pairs, transfer and reversal links, and the last-4-digits mask format.
- **API**:
  - Accounts: create, list, edit, archive, and delete if never used.
  - Transactions: create; two-sided transfers; edit with revision history; soft delete; reverse; mark pending as completed or failed.
  - List with filters, search and pages; CSV export.
  - Monthly summary in your timezone.
  - JSON export of everything; email change; delete my account; admin make/remove admin.
- **Screens**:
  - Home: this month's income, spending, net cash flow and pending, plus balances and total.
  - Accounts and Transactions, with a detail panel showing full history and actions.
  - Settings: change email, download data, delete account.
  - Admin: role toggle.

### Acceptance criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Accounts with type, currency, opening balance and date; labelled manual/estimated | Pass | `test_create_account_is_manual_and_estimated`, validation tests; clients cannot set `source=connected` |
| 2 | Income, expense, fee, refund, adjustment with all fields and statuses | Pass | `test_finance.py` |
| 3 | Transfers saved as two linked entries in one step; never income or spending | Pass | `test_transfer_two_legs_atomic_and_not_pnl`, property test |
| 4 | Every edit and delete in viewable history; deleted rows excluded but kept | Pass | `test_edit_creates_revision_history`, `test_soft_delete_excluded_but_audited` |
| 5 | Calculation rules | Pass | `RULES.md` R1–R12 each tested; 100% branch coverage |
| 6 | Balance = opening + posted on/after opening date, plus a figure including pending | Pass | B1–B3 tests, API tests |
| 7 | List filters, search, pages ≤100 | Pass | `test_list_filters_search_and_pagination` (incl. literal `%` search) |
| 8 | Home: month totals in your timezone, balances per account | Pass | `test_summary_defaults_to_current_month`; manual run matched hand calculation |
| 9 | Email change (password), JSON + CSV export, delete account (password + DELETE), last admin protected | Pass | `test_my_data.py` incl. CSV formula-injection guard |
| 10 | Tests per rule, property tests, user isolation, CI green | Pass | 158 backend tests; the isolation test covers every finance endpoint; anonymous-401 sweep is now automatic for all routes |

### Bugs found and fixed during the phase

1. The API silently accepted the text `"100"` as an amount. Money fields are now strict integers (test added).
2. A deprecated SQLAlchemy call broke the link lookups for refunds and reversals. Replaced, and covered by tests.
3. An unknown transaction type would have been silently ignored by the engine. It now fails loudly (test added).

### Upgrading your running copy

```
git pull
docker compose up --build -d
```
The new tables are added automatically by `migrate`. Your existing login is kept and nothing needs resetting.

### Known limitations

- Balances are always **estimates**. Reconciling against bank statements arrives with statement import (Phase 3).
- Only NGN is enabled. Multi-currency is supported by the data model but not switched on.
- No categories yet (Phase 4). Spending is shown as a total, not by category.
- Email change has no verification link (D-028). Account deletion is immediate (D-027).
- Summaries load all transactions for the period. That's fine for a small group, and will be optimised if volumes grow.

### Phase 3 preview (needs your approval)

- Import CSV and Excel bank statements (Nigerian bank formats), with a review screen before anything is saved.
- Duplicate detection, so re-importing the same file adds nothing.
- Simulated bank events for testing.
- Reconciling a computed balance against the statement balance.

---

## Phase 3 — report (28 Oct 2026)

**Objective:** bring transactions in from bank statement files safely and accurately, never double counting, and show whether each account's balance agrees with the bank.

### What was built

- **Ingestion pipeline** (`api/app/ingestion/`):
  - Readers for CSV (any common delimiter, UTF-8 or Windows encoding), .xlsx and .xls, with size, row and zip-bomb limits.
  - Exact date and amount parsing (no floating point). Dates use DMY by default with automatic detection; amounts handle ₦, commas, brackets and DR/CR suffixes.
  - Header-row detection under preamble lines, plus column-role guessing.
  - Normalisation into one schema, with masking of account and card numbers and kind suggestions (bank fees, refunds, reversals).
  - A running-balance check that detects swapped columns.
- **Duplicates:** an exact fingerprint (with an occurrence index so identical twin charges are both kept), references used only when unique within the file, and possible duplicates against manual entries.
- **Matching:** own-account transfers within 2 days, and reversals linked to their original (same file or already saved). An unmatched reversal is saved as a refund.
- **Commit** is one database transaction. It can set the starting balance from the statement, records the statement's closing balance and remembers the column layout per account. **Undo** removes everything an import added and restores what it changed, including transfer partners in other accounts.
- **Reconciliation** (ledger rule B5): accounts show *Matches statement*, *Differs by ₦X* or *Estimated*. You can also check a balance by hand against your banking app, with a history of checks.
- **Simulated bank events** in demo mode only.
- **Screens:**
  - Imports list and upload.
  - Review: filter tabs, include/skip, type changes, a column editor with a preview of the file.
  - Result panel with the balance check.
  - Accounts: badges, "Import statement" and "Check against bank".
- **Ops:** new settings `DEMO_MODE` and `UPLOAD_MAX_MB`; synthetic sample statements in `docs/samples/`; CI imports a sample through the running Docker stack.

### Acceptance criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Upload CSV / XLSX / XLS with limits; original not kept | Pass | 5 layouts tested; size → 413, rows, zip, HTML and PDF rejections tested; `grid` cleared (test) |
| 2 | Columns detected; correctable; remembered per account | Pass | `test_role_for`, `test_remap_columns`, `test_mapping_is_remembered_per_account` |
| 3 | Review before saving; rows marked new / duplicate / possible duplicate / problem | Pass | `test_upload_detects_columns_and_stages_rows` (nothing saved before commit) |
| 4 | Re-importing adds nothing; twins kept | Pass | `test_reimporting_same_file_adds_nothing` (incl. the same statement as .xlsx), `test_genuine_identical_twins_both_kept` |
| 5 | Fees, refunds and reversals suggested; reversals linked | Pass | `test_suggest_kind`, `test_commit_creates_transactions_links_reversal_and_reconciles`, `test_reversal_of_existing_manual_transaction` |
| 6 | Own-account transfers matched, not counted twice | Pass | `test_transfer_matched_across_accounts_not_counted_twice` |
| 7 | Statement balance compared; matches / differs shown; manual checks | Pass | B5 ledger test, `test_manual_reconcile` (an old edit breaks the match), live run |
| 8 | Undo restores everything | Pass | `test_undo_removes_everything_and_allows_reimport`, `test_undo_restores_manual_transaction_converted_to_transfer` |
| 9 | Simulated events only in demo mode, labelled | Pass | `test_simulate_requires_demo_mode`, `test_simulated_events_flow` |
| 10 | Isolation, security, CI | Pass | `test_users_cannot_touch_each_others_imports`, anonymous-401 sweep covers all new routes; 286 tests |

### Bugs found and fixed during the phase

1. "Clearing" the staged grid saved a JSON `null` rather than an empty database field. Fixed, and covered by tests.
2. A remembered column layout wasn't reused when the headers were unrecognisable on their own. Saved layouts are now matched on any of the first 40 rows.
3. Undo wrote a duplicate entry in the history of a transaction it restored. A missing flush; fixed.
4. Through the local web server, uploads over 10 MB were cut off and showed "Internal Server Error". The proxy limit is now raised, so the API's clear "file is larger than 10 MB" message gets through.

### Upgrading your running copy

```
git pull
docker compose up --build -d
```
Migration 0003 runs automatically. The new settings are optional: `DEMO_MODE` defaults to false and `UPLOAD_MAX_MB` to 10.

### Known limitations

- **Formats are inferred, not verified against real bank exports.** I had no real statements from Nigerian banks. If a file isn't detected, choose the columns once and they're remembered. Sharing a redacted export lets me add an exact preset.
- PDF statements are still Phase 11. Many Nigerian banks email PDFs; download the CSV or Excel version where the bank offers one.
- If rows within the same day appear in an unusual order, the running-balance check may not use the closing balance. The import still works; only the automatic balance check is skipped, with a warning.
- Transfer matching needs both sides within 2 days and the exact same amount. A transfer whose fee is included in the amount won't match automatically; change the type in review instead.
- Demo transactions count in totals while they exist. Undo the simulated import to remove them.

---

## Phase 4 — report (28 Oct 2026)

**Objective:** every transaction gets a trustworthy category with a visible reason; uncertain ones go to a review queue; your corrections can become rules; spending is broken down by category with the same accuracy as all other totals.

### What was built

- **22 default categories** for every user, existing users included (seeded by migration 0004). You can add, rename, recolour, archive, merge or delete your own.
- **Categorisation engine** (`api/app/categorise/engine.py`, pure and deterministic):
  - Your choice wins.
  - Then fixed types: fees, transfers, and refunds or reversals linked to their original.
  - Then your rules.
  - Then built-in recognition of about 150 common Nigerian merchants and words.
  - Anything left goes to review.
  - Every result has a confidence and a reason. Generic words are suggestions only.
- **Merchant normalisation**, e.g. "POS PURCHASE SHOPRITE LEKKI ••••7895" → "SHOPRITE LEKKI". Used for rules and suggestions.
- **Rules**: contains / starts with / exact merchant, with optional account restriction, priority, pause and hit counts. You can preview "N would change", apply a rule to existing transactions, and "Re-run my rules".
- **Learning from corrections**: after you pick a category, Wealthwise offers an editable rule and to update similar transactions. Nothing happens unless you accept.
- **To review queue**: confirm, change or bulk-assign, or deliberately leave transactions uncategorised. The nav badge and a Home alert show the count.
- **Categories everywhere**: manual entry (Automatic by default), the transaction detail panel (with reason and history), transaction filters (by category, "needs a category"), import review rows, CSV and JSON export.
- **Spending by category** (ledger rules R13–R14) for any month, on the Categories page.
- **Upgrade backfill**: the migrate service runs `categorise-pending` automatically.

### Acceptance criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Default and custom categories; edit, archive, merge, delete safely | Pass | `test_create_rename_archive_delete`, `test_delete_used_category_refused_merge_instead` |
| 2 | Rules before built-in recognition; built-in before review | Pass | engine precedence tests, `test_rule_beats_builtin_and_respects_filters` |
| 3 | Category + confidence + reason on every transaction | Pass | `test_automatic_categories_with_reasons` |
| 4 | Uncertain → review queue; bulk tools | Pass | `test_bulk_assign_modes`, review-count tests |
| 5 | Learn from corrections via explicit, opt-in rules; never overwrite user choices | Pass | `test_rule_suggestion_after_correction`, `test_create_rule_applies_to_existing_but_not_user_choices`, `test_user_choice_is_never_overwritten` |
| 6 | Refunds/reversals inherit; transfers/fees fixed | Pass | `test_refund_and_reversal_inherit_category`, `test_transfers_and_adjustments` |
| 7 | Import review shows and honours categories; undo restores | Pass | `test_import_suggests_categories_and_honours_changes`, `test_transfer_match_recategorises_partner_and_undo_restores` |
| 8 | Spending by category adds up to totals | Pass | R13–R14 + property test; API test; live run (₦637,335.72 both ways) |
| 9 | Existing data categorised on upgrade | Pass | `test_cli_categorise_pending`; dev-data backfill |
| 10 | Isolation, security, CI | Pass | `test_users_cannot_touch_each_others_categories`, anonymous sweep covers all new routes; 360 tests |

### Upgrading your running copy

```
git pull
docker compose up --build -d
```
The migration adds the categories, and the migrate step then categorises your existing transactions. Open **To review** to handle the uncertain ones.

### Known limitations

- Built-in recognition is a fixed word list, so local businesses won't be recognised until you teach Wealthwise with a rule (one click after a correction).
- No sub-categories yet.
- Person-to-person transfers ("NIP TRF TO CHIOMA") can't be guessed. They go to review, where one correction plus a rule handles the rest.
- AI suggestions are planned for Phase 10. They will only ever be suggestions, behind your rules.

## Phase 5 — report (28 Oct 2026)

**Objective:** a dashboard and reports built only from your ledger, where every figure ties back to the transactions behind it.

### What was built

- **Ledger engine, rules R15–R18** (`api/app/ledger/engine.py`, documented in RULES.md):
  - **Trend buckets** by day, week (starting on your chosen first weekday) or calendar month. Empty buckets are included and partial first/last buckets are clipped to the period.
  - **Spending by merchant**, using the same inclusion rules as the totals.
  - **Comparison period:** this month so far is compared with the same days last month; a whole month with the previous month; the year to date with the same dates last year; a custom range with the same number of days just before it.
  - **% change** in whole numbers. It shows "no comparison" when the earlier figure is zero.
- **Reports API:**
  - `GET /api/reports/overview` returns totals, the comparison period and % changes, the trend series, spending and income by category, the top 10 merchants plus an "everything else" group, other currencies with activity, balances with reconciliation status, and the review count.
  - `GET /api/reports/export.csv?report=period|categories|merchants`: exact decimal amounts (computed from integer kobo, never floats), a header line naming the period, account and currency, a total row on the period table, formula-injection protection, and an audit event for every export.
- **Transactions:** a new `merchant=` filter, so you can open a merchant's transactions from a report. The Transactions page now also accepts `from`, `to`, `kind` and `status` in its link.
- **Home dashboard:**
  - Period chips (This month, Last month, Last 3 months, This year, Custom) and an account filter (shown when you have more than one account). Both are kept in the address bar, so a view can be bookmarked.
  - Four KPI tiles (income, spending, net cash flow, pending). Changes are shown with an arrow and words, never colour alone.
  - Trend chart with Spending / Income vs spending and Chart / Table toggles.
  - Top categories and top merchants. Each row links to the matching transactions.
  - Balances today with the estimated/reconciled note, recent transactions, a review alert, and an other-currency notice.
- **Reports page** (`/reports`): Auto/Daily/Weekly/Monthly grouping, income by category, a CSV button on each table, and a link to the printable summary.
- **Printable summary** (`/reports/print`): an A4 layout with the generation date, the comparison period, a by-period table with a total row, balances with their statement status, and notes on what counts, estimated balances and that this is not a bank statement. "Print or save as PDF" uses the browser; the app navigation is hidden when printing.
- **Charts** (Recharts 3.10.1, MIT licence):
  - One y-axis only, with a hover tooltip showing exact naira figures, a legend when two series are shown, and a table view.
  - Separate light and dark colours. Spending blue and income orange both passed the colour-blind safety, lightness and contrast checks against the app's actual light and dark surfaces.

### Acceptance criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Period selector, account filter, KPIs with change vs comparison period | Pass | `test_overview_totals_series_and_comparison`, `test_account_filter_and_isolation`, vitest `periods` tests, screenshots |
| 2 | Daily/weekly/monthly trends; one axis, tooltips, legend, table view, light and dark mode, validated palette | Pass | `test_overview_granularity_rules`, `test_week_start_preference_is_used`; palette validator output; screenshots at desktop and phone width, light and dark |
| 3 | Top categories and merchants, linked to matching transactions | Pass | `test_overview_categories_and_merchants_add_up`, `test_merchant_filter_drills_down` |
| 4 | Reports page with CSV exports (period, categories, merchants) and print | Pass | `test_csv_exports`, `test_csv_neutralises_formulas` |
| 5 | Printable summary with generation date and estimated/reconciled note | Pass | `/reports/print` rendered to a one-page A4 PDF in headless Chromium |
| 6 | Buckets, categories and merchants always add up; ledger engine at 100% branch coverage; user isolation | Pass | property tests `test_prop_series_buckets_add_up_to_period`, `test_prop_merchants_add_up_to_net_spending`, `test_prop_previous_period_ends_before_and_is_valid`; coverage 100%; isolation test; anonymous route sweep covers the new endpoints; 402 backend tests |

Live run through the web origin, after importing the sample statement: October series, categories and merchants each summed to exactly ₦126,056.94 net spending, and the CSV figures matched the screen.

### Upgrading your running copy

```
git pull
docker compose up --build -d
```
No database migration in this phase.

### Known limitations

- **Merchant names come from the transaction description.** For a bank transfer to a person (for example "NIP TRF TO KUDA/JOHN DOE"), the "merchant" shown is the receiving bank (KUDA). The fix needs better recognition of person-to-person transfers; this is planned with spending intelligence in Phase 8.
- Recurring bills, budgets and goals are not on the dashboard yet. They arrive in Phases 6–8 and won't be shown before their calculations exist.
- Figures are shown in one currency at a time (NGN by default). Activity in other currencies is flagged and never added in.
- The printable summary relies on the browser's own "Save as PDF". The server does not generate PDF files.
- Dark mode follows your device setting; there is no in-app toggle yet.

## Phase 6 — report (28 Oct 2026)

**Objective:** monthly budgets you can trust. You set each budget yourself; Wealthwise computes spent, pace and what is left from the same calculation code as the dashboard.

### What was built

- **Ledger engine, rules R19–R24** (`api/app/ledger/engine.py`, documented in RULES.md):
  - **Spent** per line is the category's net spending for the month. An overall line counts all net spending. Everything else is reported as unbudgeted.
  - **Available, remaining, % used** and **thresholds** for each line, plus an "over" flag.
  - **Carry-over:** unspent money moves to the same category next month. Overspending never does. It chains through consecutive months and is recalculated live.
  - **Projection** ("at your current pace", from day 7) and **safe per day**.
  - **Suggested budget:** the average of the last 3 complete months, rounded up to whole ₦1,000. It is offered only when there was spending in at least 2 of those months.
- **Database (migration 0005):** `budgets` (one per user, month and currency; carry-over switch; optional threshold override) and `budget_lines` (category or overall, planned amount). Both are tied to the owning user by composite keys. Spent, carry-over and projections are never stored.
- **Budgets API:**
  - `GET /api/budgets?month=`: live figures; `budget` is null when no budget has been set.
  - `GET /api/budgets/suggestions`
  - `POST /api/budgets`: start blank, copy the previous month, or use suggestions.
  - `PATCH /api/budgets/{id}`: carry-over and alert levels.
  - `PUT /api/budgets/{id}/lines`: replaces all lines in one save.
  - `DELETE /api/budgets/{id}`
  - Every change writes an audit event.
- **Categories:** a category in a budget can't be deleted (you're asked to remove it from the budget or archive it). Merging a category moves its budget lines; if the target already has a line, the two amounts are added together.
- **Your data:** budgets are included in the JSON export and deleted with your account.
- **Budgets page** (`/budgets`, new menu item):
  - Month arrows to move between months.
  - Create from suggestions (each suggestion shows the three monthly figures behind it), copy last month, or start blank.
  - Summary tiles, an optional overall limit, and one row per category. Each row has a status ("On track", "Reached 90%", "Over by ₦X", always with an icon), a progress bar with tick marks at each alert level, spent of available (with any carry-over shown), what's left, a safe daily amount and the pace estimate.
  - "Spending not in the budget" lists unbudgeted categories and uncategorised spending, each linked to its transactions.
  - Editor with "spent so far" next to each category and a running total.
  - Settings: carry-over, alert levels for this month, and delete (with an inline confirmation).
- **Home:** a budget card for the current month (shown when viewing This month for all accounts) with the overall limit and the lines that need attention, or a prompt to set a budget.

### Acceptance criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Monthly budget per category plus optional overall limit; blank/copy/suggested; edit and delete | Pass | `test_lines_spent_unbudgeted_and_status`, `test_copy_previous_and_suggestions`, `test_delete_budget_and_isolation`; UI flow driven in headless Chromium |
| 2 | Budgeted, carried over, available, spent (after refunds), remaining; unbudgeted shown separately | Pass | R19–R20 tests; API test checks budget totals equal the reports overview (₦87,000 both ways) |
| 3 | Thresholds from Settings, overridable per budget; status in words and icon; Home card | Pass | `test_thresholds_from_settings_and_override`, R21 tests, screenshots |
| 4 | Pace estimate from day 7 and safe per day, labelled as estimates | Pass | R23 tests, `test_projection_and_safe_per_day` |
| 5 | Suggestions from 3 complete months with their figures, applied only on request | Pass | R24 tests, `test_copy_previous_and_suggestions`; live: 5 suggestions matched hand calculation |
| 6 | Optional carry-over of unspent money only, chained and live | Pass | `test_rollover_chains_and_never_carries_overspending` (incl. editing an August transaction), R22 tests |
| 7 | Figures add up; engine 100% branch coverage; isolation | Pass | property tests `test_prop_budget_lines_plus_unbudgeted_equal_total`, `test_prop_line_status_invariants`; coverage 100%; isolation test; anonymous sweep covers new routes; 431 backend tests |

### Upgrading your running copy

```
git pull
docker compose up --build -d
```
The migrate step adds the two budget tables. Nothing else changes.

### Known limitations

- **Monthly budgets only.** Custom periods (e.g. salary date to salary date) are not supported yet.
- **The estimate is a simple straight-line pace.** A big one-off payment early in the month (rent, school fees) will make the estimate high for that category. It is labelled as an estimate for this reason.
- **No push alerts yet.** Threshold warnings show on the Budgets page and Home. Notifications arrive in Phase 9.
- **Naira only.** Budgets cover NGN spending.
