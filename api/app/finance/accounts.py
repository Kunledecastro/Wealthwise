import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import record as audit
from app.auth.sessions import CurrentAuth, client_ip, require_auth
from app.db.models import Account, Currency, Transaction
from app.db.session import get_db
from app.finance.schemas import AccountIn, AccountOut, AccountPatch
from app.finance.service import (
    account_out,
    balances_for,
    blank_to_none,
    get_account,
    today_for,
    unprocessable,
)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _out(db: Session, auth: CurrentAuth, a: Account) -> AccountOut:
    today = today_for(auth.user)
    bal, count = balances_for(db, auth.user.id, [a])[a.id]
    return account_out(a, bal, count, today)


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
