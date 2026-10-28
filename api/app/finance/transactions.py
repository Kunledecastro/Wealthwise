import csv
import io
import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.audit.service import record as audit
from app.auth.sessions import CurrentAuth, client_ip, require_auth
from app.categorise import service as cats
from app.db.models import Account, Category, Transaction, TransactionRevision, utcnow
from app.db.session import get_db
from app.finance.schemas import (
    DeleteIn,
    ReverseIn,
    RevisionOut,
    TransactionDetailOut,
    TransactionIn,
    TransactionOut,
    TransactionPage,
    TransactionPatch,
    TransferIn,
    TransferOut,
)
from app.finance.service import (
    add_revision,
    blank_to_none,
    diff,
    get_account,
    get_txn,
    snapshot,
    today_for,
    transfer_legs,
    txn_outs,
    unprocessable,
)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

FIXED_DIRECTION = {"income": "credit", "refund": "credit", "expense": "debit", "fee": "debit"}
REVERSIBLE = {"income", "expense", "fee", "refund", "adjustment"}
MAX_FUTURE_DAYS = 366


def _check_dates(auth: CurrentAuth, txn_date: date) -> None:
    if txn_date > today_for(auth.user) + timedelta(days=MAX_FUTURE_DAYS):
        raise unprocessable("Transaction date is too far in the future.")


def _usable_account(db: Session, auth: CurrentAuth, public_id: uuid.UUID) -> Account:
    a = get_account(db, auth.user.id, public_id)
    if a.is_archived:
        raise unprocessable("This account is archived. Unarchive it to add transactions.")
    return a


def _settle_posting_date(t: Transaction) -> None:
    """A posted transaction always has a posting date (default: its transaction date)."""
    if t.status == "posted" and t.posting_date is None:
        t.posting_date = t.transaction_date


def _pub_ids(db: Session, user_id: int, ids: set[int]) -> dict[int, uuid.UUID]:
    if not ids:
        return {}
    return {
        k: v
        for k, v in db.execute(
            select(Account.id, Account.public_id).where(
                Account.user_id == user_id, Account.id.in_(ids)
            )
        )
    }


def _one_out(db: Session, auth: CurrentAuth, t: Transaction) -> TransactionOut:
    return txn_outs(db, auth.user.id, [t])[0]


# ---------------- list / search ----------------


def _filtered(
    auth: CurrentAuth,
    db: Session,
    account_id: uuid.UUID | None,
    kind: Sequence[str] | None,
    status_: Sequence[str] | None,
    date_from: date | None,
    date_to: date | None,
    q: str | None,
    min_amount: int | None,
    max_amount: int | None,
    category: str | None = None,
    needs_review: bool | None = None,
) -> Select[Transaction]:
    stmt = select(Transaction).where(
        Transaction.user_id == auth.user.id, Transaction.deleted_at.is_(None)
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == get_account(db, auth.user.id, account_id).id)
    if kind:
        stmt = stmt.where(Transaction.kind.in_(kind))
    if status_:
        stmt = stmt.where(Transaction.status.in_(status_))
    if date_from:
        stmt = stmt.where(Transaction.transaction_date >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.transaction_date <= date_to)
    if min_amount is not None:
        stmt = stmt.where(Transaction.amount_minor >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Transaction.amount_minor <= max_amount)
    if category == "none":
        stmt = stmt.where(Transaction.category_id.is_(None))
    elif category:
        try:
            cat_uuid = uuid.UUID(category)
        except ValueError as exc:
            raise unprocessable("Unknown category.") from exc
        stmt = stmt.where(
            Transaction.category_id == cats.get_category(db, auth.user.id, cat_uuid).id
        )
    if needs_review is not None:
        stmt = stmt.where(Transaction.needs_review.is_(needs_review))
    if q:
        term = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(
            or_(
                Transaction.merchant.ilike(term, escape="\\"),
                Transaction.narration.ilike(term, escape="\\"),
                Transaction.notes.ilike(term, escape="\\"),
            )
        )
    return stmt


