"""Your data: change sign-in email, export everything, delete your account."""

import json
from datetime import timedelta
from typing import Any

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import record as audit
from app.auth import ratelimit
from app.auth.schemas import MessageOut, Strict, UserOut
from app.auth.sessions import (
    CurrentAuth,
    clear_session_cookie,
    client_ip,
    require_auth,
    revoke_user_sessions,
)
from app.core.security import hash_identifier, verify_password
from app.db.models import (
    Account,
    Category,
    CategoryRule,
    Transaction,
    TransactionRevision,
    User,
    utcnow,
)
from app.db.session import get_db
from app.finance.service import (
    account_out,
    balances_for,
    today_for,
    txn_outs,
)
from app.users.router import user_out

router = APIRouter(prefix="/api/me", tags=["me"])


class EmailChangeIn(Strict):
    new_email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class DeleteMeIn(Strict):
    password: str = Field(min_length=1, max_length=256)
    confirm: str = Field(max_length=16)


def _check_password(db: Session, auth: CurrentAuth, password: str, ip: str | None) -> None:
    ident = hash_identifier(auth.user.email)
    ratelimit.check_generic(
        db,
        "pw_check",
        window=timedelta(minutes=15),
        limit=5,
        identifier_hash=ident,
        failures_only=True,
    )
    if not verify_password(auth.user.password_hash, password):
        ratelimit.record_attempt(db, "pw_check", identifier_hash=ident, ip=ip, success=False)
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password is incorrect.")


@router.post("/email", response_model=UserOut)
def change_email(
    body: EmailChangeIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> UserOut:
    ip = client_ip(request)
    _check_password(db, auth, body.password, ip)
    try:
        new = validate_email(body.new_email, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if new.lower() == auth.user.email.lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That is already your email.")
    if db.scalar(select(User.id).where(User.email == new)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already in use.")
    auth.user.email = new
    revoke_user_sessions(db, auth.user.id, except_id=auth.session.id)
    audit(db, "account.email_changed", user_id=auth.user.id, ip=ip)  # no addresses in the log
    db.commit()
    return user_out(auth.user)


def _export_payload(db: Session, auth: CurrentAuth) -> dict[str, Any]:
    u = auth.user
    accounts = db.scalars(
        select(Account).where(Account.user_id == u.id).order_by(Account.created_at)
    ).all()
    bals = balances_for(db, u.id, accounts)
    today = today_for(u)
    live = db.scalars(
        select(Transaction)
        .where(Transaction.user_id == u.id, Transaction.deleted_at.is_(None))
        .order_by(Transaction.transaction_date, Transaction.id)
    ).all()
    deleted_count = db.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.user_id == u.id, Transaction.deleted_at.is_not(None))
    )
    pub = {
        t.id: str(t.public_id)
        for t in db.scalars(select(Transaction).where(Transaction.user_id == u.id))
    }
    revisions = [
        {
            "transaction_id": pub.get(r.transaction_id),
            "action": r.action,
            "changes": r.changes,
            "reason": r.reason,
            "at": r.created_at.isoformat(),
        }
        for r in db.scalars(
            select(TransactionRevision)
            .where(TransactionRevision.user_id == u.id)
            .order_by(TransactionRevision.id)
        )
    ]
    cat_names = dict(
        db.execute(select(Category.id, Category.name).where(Category.user_id == u.id)).all()
    )
    return {
        "format": "wealthwise-export",
        "version": 1,
        "exported_at": utcnow().isoformat(),
        "money_note": "All amounts are integers in minor units (kobo for NGN).",
        "user": json.loads(user_out(u).model_dump_json()),
        "accounts": [
            json.loads(account_out(a, *bals[a.id], today).model_dump_json()) for a in accounts
        ],
        "transactions": [json.loads(t.model_dump_json()) for t in txn_outs(db, u.id, live)],
        "categories": [
            {
                "id": str(c.public_id),
                "name": c.name,
                "kind": c.kind,
                "color": c.color,
                "archived": c.is_archived,
            }
            for c in db.scalars(select(Category).where(Category.user_id == u.id))
        ],
        "category_rules": [
            {
                "match_type": r.match_type,
                "pattern": r.pattern,
                "direction": r.direction,
                "category": cat_names.get(r.category_id),
                "priority": r.priority,
                "active": r.is_active,
            }
            for r in db.scalars(select(CategoryRule).where(CategoryRule.user_id == u.id))
        ],
        "deleted_transaction_count": deleted_count,
        "revisions": revisions,
    }


@router.get("/export")
def export_all(
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> JSONResponse:
    payload = _export_payload(db, auth)
    audit(db, "data.export_json", user_id=auth.user.id, ip=client_ip(request))
    db.commit()
    stamp = today_for(auth.user).isoformat()
    return JSONResponse(
        payload,
        headers={"Content-Disposition": f'attachment; filename="wealthwise-export-{stamp}.json"'},
    )


@router.post("/delete", response_model=MessageOut)
def delete_me(
    body: DeleteMeIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> MessageOut:
    """Permanently delete the signed-in user and all of their financial data.

    Audit events keep only the numeric user id and action (no personal or financial data),
    so there is a record that the deletion happened."""
    ip = client_ip(request)
    if body.confirm != "DELETE":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Type DELETE to confirm.")
    _check_password(db, auth, body.password, ip)
    u = auth.user
    if u.role == "admin":
        other_admins = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.status == "active", User.id != u.id)
        )
        if not other_admins:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You are the only admin. Make someone else an admin before deleting your account.",
            )
    uid = u.id
    db.delete(u)  # cascades to preferences, sessions, accounts, transactions, revisions
    audit(db, "account.deleted_by_user", user_id=uid, ip=ip)
    db.commit()
    clear_session_cookie(response)
    return MessageOut(message="Your account and all your data have been deleted.")
