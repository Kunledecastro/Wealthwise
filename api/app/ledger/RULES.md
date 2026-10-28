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
| R13 | **Spending by category** uses exactly the same inclusion rules as R1–R12; uncategorised transactions form their own group, so the categories always add up to the totals. |
| R14 | A **refund** reduces spending in **its own** category (which is the purchase's category when the refund is linked to it). Categories are labels only: they never change whether something counts as income or spending. |
| R12 | Reporting periods use `transaction_date` (the date it happened, in the user's timezone), inclusive at both ends. |

## Trends and comparisons
| # | Rule |
|---|---|
| R15 | **Trend buckets** are days, weeks or calendar months. Weeks start on the user's chosen first day of the week. Every bucket in the period is listed, including empty ones, and the first and last buckets are clipped to the period (a partial week or month is labelled with its real dates). |
| R16 | Each bucket applies R1–R12 to its own dates. Every transaction falls into exactly one bucket, so **the buckets always add up to the period totals**. |
| R17 | **Spending by merchant** uses the same inclusion rules as R1–R12, covers spending and refunds only (income is not grouped by merchant), and puts transactions with no recognised merchant in their own group, so the merchants always add up to net spending. |
| R18 | **Comparison period.** A period that starts on 1 January and ends in the same year is compared with the same dates one year earlier. A period that starts on the 1st of a month is compared with the same days shifted back by the number of months it touches (this month so far → the same days last month; a whole month → the whole previous month). Any other period is compared with the same number of days immediately before. % change = (current − previous) ÷ \|previous\|, rounded to a whole number; it is shown as "no comparison" when the previous figure is zero. |

## Balances
| # | Rule |
|---|---|
| B1 | Balance = opening balance + posted credits − posted debits, for transactions dated **on or after** the opening-balance date. Earlier transactions are assumed already included in the opening balance (they still appear in reports). |
| B2 | All posted kinds except reversal pairs move the balance: income, expense, fee, refund, transfer legs, adjustments. |
| B3 | Available incl. pending = balance + pending credits − pending debits (same date rule). |
| B4 | An account with no statement balance on record is labelled **estimated**. |
| B5 | Reconciliation compares the latest recorded statement balance (from an imported statement's closing balance, or typed in by hand) with the balance computed **now** for that same date. Equal → **matches statement**; otherwise → **differs by ₦X**. Because it is recomputed every time, a later edit to an older transaction correctly breaks the match. Statement balances from an import that was undone are ignored. |