KindQ = Annotated[
    list[Literal["income", "expense", "fee", "refund", "transfer", "reversal", "adjustment"]]
    | None,
    Query(),
]
StatusQ = Annotated[
    list[Literal["pending", "posted", "failed", "reversed"]] | None, Query(alias="status")
]


@router.get("", response_model=TransactionPage)
def list_transactions(
    account_id: uuid.UUID | None = None,
    kind: KindQ = None,
    status_: StatusQ = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    min_amount: Annotated[int | None, Query(ge=0)] = None,
    max_amount: Annotated[int | None, Query(ge=0)] = None,
    category: Annotated[str | None, Query(max_length=40)] = None,
    needs_review: bool | None = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> TransactionPage:
    stmt = _filtered(
        auth,
        db,
        account_id,
        kind,
        status_,
        date_from,
        date_to,
        q,
        min_amount,
        max_amount,
        category,
        needs_review,
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return TransactionPage(
        items=txn_outs(db, auth.user.id, rows), total=total, page=page, page_size=page_size
    )


CSV_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(v: object) -> str:
    """Neutralise spreadsheet formula injection in user-entered text."""
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(CSV_DANGEROUS) else s


@router.get("/export.csv")
def export_csv(
    request: Request,
    account_id: uuid.UUID | None = None,
    kind: KindQ = None,
    status_: StatusQ = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category: Annotated[str | None, Query(max_length=40)] = None,
    needs_review: bool | None = None,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> StreamingResponse:
    stmt = _filtered(
        auth,
        db,
        account_id,
        kind,
        status_,
        date_from,
        date_to,
        q,
        None,
        None,
        category,
        needs_review,
    )
    rows = db.scalars(stmt.order_by(Transaction.transaction_date, Transaction.id)).all()
    outs = txn_outs(db, auth.user.id, rows)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "date",
            "posting_date",
            "account",
            "type",
            "direction",
            "amount",
            "amount_minor",
            "currency",
            "status",
            "merchant",
            "category",
            "description",
            "notes",
            "transfer_counterpart",
        ]
    )
    for t in outs:
        major, minor = divmod(t.amount_minor, 100)
        signed = ("-" if t.direction == "debit" else "") + f"{major}.{minor:02d}"
        w.writerow(
            [
                t.id,
                t.transaction_date,
                t.posting_date or "",
                _csv_safe(t.account_name),
                t.kind,
                t.direction,
                signed,
                t.amount_minor,
                t.currency,
                t.status,
                _csv_safe(t.merchant),
                _csv_safe(t.category_name),
                _csv_safe(t.narration),
                _csv_safe(t.notes),
                _csv_safe(t.counterpart_account_name),
            ]
        )
    audit(
        db,
        "data.export_csv",
        user_id=auth.user.id,
        ip=client_ip(request),
        details={"rows": len(outs)},
    )
    db.commit()
    stamp = today_for(auth.user).isoformat()
    return StreamingResponse(
        iter(["﻿" + buf.getvalue()]),  # BOM so Excel reads ₦ and UTF-8 correctly
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="wealthwise-transactions-{stamp}.csv"'
        },
    )


# ---------------- create ----------------


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    body: TransactionIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> TransactionOut:
    _check_dates(auth, body.transaction_date)
    acct = _usable_account(db, auth, body.account_id)
    refund_of_id = None
    orig: Transaction | None = None
    if body.refund_of_id is not None:
        orig = get_txn(db, auth.user.id, body.refund_of_id)
        if orig.kind not in ("expense", "fee"):
            raise unprocessable("A refund can only be linked to an expense or fee.")
        if orig.currency != acct.currency:
            raise unprocessable("The refund must be in the same currency as the purchase.")
        refund_of_id = orig.id
    direction = FIXED_DIRECTION.get(body.kind) or body.direction
    if direction is None:  # schema validation already guarantees this; belt and braces
        raise unprocessable("Choose whether the adjustment adds or removes money.")
    t = Transaction(
        user_id=auth.user.id,
        account_id=acct.id,
        kind=body.kind,
        direction=direction,
        amount_minor=body.amount_minor,
        currency=acct.currency,
        status=body.status,
        transaction_date=body.transaction_date,
        posting_date=body.posting_date,
        merchant=blank_to_none(body.merchant),
        narration=blank_to_none(body.narration),
        notes=blank_to_none(body.notes),
        source="manual",
        refund_of_transaction_id=refund_of_id,
    )
    _settle_posting_date(t)
    ctx = cats.load_context(db, auth.user.id)
    chosen = cats.choose(db, auth.user.id, body.category_id, t.kind) if body.category_id else None
    cats.apply(
        ctx,
        t,
        user_category_id=chosen.id if chosen else None,
        linked_category_id=orig.category_id if orig is not None else None,
    )
    cats.flush_hits(db, ctx)
    db.add(t)
    db.flush()
    add_revision(db, t, "create", snapshot(t, {acct.id: acct.public_id}))
    audit(
        db,
        "transaction.created",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="transaction",
        target_id=str(t.public_id),
        details={"kind": t.kind},
    )
    db.commit()
    db.refresh(t)
    return _one_out(db, auth, t)


