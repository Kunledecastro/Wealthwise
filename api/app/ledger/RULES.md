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

## Budgets
| # | Rule |
|---|---|
| R19 | **Spent** on a budget line is the category's net spending for the calendar month (R13–R14: posted only, refunds deducted, transfers and adjustments excluded). An **overall** line uses total net spending (R8), including uncategorised spending. Spending in categories without a line, plus uncategorised spending, is reported as **unbudgeted**, so line spending + unbudgeted = total net spending. |
| R20 | **Available** = budgeted + carried over. **Remaining** = available − spent (negative = over budget). **% used** is rounded down. |
| R21 | **Thresholds** are whole percentages (1–200; default 70, 90, 100 from Settings, overridable per budget). A line has *reached* the highest threshold where spent × 100 ≥ threshold × available. It is **over** when spent > available. |
| R22 | **Carry-over** (when the budget has it switched on): a line receives the previous month's unspent amount for the same category (available − spent, never below zero). Overspending is never carried forward. It is recalculated live, so an edit to an old transaction updates it, and chains through consecutive months that have carry-over on. |
| R23 | **Projection** ("at your current pace") = spent + spent × (days after today ÷ days so far), rounded down. It is shown only from day 7 of the month; for a finished month it equals spent. **Safe per day** = remaining ÷ days left including today, rounded down, never negative. Both are estimates and labelled as such. |
| R24 | **Suggested budget** = average net spending over the last 3 complete months (months with nothing count as zero), rounded **up** to whole ₦1,000. It is offered only for categories with spending in at least 2 of those months, and never applied without the user's confirmation. |

## Balances
| # | Rule |
|---|---|
| B1 | Balance = opening balance + posted credits − posted debits, for transactions dated **on or after** the opening-balance date. Earlier transactions are assumed already included in the opening balance (they still appear in reports). |
| B2 | All posted kinds except reversal pairs move the balance: income, expense, fee, refund, transfer legs, adjustments. |
| B3 | Available incl. pending = balance + pending credits − pending debits (same date rule). |
| B4 | An account with no statement balance on record is labelled **estimated**. |
| B5 | Reconciliation compares the latest recorded statement balance (from an imported statement's closing balance, or typed in by hand) with the balance computed **now** for that same date. Equal → **matches statement**; otherwise → **differs by ₦X**. Because it is recomputed every time, a later edit to an older transaction correctly breaks the match. Statement balances from an import that was undone are ignored. |
