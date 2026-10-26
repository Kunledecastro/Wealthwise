# Ledger rules — the single source of truth for money

Every naira figure the app shows (dashboard, balances, reports, budgets, insights, AI answers)
is computed by `app/ledger/engine.py` using these rules. Nothing else sums money.
Each rule below has at least one test in `tests/test_ledger.py`.

## Representation
- Amounts are positive integers in minor units (kobo). Direction (`debit`/`credit`) carries the sign.
- Totals are only ever computed within one currency. Mixed currencies are grouped, never added.

## What counts
| # | Rule |
|---|---|
| R1 | Only **posted** transactions count toward income, spending and balances. |
| R2 | **Pending** transactions are reported separately (`pending_in`, `pending_out`) and in "available incl. pending". |
| R3 | **Failed** transactions never count anywhere. |
| R4 | **Deleted** transactions never count anywhere. |
| R5 | A **reversed** original and its **reversal** row both count nowhere (they cancel out). |
| R6 | **Income** = posted `income` credits. |
| R7 | **Gross spending** = posted `expense` + `fee` debits. Fees are also reported on their own. |
| R8 | **Refunds** (posted `refund` credits) reduce spending: `net spending = gross spending − refunds`. A refund is never income. A refund dated in a different period from the purchase reduces spending in the refund's period. |
| R9 | **Transfers** between own accounts are never income or spending, but move each account's balance. |
| R10 | **Adjustments** (manual corrections) are never income or spending, but move the balance. |
| R11 | **Net cash flow** = income − net spending. |
| R12 | Reporting periods use `transaction_date` (the date it happened, in the user's timezone), inclusive at both ends. |

## Balances
| # | Rule |
|---|---|
| B1 | Balance = opening balance + posted credits − posted debits, for transactions dated **on or after** the opening-balance date. Earlier transactions are assumed already included in the opening balance (they still appear in reports). |
| B2 | All posted kinds except reversal pairs move the balance: income, expense, fee, refund, transfer legs, adjustments. |
| B3 | Available incl. pending = balance + pending credits − pending debits (same date rule). |
| B4 | Manual accounts are always labelled **estimated** until reconciliation against a statement exists (Phase 3). |
