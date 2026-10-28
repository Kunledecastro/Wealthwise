import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.sessions import CurrentAuth, require_auth
from app.db.models import Account, Transaction
from app.db.session import get_db
from app.finance.schemas import CurrencySummaryOut, SummaryOut
from app.finance.service import (
    account_out,
    balances_for,
    get_account,
    to_entry,
    today_for,
    unprocessable,
)
from app.ledger.engine import summarize, total_balances

router = APIRouter(prefix="/api/ledger", tags=["ledger"])


def month_bounds(d: date) -> tuple[date, date]:
    start = d.replace(day=1)
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return start, date.fromordinal(nxt.toordinal() - 1)


@router.get("/summary", response_model=SummaryOut)
def summary(
    date_from: date | None = None,
    date_to: date | None = None,
    account_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> SummaryOut:
    """Totals for a period (default: the current calendar month in the user's timezone) and
    current balances. All figures come from app.ledger.engine."""
    today = today_for(auth.user)
    default_from, default_to = month_bounds(today)
    date_from = date_from or default_from
    date_to = date_to or default_to
    if date_to < date_from:
        raise unprocessable("The end date must be on or after the start date.")
    if (date_to - date_from).days > 3660:
        raise unprocessable("Please choose a period of 10 years or less.")

    stmt = select(Transaction).where(
        Transaction.user_id == auth.user.id,
        Transaction.deleted_at.is_(None),
        Transaction.transaction_date >= date_from,
        Transaction.transaction_date <= date_to,
    )
    acct_stmt = select(Account).where(
        Account.user_id == auth.user.id, Account.is_archived.is_(False)
    )
    if account_id is not None:
        acct = get_account(db, auth.user.id, account_id)
        stmt = stmt.where(Transaction.account_id == acct.id)
        acct_stmt = select(Account).where(Account.id == acct.id)

    entries = [to_entry(t) for t in db.scalars(stmt)]
    sums = summarize(entries, date_from, date_to)
    accounts = db.scalars(acct_stmt.order_by(Account.created_at)).all()
    bals = balances_for(db, auth.user.id, accounts)
    return SummaryOut(
        date_from=date_from,
        date_to=date_to,
        timezone=auth.user.preferences.timezone,
        summaries=[CurrencySummaryOut(**s.as_dict()) for s in sums.values()],
        accounts=[account_out(a, *bals[a.id], today) for a in accounts],
        balance_totals=total_balances(b for b, *_ in bals.values()),
        balances_are_estimated=not bals
        or any(r is None or not r.matches for _, _, r in bals.values()),
    )
