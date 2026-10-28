"""Dashboard and reports (Phase 5). Every figure comes from app.ledger.engine (R1-R18).

Read-only: these endpoints never change data. Everything is scoped to the signed-in user.
"""

import csv
import io
import uuid
from collections.abc import Sequence
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import record as audit
from app.auth.sessions import CurrentAuth, client_ip, require_auth
from app.db.models import Account, Category, Transaction
from app.db.session import get_db
from app.finance.schemas import AccountOut, CurrencySummaryOut
from app.finance.service import (
    account_out,
    balances_for,
    get_account,
    to_entry,
    today_for,
    unprocessable,
)
from app.finance.summary import month_bounds
from app.finance.transactions import _csv_safe
from app.ledger.engine import (
    Entry,
    Summary,
    by_category,
    by_merchant,
    percent_change,
    previous_period,
    summarize,
    time_series,
    total_balances,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])

Granularity = Literal["auto", "day", "week", "month"]
MAX_DAYS = 3660  # 10 years
MAX_DAY_BUCKETS = 400
MAX_WEEK_BUCKETS = 530
TOP_MERCHANTS = 10


# ---------------------------------------------------------------- schemas


class SeriesPointOut(BaseModel):
    date_from: date
    date_to: date
    income: int
    gross_spending: int
    refunds: int
    net_spending: int
    net_cash_flow: int
    pending_out: int
    transaction_count: int


class PeriodOut(BaseModel):
    date_from: date
    date_to: date
    summary: CurrencySummaryOut


class ChangesOut(BaseModel):
    """Whole-number % change vs the comparison period (R18); null = nothing to compare."""

    income: int | None
    net_spending: int | None
    net_cash_flow: int | None
    transaction_count: int | None


class CategoryRowOut(BaseModel):
    category_id: uuid.UUID | None
    name: str
    color: str
    net_spending: int
    income: int
    transaction_count: int


class MerchantRowOut(BaseModel):
    merchant: str | None  # None = no merchant recognised
    net_spending: int
    transaction_count: int


class OverviewOut(BaseModel):
    date_from: date
    date_to: date
    timezone: str
    currency: str
    granularity: Literal["day", "week", "month"]
    week_start: int
    summary: CurrencySummaryOut
    previous: PeriodOut
    changes: ChangesOut
    series: list[SeriesPointOut]
    spending_by_category: list[CategoryRowOut]
    income_by_category: list[CategoryRowOut]
    top_merchants: list[MerchantRowOut]
    other_merchants: MerchantRowOut | None  # everything outside the top list, combined
    other_currencies: list[str]  # currencies with activity in the period, not included above
    accounts: list[AccountOut]
    balance_totals: dict[str, int]
    balances_are_estimated: bool
    needs_review_count: int
    generated_on: date


# ---------------------------------------------------------------- helpers


def _summary_out(s: Summary) -> CurrencySummaryOut:
    return CurrencySummaryOut(**s.as_dict())


def resolve_period(
    auth: CurrentAuth, date_from: date | None, date_to: date | None
) -> tuple[date, date]:
    d0, d1 = month_bounds(today_for(auth.user))
    date_from, date_to = date_from or d0, date_to or d1
    if date_to < date_from:
        raise unprocessable("The end date must be on or after the start date.")
    if (date_to - date_from).days > MAX_DAYS:
        raise unprocessable("Please choose a period of 10 years or less.")
    return date_from, date_to


def resolve_granularity(g: Granularity, date_from: date, date_to: date) -> str:
    days = (date_to - date_from).days + 1
    if g == "auto":
        return "day" if days <= 62 else "week" if days <= 183 else "month"
    if g == "day" and days > MAX_DAY_BUCKETS:
        raise unprocessable("Daily figures are available for periods up to 400 days.")
    if g == "week" and days > MAX_WEEK_BUCKETS * 7:
        raise unprocessable("Weekly figures are available for periods up to 10 years.")
    return g


def load_entries(
    db: Session,
    user_id: int,
    date_from: date,
    date_to: date,
    account_pk: int | None,
) -> list[Entry]:
    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.deleted_at.is_(None),
        Transaction.transaction_date.between(date_from, date_to),
    )
    if account_pk is not None:
        stmt = stmt.where(Transaction.account_id == account_pk)
    return [to_entry(t) for t in db.scalars(stmt)]


