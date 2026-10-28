"""Budget calculations: load rows, then let app.ledger.engine do every sum (R19-R24)."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Budget, Category, Transaction, User
from app.finance.service import to_entry
from app.ledger.engine import (
    Entry,
    LineStatus,
    add_months,
    budget_line_status,
    carry_over,
    month_spending,
    month_start_end,
    normalise_thresholds,
    suggest_budget,
)

MAX_CHAIN = 24  # carry-over looks back at most two years
SUGGESTION_MONTHS = 3


def first_of_month(d: date) -> date:
    return d.replace(day=1)


def effective_thresholds(budget: Budget | None, user: User) -> tuple[int, ...]:
    raw = budget.alert_thresholds if budget and budget.alert_thresholds else None
    return normalise_thresholds(raw or user.preferences.budget_alert_thresholds or [70, 90, 100])


def load_entries(db: Session, user_id: int, start: date, end: date) -> list[Entry]:
    rows = db.scalars(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
            Transaction.transaction_date.between(start, end),
        )
    )
    return [to_entry(t) for t in rows]


def spending_by_month(
    db: Session, user_id: int, months: list[date], currency: str
) -> dict[date, tuple[int, dict[int | None, int]]]:
    """Net spending (total, per category) for each month, from one query."""
    if not months:
        return {}
    start = month_start_end(min(months))[0]
    end = month_start_end(max(months))[1]
    entries = load_entries(db, user_id, start, end)
    return {m: month_spending(entries, m, currency) for m in months}


def _line_spent(spent: tuple[int, dict[int | None, int]], category_id: int | None) -> int:
    total, per_cat = spent
    return total if category_id is None else per_cat.get(category_id, 0)


def rollover_for(db: Session, budget: Budget) -> dict[int | None, int]:
    """R22: carry-over into each line of `budget`, chained through consecutive months that
    have carry-over switched on. Recomputed from transactions every time."""
    if not budget.rollover_enabled:
        return {}
    chain: list[Budget] = []  # previous budgets, newest first
    current = budget
    while current.rollover_enabled and len(chain) < MAX_CHAIN:
        prev = db.scalar(
            select(Budget).where(
                Budget.user_id == budget.user_id,
                Budget.currency == budget.currency,
                Budget.month == add_months(current.month, -1),
            )
        )
        if prev is None:
            break
        chain.append(prev)
        current = prev
    if not chain:
        return {}
    chain.reverse()  # oldest first
    spent = spending_by_month(db, budget.user_id, [b.month for b in chain], budget.currency)
    carried: dict[int | None, int] = {}
    for i, b in enumerate(chain):
        incoming = carried if (i > 0 and b.rollover_enabled) else {}
        carried = {
            line.category_id: carry_over(
                line.planned_minor + incoming.get(line.category_id, 0),
                _line_spent(spent[b.month], line.category_id),
            )
            for line in b.lines
        }
    return carried


@dataclass(frozen=True)
class LineResult:
    category: Category | None
    line_public_id: str
    status: LineStatus


@dataclass(frozen=True)
class BudgetResult:
    lines: list[LineResult]  # category lines, in display order
    overall: LineResult | None
    total_spending: int
    budgeted_spending: int  # spending on categories that have a line
    unbudgeted: list[tuple[Category | None, int]]  # (category or uncategorised, net spending)
    thresholds: tuple[int, ...]


def evaluate(db: Session, budget: Budget, user: User, today: date) -> BudgetResult:
    thresholds = effective_thresholds(budget, user)
    spent = spending_by_month(db, user.id, [budget.month], budget.currency)[budget.month]
    total, per_cat = spent
    carry = rollover_for(db, budget)
    cats = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}

    def status(category_id: int | None, planned: int) -> LineStatus:
        return budget_line_status(
            planned_minor=planned,
            rollover_minor=carry.get(category_id, 0),
            spent_minor=_line_spent(spent, category_id),
            thresholds=thresholds,
            month=budget.month,
            today=today,
        )

    lines: list[LineResult] = []
    overall = None
    for line in budget.lines:
        r = LineResult(
            cats.get(line.category_id) if line.category_id else None,
            str(line.public_id),
            status(line.category_id, line.planned_minor),
        )
        if line.category_id is None:
            overall = r
        else:
            lines.append(r)
    lines.sort(
        key=lambda r: (
            r.category.sort_order if r.category else 0,
            str(r.category.name if r.category else ""),
        )
    )
    budgeted_ids = {line.category_id for line in budget.lines if line.category_id is not None}
    unbudgeted = [
        (cats.get(cid) if cid else None, amount)
        for cid, amount in per_cat.items()
        if cid not in budgeted_ids and amount != 0
    ]
    unbudgeted.sort(key=lambda x: -x[1])
    return BudgetResult(
        lines=lines,
        overall=overall,
        total_spending=total,
        budgeted_spending=sum(v for k, v in per_cat.items() if k in budgeted_ids),
        unbudgeted=unbudgeted,
        thresholds=thresholds,
    )


@dataclass(frozen=True)
class SuggestionResult:
    category: Category
    amount_minor: int
    months: list[tuple[date, int]]


def suggestion_months(month: date, today: date) -> list[date]:
    """The 3 complete months before `month` (never including the current month)."""
    anchor = min(first_of_month(month), first_of_month(today))
    return [add_months(anchor, -i) for i in range(SUGGESTION_MONTHS, 0, -1)]


def suggestions(
    db: Session, user_id: int, month: date, today: date, currency: str = "NGN"
) -> list[SuggestionResult]:
    months = suggestion_months(month, today)
    spent = spending_by_month(db, user_id, months, currency)
    cats = db.scalars(
        select(Category)
        .where(
            Category.user_id == user_id,
            Category.kind == "expense",
            Category.is_archived.is_(False),
        )
        .order_by(Category.sort_order, Category.name)
    ).all()
    out = []
    for c in cats:
        monthly = [spent[m][1].get(c.id, 0) for m in months]
        s = suggest_budget(monthly)
        if s is not None:
            out.append(SuggestionResult(c, s.amount_minor, list(zip(months, monthly, strict=True))))
    return out