@router.post("/transfers", response_model=TransferOut, status_code=status.HTTP_201_CREATED)
def create_transfer(
    body: TransferIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> TransferOut:
    """Both legs are written in one DB transaction: either both exist or neither does."""
    _check_dates(auth, body.transaction_date)
    src = _usable_account(db, auth, body.from_account_id)
    dst = _usable_account(db, auth, body.to_account_id)
    if src.currency != dst.currency:
        raise unprocessable("Transfers between different currencies are not supported yet.")
    group = uuid.uuid4()
    legs = []
    ctx = cats.load_context(db, auth.user.id)
    for acct, direction in ((src, "debit"), (dst, "credit")):
        t = Transaction(
            user_id=auth.user.id,
            account_id=acct.id,
            kind="transfer",
            direction=direction,
            amount_minor=body.amount_minor,
            currency=acct.currency,
            status=body.status,
            transaction_date=body.transaction_date,
            posting_date=body.posting_date,
            narration=blank_to_none(body.narration),
            notes=blank_to_none(body.notes),
            source="manual",
            transfer_group_id=group,
        )
        _settle_posting_date(t)
        cats.apply(ctx, t)
        db.add(t)
        legs.append(t)
    db.flush()
    ids = {src.id: src.public_id, dst.id: dst.public_id}
    for t in legs:
        add_revision(db, t, "create", snapshot(t, ids))
    audit(
        db,
        "transfer.created",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="transfer",
        target_id=str(group),
    )
    db.commit()
    outs = txn_outs(db, auth.user.id, legs)
    return TransferOut(transfer_group_id=group, debit=outs[0], credit=outs[1])


# ---------------- read ----------------


@router.get("/{txn_id}", response_model=TransactionDetailOut)
def get_transaction(
    txn_id: uuid.UUID,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> TransactionDetailOut:
    t = get_txn(db, auth.user.id, txn_id, lock=False)
    revs = db.scalars(
        select(TransactionRevision)
        .where(
            TransactionRevision.user_id == auth.user.id,
            TransactionRevision.transaction_id == t.id,
        )
        .order_by(TransactionRevision.id)
    ).all()
    base = _one_out(db, auth, t)
    return TransactionDetailOut(
        **base.model_dump(),
        revisions=[
            RevisionOut(
                action=r.action, changes=r.changes, reason=r.reason, created_at=r.created_at
            )
            for r in revs
        ],
    )


# ---------------- update ----------------


@router.patch("/{txn_id}", response_model=TransactionOut)
def update_transaction(
    txn_id: uuid.UUID,
    body: TransactionPatch,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> TransactionOut:
    t = get_txn(db, auth.user.id, txn_id)
    raw = body.model_dump(exclude_unset=True)
    reason = blank_to_none(raw.pop("reason", None))
    category_set = "category_id" in raw
    category_choice = raw.pop("category_id", None)
    for k in ("merchant", "narration", "notes"):
        if k in raw:
            raw[k] = blank_to_none(raw[k])
    # Non-nullable fields: an explicit null means "no change".
    for k in ("account_id", "kind", "direction", "amount_minor", "status", "transaction_date"):
        if k in raw and raw[k] is None:
            raw.pop(k)

    if category_set and t.kind in ("transfer", "reversal", "adjustment"):
        raise unprocessable(
            "Transfers, reversals and adjustments get their category automatically."
        )
    if (t.kind == "reversal" or t.status == "reversed") and set(raw) - {"notes"}:
        raise unprocessable(
            "Reversed transactions are locked. Only notes can change; delete the reversal "
            "to undo it."
        )
    if "transaction_date" in raw:
        _check_dates(auth, raw["transaction_date"])

    targets = [t]
    if t.kind == "transfer":
        if set(raw) & {"account_id", "kind", "direction", "merchant"}:
            raise unprocessable(
                "For transfers you can change amount, dates, status and notes. "
                "To change accounts, delete it and create a new transfer."
            )
        targets = transfer_legs(db, auth.user.id, t.transfer_group_id)  # type: ignore[arg-type]
    else:
        if "kind" in raw and raw["kind"] != "adjustment":
            raw["direction"] = FIXED_DIRECTION[raw["kind"]]
        new_kind = raw.get("kind", t.kind)
        if (
            new_kind != "adjustment"
            and "direction" in raw
            and (raw["direction"] != FIXED_DIRECTION[new_kind])
        ):
            raise unprocessable("Direction is fixed for this type.")
        if new_kind != "refund" and t.refund_of_transaction_id:
            t.refund_of_transaction_id = None
        if "account_id" in raw:
            acct = _usable_account(db, auth, raw["account_id"])
            if acct.currency != t.currency:
                raise unprocessable(
                    "You can only move a transaction to an account in the same currency."
                )
            raw["account_id"] = acct.id

    new_tx_date = raw.get("transaction_date", t.transaction_date)
    new_posting = raw.get("posting_date", t.posting_date)
    if new_posting is not None and new_posting < new_tx_date:
        raise unprocessable("Posting date cannot be before the transaction date.")

    ids = _pub_ids(
        db,
        auth.user.id,
        {x.account_id for x in targets} | ({raw["account_id"]} if "account_id" in raw else set()),
    )
    any_change = False
    for x in targets:
        before = snapshot(x, ids)
        for k, v in raw.items():
            setattr(x, k, v)
        _settle_posting_date(x)
        changes = diff(before, snapshot(x, ids))
        if changes:
            any_change = True
            add_revision(db, x, "update", changes, reason)
    any_change |= _update_category(db, auth, t, raw, category_set, category_choice, reason)
    if any_change:
        audit(
            db,
            "transaction.updated",
            user_id=auth.user.id,
            ip=client_ip(request),
            target_type="transaction",
            target_id=str(t.public_id),
        )
        db.commit()
    db.refresh(t)
    return _one_out(db, auth, t)


def _cat_name(db: Session, cat_id: int | None) -> str | None:
    return db.scalar(select(Category.name).where(Category.id == cat_id)) if cat_id else None


def _update_category(
    db: Session,
    auth: CurrentAuth,
    t: Transaction,
    raw: dict[str, object],
    category_set: bool,
    choice: object,
    reason: str | None,
) -> bool:
    """Apply an explicit category choice, or re-run automatic categorisation when something
    that affects it changed. Returns True if anything changed."""
    before_id, before_src = t.category_id, t.category_source
    ctx = cats.load_context(db, auth.user.id)
    if category_set:
        if choice is None:
            cats.apply(ctx, t, user_uncategorised=True)
        else:
            chosen = cats.choose(db, auth.user.id, choice, t.kind)  # type: ignore[arg-type]
            cats.apply(ctx, t, user_category_id=chosen.id)
    elif set(raw) & {"kind", "direction", "merchant", "narration", "account_id"}:
        cat = db.get(Category, t.category_id) if t.category_id else None
        if t.category_source == "user" and (cat is None or not cats.fits(cat, t.kind)):
            t.category_source = "none"  # the old choice no longer makes sense for this type
        cats.apply(ctx, t, linked_category_id=cats.linked_category(db, t))
    cats.flush_hits(db, ctx)
    if before_id != t.category_id or (category_set and before_src != t.category_source):
        add_revision(
            db,
            t,
            "update",
            {"category": [_cat_name(db, before_id), _cat_name(db, t.category_id)]},
            reason if category_set else "Category updated automatically",
        )
        return True
    return category_set and before_src != t.category_source


# ---------------- delete ----------------


@router.post("/{txn_id}/delete", response_model=list[uuid.UUID])
def delete_transaction(
    txn_id: uuid.UUID,
    body: DeleteIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> list[uuid.UUID]:
    """Soft delete: hidden and excluded from every total, but kept for the audit trail.
    Transfers delete both legs. Deleting a reversal row un-reverses the original.
    Deleting a reversed original also deletes its reversal. Returns the ids deleted."""
    t = get_txn(db, auth.user.id, txn_id)
    reason = blank_to_none(body.reason)
    now = utcnow()
    deleted: list[Transaction] = []

    if t.kind == "transfer":
        deleted = transfer_legs(db, auth.user.id, t.transfer_group_id)  # type: ignore[arg-type]
    elif t.kind == "reversal":
        orig = db.scalar(
            select(Transaction)
            .where(Transaction.user_id == auth.user.id, Transaction.id == t.reverses_transaction_id)
            .with_for_update()
        )
        if orig is not None and orig.deleted_at is None and orig.status == "reversed":
            orig.status = "posted"
            add_revision(db, orig, "update", {"status": ["reversed", "posted"]}, "Reversal deleted")
        deleted = [t]
    else:
        deleted = [t]
        if t.status == "reversed":
            rev = db.scalar(
                select(Transaction)
                .where(
                    Transaction.user_id == auth.user.id,
                    Transaction.reverses_transaction_id == t.id,
                    Transaction.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if rev is not None:
                deleted.append(rev)

    for x in deleted:
        x.deleted_at = now
        add_revision(db, x, "delete", {}, reason)
    audit(
        db,
        "transaction.deleted",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="transaction",
        target_id=str(t.public_id),
        details={"count": len(deleted)},
    )
    db.commit()
    return [x.public_id for x in deleted]


# ---------------- reverse ----------------


@router.post(
    "/{txn_id}/reverse", response_model=TransactionOut, status_code=status.HTTP_201_CREATED
)
def reverse_transaction(
    txn_id: uuid.UUID,
    body: ReverseIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> TransactionOut:
    """Record that the bank reversed a posted transaction. The original and the reversal
    then cancel out everywhere (RULES.md R5)."""
    t = get_txn(db, auth.user.id, txn_id)
    if t.kind not in REVERSIBLE:
        raise unprocessable(
            "Transfers and reversals cannot be reversed. Delete the transfer instead."
        )
    if t.status != "posted":
        raise unprocessable(
            "Only posted transactions can be reversed. Mark pending ones as failed."
        )
    rev_date = body.reversal_date or today_for(auth.user)
    if rev_date < t.transaction_date:
        raise unprocessable("The reversal date cannot be before the original transaction.")
    _check_dates(auth, rev_date)
    reason = blank_to_none(body.reason)
    rev = Transaction(
        user_id=auth.user.id,
        account_id=t.account_id,
        kind="reversal",
        direction="credit" if t.direction == "debit" else "debit",
        amount_minor=t.amount_minor,
        currency=t.currency,
        status="posted",
        transaction_date=rev_date,
        posting_date=rev_date,
        merchant=t.merchant,
        narration=f"Reversal of {t.merchant or t.narration or t.kind}"[:500],
        notes=reason,
        source="manual",
        reverses_transaction_id=t.id,
    )
    ctx = cats.load_context(db, auth.user.id)
    cats.apply(ctx, rev, linked_category_id=t.category_id)
    t.status = "reversed"
    db.add(rev)
    db.flush()
    ids = _pub_ids(db, auth.user.id, {t.account_id})
    add_revision(db, t, "reverse", {"status": ["posted", "reversed"]}, reason)
    add_revision(db, rev, "create", snapshot(rev, ids), reason)
    audit(
        db,
        "transaction.reversed",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="transaction",
        target_id=str(t.public_id),
    )
    db.commit()
    db.refresh(rev)
    return _one_out(db, auth, rev)