def _category_rows(
    entries: Sequence[Entry], currency: str, cats: dict[int, Category]
) -> tuple[list[CategoryRowOut], list[CategoryRowOut]]:
    spend, income = [], []
    for (cur, cid), t in by_category(entries).items():
        if cur != currency:
            continue
        c = cats.get(cid) if cid else None
        row = CategoryRowOut(
            category_id=c.public_id if c else None,
            name=c.name if c else "Uncategorised",
            color=c.color if c else "#94a3b8",
            net_spending=t.net_spending,
            income=t.income,
            transaction_count=t.transaction_count,
        )
        if t.gross_spending or t.refunds:
            spend.append(row)
        if t.income:
            income.append(row)
    spend.sort(key=lambda r: (-r.net_spending, r.name))
    income.sort(key=lambda r: (-r.income, r.name))
    return spend, income


def _merchant_rows(
    entries: Sequence[Entry], currency: str
) -> tuple[list[MerchantRowOut], MerchantRowOut | None]:
    rows = [
        MerchantRowOut(
            merchant=t.merchant, net_spending=t.net_spending, transaction_count=t.transaction_count
        )
        for (cur, _), t in by_merchant(entries).items()
        if cur == currency
    ]
    # Unrecognised spending is always reported, but never ranked as a "merchant".
    named = sorted(
        (r for r in rows if r.merchant), key=lambda r: (-r.net_spending, r.merchant or "")
    )
    unnamed = [r for r in rows if not r.merchant]
    top, rest = named[:TOP_MERCHANTS], named[TOP_MERCHANTS:] + unnamed
    other = None
    if rest:
        other = MerchantRowOut(
            merchant=None,
            net_spending=sum(r.net_spending for r in rest),
            transaction_count=sum(r.transaction_count for r in rest),
        )
    return top, other


# ---------------------------------------------------------------- endpoints


@router.get("/overview", response_model=OverviewOut)
def overview(
    date_from: date | None = None,
    date_to: date | None = None,
    account_id: uuid.UUID | None = None,
    granularity: Granularity = "auto",
    currency: Annotated[str, Query(min_length=3, max_length=3)] = "NGN",
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> OverviewOut:
    """Everything the dashboard shows for one period, in one currency."""
    currency = currency.upper()
    date_from, date_to = resolve_period(auth, date_from, date_to)
    gran = resolve_granularity(granularity, date_from, date_to)
    week_start = auth.user.preferences.week_start
    uid = auth.user.id

    acct = get_account(db, uid, account_id) if account_id is not None else None
    entries = load_entries(db, uid, date_from, date_to, acct.id if acct else None)
    p0, p1 = previous_period(date_from, date_to)
    prev_entries = load_entries(db, uid, p0, p1, acct.id if acct else None)

    sums = summarize(entries, date_from, date_to)
    cur = sums.get(currency) or Summary(currency=currency)
    prev = summarize(prev_entries, p0, p1).get(currency) or Summary(currency=currency)
    series = time_series(entries, date_from, date_to, gran, week_start, currency)

    cats = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == uid))}
    spend_rows, income_rows = _category_rows(entries, currency, cats)
    top, other = _merchant_rows(entries, currency)

    if acct is not None:
        accounts: Sequence[Account] = [acct]
    else:
        accounts = db.scalars(
            select(Account)
            .where(Account.user_id == uid, Account.is_archived.is_(False))
            .order_by(Account.created_at)
        ).all()
    today = today_for(auth.user)
    bals = balances_for(db, uid, accounts)
    review = (
        db.scalar(
            select(func.count()).where(
                Transaction.user_id == uid,
                Transaction.deleted_at.is_(None),
                Transaction.needs_review.is_(True),
            )
        )
        or 0
    )
    return OverviewOut(
        date_from=date_from,
        date_to=date_to,
        timezone=auth.user.preferences.timezone,
        currency=currency,
        granularity=gran,
        week_start=week_start,
        summary=_summary_out(cur),
        previous=PeriodOut(date_from=p0, date_to=p1, summary=_summary_out(prev)),
        changes=ChangesOut(
            income=percent_change(cur.income, prev.income),
            net_spending=percent_change(cur.net_spending, prev.net_spending),
            net_cash_flow=percent_change(cur.net_cash_flow, prev.net_cash_flow),
            transaction_count=percent_change(cur.transaction_count, prev.transaction_count),
        ),
        series=[
            SeriesPointOut(
                date_from=p.date_from,
                date_to=p.date_to,
                income=p.summary.income,
                gross_spending=p.summary.gross_spending,
                refunds=p.summary.refunds,
                net_spending=p.summary.net_spending,
                net_cash_flow=p.summary.net_cash_flow,
                pending_out=p.summary.pending_out,
                transaction_count=p.summary.transaction_count,
            )
            for p in series
        ],
        spending_by_category=spend_rows,
        income_by_category=income_rows,
        top_merchants=top,
        other_merchants=other,
        other_currencies=sorted(c for c in sums if c != currency),
        accounts=[account_out(a, *bals[a.id], today) for a in accounts],
        balance_totals=total_balances(b for b, *_ in bals.values()),
        balances_are_estimated=not bals
        or any(r is None or not r.matches for _, _, r in bals.values()),
        needs_review_count=review,
        generated_on=today,
    )


