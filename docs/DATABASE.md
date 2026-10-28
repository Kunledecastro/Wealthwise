# Data model (Phase 0 proposal)

Status: tables from Phases 1–3 are **implemented** (Phase 3 added import_batches, import_rows, import_profiles, reconciliation_points and transactions.import_batch_id) (users, preferences, sessions, reset tokens, invites, auth_attempts, audit_events, currencies, accounts, transactions, transaction_revisions). The rest is the target shape for later phases.

## 1. Conventions

- **Money**: `BIGINT` minor units (`amount_minor`) + `currency CHAR(3)` (ISO 4217). Never `FLOAT`/`NUMERIC` for stored amounts. NGN: 1 naira = 100 kobo. Exponent is looked up from the `currencies` table, never hard-coded.
- **Sign convention**: `amount_minor` is always **positive**; direction is carried by `direction` (`debit` | `credit`). This avoids sign bugs in imports where banks disagree on conventions. A DB `CHECK (amount_minor > 0)` enforces it.
- **IDs**: internal `BIGINT` identity PK + public `UUID` (`public_id`, v7 for index locality) exposed in URLs/API. Internal ids never leave the API.
- **Time**: `TIMESTAMPTZ` stored in UTC. Business dates (`transaction_date`, `posting_date`) are `DATE` values in the user's timezone at the time of capture. Default timezone `Africa/Lagos`.
- **Ownership**: every user-data table has `user_id NOT NULL` with an index. Composite foreign keys `(user_id, id)` are used where a child must belong to the same user as its parent (e.g. a transaction's account and category).
- **Soft delete** only where history matters (accounts, categories); transactions are corrected via revisions, not edited silently.
- `created_at`, `updated_at` on every table.

## 2. Entity overview

```
users ─┬─ user_preferences (1:1)
       ├─ sessions, password_reset_tokens, auth_attempts
       ├─ consents                     (AI/external data, future open banking)
       ├─ accounts ─┬─ reconciliation_points
       │            └─ transactions ─┬─ transaction_revisions (audit trail)
       │                             ├─ links: transfer_group / reverses / refunds
       │                             └─ category ← categories ← category_rules
       ├─ import_batches ── import_rows ──► transactions
       ├─ budgets ── budget_lines (per category)
       ├─ goals ── goal_contributions
       ├─ recurring_series (detected or user-defined bills/subscriptions)
       ├─ insights, notifications
       └─ audit_events
currencies (reference table: code, exponent, symbol)
```

## 3. Core tables

### users / auth
| Table | Key columns |
|---|---|
| `users` | email (citext, unique), password_hash (Argon2id), email_verified_at, status, deleted_at |
| `user_preferences` | display_currency (default NGN), timezone (default Africa/Lagos), week_start, budget_alert_thresholds (int[] default {70,90,100}), ai_enabled (default false), external_ai_consent (default false) |
| `sessions` | token_hash (SHA-256 of random 256-bit token), user_id, created_at, last_seen_at, expires_at, ip, user_agent, revoked_at |
| `password_reset_tokens` | token_hash, user_id, expires_at (≤30 min), used_at |
| `auth_attempts` | email_hash, ip, success, created_at — used for rate limiting and lockout |

### accounts
| Column | Notes |
|---|---|
| `type` | bank, wallet, cash, savings, card, loan |
| `institution_name`, `display_name`, `mask` | last 4 digits only — never full account numbers |
| `currency` | per-account; multi-currency ready |
| `opening_balance_minor`, `opening_balance_date` | |
| `source` | **manual, imported, simulated, connected** — UI label is driven by this; `connected` is only settable by a real integration |
| `last_synced_at`, `balance_status` | `estimated` / `reconciled` / `stale` / `incomplete` |

`reconciliation_points`: (account, as_of_date, statement_balance_minor, computed_balance_minor, difference_minor). Lets the UI say "your computed balance differs from the statement by ₦X".

### transactions
| Column | Notes |
|---|---|
| `account_id` | |
| `kind` | `income`, `expense`, `transfer`, `fee`, `refund`, `reversal`, `adjustment` |
| `direction` | `debit` / `credit` |
| `amount_minor`, `currency` | |
| `status` | `pending`, `posted`, `failed`, `reversed` |
| `transaction_date`, `posting_date` | posting_date nullable until settled |
| `merchant_raw`, `merchant_normalised`, `narration` | |
| `category_id`, `category_source` (`rule`, `ai`, `user`, `none`), `category_confidence` (0–100), `category_reason` | |
| `needs_review` | true when uncertain or unmatched |
| `source` | `manual`, `csv`, `xlsx`, `pdf`, `simulated`, `email`, `open_banking` |
| `import_batch_id` | nullable |
| `external_ref` | bank reference where provided |
| `fingerprint` | SHA-256 dedupe key (see §4) |
| `transfer_group_id` | UUID shared by both legs of an own-account transfer |
| `reverses_transaction_id`, `refund_of_transaction_id` | self-references |
| `pending_of_transaction_id` | links a posted record to the pending authorisation it settles |
| `notes`, `is_demo` | `is_demo` keeps sample data strictly separated |

Constraints: `UNIQUE (account_id, external_ref) WHERE external_ref IS NOT NULL`; `UNIQUE (account_id, fingerprint)`; `CHECK (amount_minor > 0)`.

`transaction_revisions`: (transaction_id, changed_by, changed_at, field diffs as JSONB, reason). Every user edit writes one row in the same DB transaction.

### ingestion
- `import_batches`: user, account, adapter, original filename, file SHA-256, status (`uploaded → parsed → reviewed → committed | failed`), row counts (new / duplicate / error), error summary. Raw files are **not** retained after parsing by default (configurable).
- `import_rows`: batch, row number, raw (redacted JSON), normalised payload, outcome (`new`, `duplicate`, `possible_duplicate`, `error`), error message, resulting transaction id.

### categorisation
- `categories`: user_id (NULL = system default, copied per user on signup), name, kind (`expense`/`income`/`transfer`), parent_id, colour, is_archived.
- `category_rules`: user_id, match_field (merchant/narration), match_type (`equals`, `contains`, `regex` — regex length-limited), pattern, category_id, priority, created_from (`user_correction`, `manual`, `system`).

### budgets, goals, recurring, insights
- `budgets`: period_type (`monthly`, `custom`), start/end, rollover_enabled, thresholds override.
- `budget_lines`: budget, category (NULL = overall), planned_minor, rollover_in_minor.
- `goals`: type (emergency, purchase, travel, education, debt, long_term, custom), target_minor, deadline, priority, status. `goal_contributions`: amount_minor, date, optional linked transaction.
- `recurring_series`: merchant key, cadence (weekly/monthly/annual), typical_amount_minor, next_expected_date, confidence, confirmed_by_user.
- `insights`: type, period_start/end, facts JSONB (supporting figures + transaction ids), is_verified_fact vs is_pattern, recommended_action, estimated_impact_minor, status (new/dismissed/acted).
- `notifications`: type, payload, read_at.

### audit
`audit_events`: user_id, actor, action (e.g. `auth.login`, `transaction.update`, `account.delete`, `data.export`), target type/id, ip, created_at, metadata (redacted). Append-only; the app role has no UPDATE/DELETE on it.

## 4. Deduplication

*Implemented in Phase 3 with one change (D-031): a bank reference is only used when it is unique within the file.*

1. If `external_ref` present (and unique in the file) → exact match in the account = duplicate.
2. Fingerprint = SHA-256 of `account_id | transaction_date | direction | amount_minor | normalised narration | occurrence_index`.
   `occurrence_index` = position among identical rows **within the same source file**, so two genuine identical ₦500 POS charges on one day are both kept, while re-importing that file still dedupes.
3. Near-matches (same amount/direction ±2 days, similar narration, different source) are flagged `possible_duplicate` for user review — never auto-merged.

## 5. Financial calculation rules (summary — the authoritative, tested version is [`api/app/ledger/RULES.md`](../api/app/ledger/RULES.md))

| Situation | Income/expense totals | Balance |
|---|---|---|
| `posted` income / expense / fee | counted | counted |
| `pending` | excluded from totals; shown separately as "pending" | shown as "available (incl. pending)" only |
| `failed` | excluded | excluded |
| Reversal pair (original + reversal) | both excluded | net zero |
| Own-account transfer (both legs) | excluded | each leg moves its account |
| Refund linked to an expense | **reduces that category's expense**, not income | counted |
| Unlinked credit marked refund | reduces expense in the chosen category; never income by default | counted |
| Pending later settled | pending row closed and linked; only the posted row counts | — |
| Reporting date | `transaction_date` in the user's timezone (posting date shown as detail) | — |

Balance = opening balance + Σ posted credits − Σ posted debits since `opening_balance_date`, flagged `estimated` until reconciled against a statement balance.

## 6. Migrations

Alembic, one migration per phase minimum, reviewed by hand (no blind autogenerate). CI check: `alembic upgrade head` → `alembic downgrade -1` → `upgrade head` on an empty database.
