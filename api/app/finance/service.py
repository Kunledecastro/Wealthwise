"""Finance domain logic: ownership-checked loading, ledger adapters, revisions.

Every query here takes `user_id` and filters on it. There is no way to fetch an
account or transaction without naming its owner (docs/SECURITY.md, authorisation).
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Account, Transaction, TransactionRevision, User
from app.finance.schemas import AccountOut, BalanceOut, TransactionOut
from app.ledger.engine import Balance, Entry, account_balance


def not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found.")


def unprocessable(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, msg)


def today_for(user: User) -> date:
    return datetime.now(ZoneInfo(user.preferences.timezone)).date()


def blank_to_none(v: str | None) -> str | None:
    return v.strip() or None if isinstance(v, str) else v


# ---------------- ownership-checked loaders ----------------


def get_account(db: Session, user_id: int, public_id: uuid.UUID, *, lock: bool = False) -> Account:
    stmt = select(Account).where(Account.user_id == user_id, Account.public_id == public_id)
    if lock:
        stmt = stmt.with_for_update()
    acct = db.scalar(stmt)
    if acct is None:
        raise not_found("Account")
    return acct


def get_txn(
    db: Session,
    user_id: int,
    public_id: uuid.UUID,
    *,
    include_deleted: bool = False,
    lock: bool = True,
) -> Transaction:
    stmt = select(Transaction).where(
        Transaction.user_id == user_id, Transaction.public_id == public_id
    )
    if not include_deleted:
        stmt = stmt.where(Transaction.deleted_at.is_(None))
    txn = db.scalar(stmt.with_for_update() if lock else stmt)
    if txn is None:
        raise not_found("Transaction")
    return txn


def transfer_legs(db: Session, user_id: int, group: uuid.UUID) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.transfer_group_id == group,
                Transaction.deleted_at.is_(None),
            )
            .order_by(Transaction.id)
            .with_for_update()
        )
    )


# ---------------- ledger adapters ----------------


def to_entry(t: Transaction) -> Entry:
    return Entry(
        kind=t.kind,
        direction=t.direction,
        amount_minor=t.amount_minor,
        currency=t.currency,
        status=t.status,
        transaction_date=t.transaction_date,
        account_id=t.account_id,
        deleted=t.deleted_at is not None,
    )


def balances_for(
    db: Session, user_id: int, accounts: Sequence[Account], as_of: date | None = None
) -> dict[int, tuple[Balance, int]]:
    """Balance and live transaction count per account, computed by the ledger engine."""
    ids = [a.id for a in accounts]
    by_acct: dict[int, list[Entry]] = {i: [] for i in ids}
    if ids:
        rows = db.scalars(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.account_id.in_(ids),
                Transaction.deleted_at.is_(None),
            )
        )
        for t in rows:
            by_acct[t.account_id].append(to_entry(t))
    return {
        a.id: (
            account_balance(
                currency=a.currency,
                opening_minor=a.opening_balance_minor,
                opening_date=a.opening_balance_date,
                entries=by_acct[a.id],
                as_of=as_of,
            ),
            len(by_acct[a.id]),
        )
        for a in accounts
    }


def account_out(a: Account, bal: Balance, count: int, as_of: date) -> AccountOut:
    return AccountOut(
        id=a.public_id,
        type=a.type,
        display_name=a.display_name,
        institution_name=a.institution_name,
        mask=a.mask,
        currency=a.currency,
        opening_balance_minor=a.opening_balance_minor,
        opening_balance_date=a.opening_balance_date,
        source=a.source,
        is_archived=a.is_archived,
        created_at=a.created_at,
        transaction_count=count,
        balance=BalanceOut(
            posted_minor=bal.posted_minor,
            pending_in=bal.pending_in,
            pending_out=bal.pending_out,
            available_incl_pending=bal.available_incl_pending,
            # B4: manual accounts are estimates until statement reconciliation exists.
            status="estimated",
            as_of=as_of,
        ),
    )


# ---------------- output ----------------


def txn_outs(db: Session, user_id: int, txns: Sequence[Transaction]) -> list[TransactionOut]:
    """Serialise transactions, resolving internal ids to public ids in a few queries."""
    if not txns:
        return []
    acct_ids = {t.account_id for t in txns}
    link_ids = {
        i for t in txns for i in (t.reverses_transaction_id, t.refund_of_transaction_id) if i
    }
    groups = {t.transfer_group_id for t in txns if t.transfer_group_id}
    ids = {t.id for t in txns}

    counterpart: dict[int, Transaction] = {}
    if groups:
        legs = db.scalars(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.transfer_group_id.in_(groups),
                Transaction.deleted_at.is_(None),
            )
        ).all()
        for t in txns:
            if t.transfer_group_id:
                other = next(
                    (
                        x
                        for x in legs
                        if x.transfer_group_id == t.transfer_group_id and x.id != t.id
                    ),
                    None,
                )
                if other:
                    counterpart[t.id] = other
                    acct_ids.add(other.account_id)

    reversed_by: dict[int, uuid.UUID] = {}
    for rid, pid in db.execute(
        select(Transaction.reverses_transaction_id, Transaction.public_id).where(
            Transaction.user_id == user_id,
            Transaction.reverses_transaction_id.in_(ids),
            Transaction.deleted_at.is_(None),
        )
    ):
        if rid is not None:
            reversed_by[rid] = pid

    accts = {
        a.id: a
        for a in db.scalars(
            select(Account).where(Account.user_id == user_id, Account.id.in_(acct_ids))
        )
    }
    links: dict[int, uuid.UUID] = {}
    if link_ids:
        links = {
            k: v
            for k, v in db.execute(
                select(Transaction.id, Transaction.public_id).where(
                    Transaction.user_id == user_id, Transaction.id.in_(link_ids)
                )
            )
        }

    out = []
    for t in txns:
        a = accts[t.account_id]
        cp = counterpart.get(t.id)
        cpa = accts.get(cp.account_id) if cp else None
        out.append(
            TransactionOut(
                id=t.public_id,
                account_id=a.public_id,
                account_name=a.display_name,
                kind=t.kind,
                direction=t.direction,
                amount_minor=t.amount_minor,
                currency=t.currency,
                status=t.status,
                transaction_date=t.transaction_date,
                posting_date=t.posting_date,
                merchant=t.merchant,
                narration=t.narration,
                notes=t.notes,
                source=t.source,
                transfer_group_id=t.transfer_group_id,
                counterpart_account_id=cpa.public_id if cpa else None,
                counterpart_account_name=cpa.display_name if cpa else None,
                reverses_id=links.get(t.reverses_transaction_id or 0),
                reversed_by_id=reversed_by.get(t.id),
                refund_of_id=links.get(t.refund_of_transaction_id or 0),
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
        )
    return out


# ---------------- revisions ----------------

TRACKED = (
    "account_id",
    "kind",
    "direction",
    "amount_minor",
    "status",
    "transaction_date",
    "posting_date",
    "merchant",
    "narration",
    "notes",
)


def _jsonable(v: Any) -> Any:
    if isinstance(v, date | datetime):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def snapshot(t: Transaction, account_public_ids: dict[int, uuid.UUID]) -> dict[str, Any]:
    snap = {k: getattr(t, k) for k in TRACKED}
    snap["account_id"] = account_public_ids.get(t.account_id, t.account_id)
    return {k: _jsonable(v) for k, v in snap.items()}


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    return {k: [before.get(k), after[k]] for k in after if before.get(k) != after[k]}


def add_revision(
    db: Session,
    t: Transaction,
    action: str,
    changes: dict[str, Any],
    reason: str | None = None,
) -> None:
    db.add(
        TransactionRevision(
            transaction_id=t.id,
            user_id=t.user_id,
            action=action,
            changes=changes,
            reason=reason,
        )
    )


def count_live_txns(db: Session, user_id: int, account_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.account_id == account_id,
                Transaction.deleted_at.is_(None),
            )
        )
        or 0
    )