def _naira(minor: int) -> str:
    """Exact decimal string from integer minor units (never a float)."""
    sign = "-" if minor < 0 else ""
    major, rest = divmod(abs(minor), 100)
    return f"{sign}{major}.{rest:02d}"


ReportKind = Literal["period", "categories", "merchants"]


@router.get("/export.csv")
def export_report_csv(
    request: Request,
    report: ReportKind = "period",
    date_from: date | None = None,
    date_to: date | None = None,
    account_id: uuid.UUID | None = None,
    granularity: Granularity = "auto",
    currency: Annotated[str, Query(min_length=3, max_length=3)] = "NGN",
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> StreamingResponse:
    """CSV of a report table. Amounts are exact decimals in the stated currency."""
    currency = currency.upper()
    date_from, date_to = resolve_period(auth, date_from, date_to)
    gran = resolve_granularity(granularity, date_from, date_to)
    uid = auth.user.id
    acct = get_account(db, uid, account_id) if account_id is not None else None
    entries = load_entries(db, uid, date_from, date_to, acct.id if acct else None)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            f"Wealthwise {report} report",
            f"{date_from.isoformat()} to {date_to.isoformat()}",
            f"account: {_csv_safe(acct.display_name) if acct else 'all accounts'}",
            f"currency: {currency}",
        ]
    )
    rows = 0
    if report == "period":
        w.writerow(
            [
                "from",
                "to",
                "income",
                "gross_spending",
                "refunds",
                "net_spending",
                "net_cash_flow",
                "pending_out",
                "transactions",
            ]
        )
        pts = time_series(
            entries, date_from, date_to, gran, auth.user.preferences.week_start, currency
        )
        for p in pts:
            s = p.summary
            w.writerow(
                [
                    p.date_from,
                    p.date_to,
                    _naira(s.income),
                    _naira(s.gross_spending),
                    _naira(s.refunds),
                    _naira(s.net_spending),
                    _naira(s.net_cash_flow),
                    _naira(s.pending_out),
                    s.transaction_count,
                ]
            )
        rows = len(pts)
        total = summarize(entries, date_from, date_to).get(currency) or Summary(currency)
        w.writerow(
            [
                "total",
                "",
                _naira(total.income),
                _naira(total.gross_spending),
                _naira(total.refunds),
                _naira(total.net_spending),
                _naira(total.net_cash_flow),
                _naira(total.pending_out),
                total.transaction_count,
            ]
        )
    elif report == "categories":
        cats = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == uid))}
        spend, income = _category_rows(entries, currency, cats)
        w.writerow(["type", "category", "amount", "transactions"])
        for r in spend:
            w.writerow(["spending", _csv_safe(r.name), _naira(r.net_spending), r.transaction_count])
        for r in income:
            w.writerow(["income", _csv_safe(r.name), _naira(r.income), r.transaction_count])
        rows = len(spend) + len(income)
    else:
        all_rows = [
            (t.merchant, t.net_spending, t.transaction_count)
            for (cur, _), t in by_merchant(entries).items()
            if cur == currency
        ]
        all_rows.sort(key=lambda r: (r[0] is None, -r[1], r[0] or ""))
        w.writerow(["merchant", "net_spending", "transactions"])
        for m, amount, n in all_rows:
            w.writerow([_csv_safe(m) if m else "(no merchant recognised)", _naira(amount), n])
        rows = len(all_rows)

    audit(
        db,
        "data.export_report_csv",
        user_id=uid,
        ip=client_ip(request),
        details={"report": report, "rows": rows},
    )
    db.commit()
    name = f"wealthwise-{report}-{date_from.isoformat()}-to-{date_to.isoformat()}.csv"
    return StreamingResponse(
        iter(["﻿" + buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
