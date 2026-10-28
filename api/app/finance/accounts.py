import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import record as audit
from app.auth.sessions import CurrentAuth, client_ip, require_auth
from app.db.models import Account, Currency, ReconciliationPoint, Transaction
from app.db.session import get_db
from app.finance.schemas import (
    AccountIn,
    AccountOut,
    AccountPatch,
    ReconcileIn,
    ReconciliationOut,
)
from app.finance.service import (
    account_out,
    balances_for,
    blank_to_none,
    get_account,
    live_entries,
    today_for,
    unprocessable,
)
from app.ledger.engine import reconcile

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _out(db: Session, auth: CurrentAuth, a: Account) -> AccountOut:
    today = today_for(auth.user)
    return account_out(a, *balances_for(db, auth.user.id, [a])[a.id], today)


@router.get("", response_model=list[AccountOut])
def list_accounts(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> list[AccountOut]:
    stmt = select(Account).where(Account.user_id == auth.user.id)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    accounts = db.scalars(stmt.order_by(Account.is_archived, Account.created_at)).all()
    today = today_for(auth.user)
    bals = balances_for(db, auth.user.id, accounts)
    return [account_out(a, *bals[a.id], today) for a in accounts]


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    body: AccountIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> AccountOut:
    cur = db.get(Currency, body.currency)
    if cur is None or not cur.is_active:
        raise unprocessable("Unsupported currency.")
    if body.opening_balance_date > today_for(auth.user):
        raise unprocessable("Opening balance date cannot be in the future.")
    if (
        db.scalar(select(func.count()).select_from(Account).where(Account.user_id == auth.user.id))
        or 0
    ) >= 100:
        raise unprocessable("Account limit reached (100).")
    a = Account(
        user_id=auth.user.id,
        type=body.type,
        display_name=body.display_name,
        institution_name=blank_to_none(body.institution_name),
        mask=blank_to_none(body.mask),
        currency=body.currency,
        opening_balance_minor=body.opening_balance_minor,
        opening_balance_date=body.opening_balance_date,
        source="manual",  # only a real integration may ever set "connected"
    )
    db.add(a)
    db.flush()
    audit(
        db,
        "account.created",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="account",
        target_id=str(a.public_id),
    )
    db.commit()
    db.refresh(a)
    return _out(db, auth, a)


@router.get("/{account_id}", response_model=AccountOut)
def get_one(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> AccountOut:
    return _out(db, auth, get_account(db, auth.user.id, account_id))


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: uuid.UUID,
    body: AccountPatch,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> AccountOut:
    a = get_account(db, auth.user.id, account_id, lock=True)
    changes = body.model_dump(exclude_unset=True)
    for k in ("institution_name", "mask"):
        if k in changes:
            changes[k] = blank_to_none(changes[k])
    if changes.get("display_name") is None:
        changes.pop("display_name", None)
    if changes.get("type") is None:
        changes.pop("type", None)
    for k in ("opening_balance_minor", "opening_balance_date", "is_archived"):
        if k in changes and changes[k] is None:
            changes.pop(k)
    if "opening_balance_date" in changes and changes["opening_balance_date"] > today_for(auth.user):
        raise unprocessable("Opening balance date cannot be in the future.")
    changed = {k: v for k, v in changes.items() if getattr(a, k) != v}
    for k, v in changed.items():
        setattr(a, k, v)
    if changed:
        audit(
            db,
            "account.updated",
            user_id=auth.user.id,
            ip=client_ip(request),
            target_type="account",
            target_id=str(a.public_id),
            details={"fields": sorted(changed)},
        )
        db.commit()
    return _out(db, auth, a)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> Response:
    """Only an account that has never had a transaction can be deleted; otherwise archive it,
    so history is never silently lost."""
    a = get_account(db, auth.user.id, account_id, lock=True)
    has_any = db.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.user_id == auth.user.id, Transaction.account_id == a.id)
    )
    if has_any:
        raise unprocessable("This account has transactions. Archive it instead.")
    audit(
        db,
        "account.deleted",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="account",
        target_id=str(a.public_id),
    )
    db.delete(a)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- reconciliation ----------------


@router.post(
    "/{account_id}/reconcile",
    response_model=ReconciliationOut,
    status_code=status.HTTP_201_CREATED,
)
def reconcile_account(
    account_id: uuid.UUID,
    body: ReconcileIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> ReconciliationOut:
    """Record the balance your bank shows on a date, and compare it with ours (RULES B5)."""
    a = get_account(db, auth.user.id, account_id)
    if body.as_of_date > today_for(auth.user):
        raise unprocessable("The statement date cannot be in the future.")
    if body.as_of_date < a.opening_balance_date:
        raise unprocessable(
            "That date is before this account's starting balance date, so there's nothing "
            "to compare. Change the starting balance date first."
        )
    entries = live_entries(db, auth.user.id, [a.id])[a.id]
    rec = reconcile(
        currency=a.currency,
        opening_minor=a.opening_balance_minor,
        opening_date=a.opening_balance_date,
        entries=entries,
        as_of=body.as_of_date,
        statement_minor=body.statement_balance_minor,
    )
    p = ReconciliationPoint(
        user_id=auth.user.id,
        account_id=a.id,
        as_of_date=body.as_of_date,
        statement_balance_minor=body.statement_balance_minor,
        computed_balance_minor=rec.computed_minor,
        source="manual",
    )
    db.add(p)
    db.flush()
    audit(
        db,
        "account.reconciled",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="account",
        target_id=str(a.public_id),
        details={"matches": rec.matches},
    )
    db.commit()
    db.refresh(p)
    return _point_out(p, rec.computed_minor)


@router.get("/{account_id}/reconciliations", response_model=list[ReconciliationOut])
def list_reconciliations(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> list[ReconciliationOut]:
    a = get_account(db, auth.user.id, account_id)
    entries = live_entries(db, auth.user.id, [a.id])[a.id]
    points = db.scalars(
        select(ReconciliationPoint)
        .where(ReconciliationPoint.user_id == auth.user.id, ReconciliationPoint.account_id == a.id)
        .order_by(ReconciliationPoint.as_of_date.desc(), ReconciliationPoint.id.desc())
        .limit(50)
    ).all()
    out = []
    for p in points:
        now = reconcile(
            currency=a.currency,
            opening_minor=a.opening_balance_minor,
            opening_date=a.opening_balance_date,
            entries=entries,
            as_of=p.as_of_date,
            statement_minor=p.statement_balance_minor,
        )
        out.append(_point_out(p, now.computed_minor))
    return out


def _point_out(p: ReconciliationPoint, computed_now: int) -> ReconciliationOut:
    return ReconciliationOut(
        id=p.public_id,
        as_of_date=p.as_of_date,
        statement_balance_minor=p.statement_balance_minor,
        computed_balance_minor_then=p.computed_balance_minor,
        computed_balance_minor_now=computed_now,
        difference_minor_now=p.statement_balance_minor - computed_now,
        source=p.source,
        created_at=p.created_at,
    )
