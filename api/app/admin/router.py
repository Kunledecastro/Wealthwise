import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record as audit
from app.auth.schemas import (
    AdminUserOut,
    InviteCreatedOut,
    InviteIn,
    InviteOut,
    UserStatusIn,
)
from app.auth.service import create_invite, invite_status, invite_url
from app.auth.sessions import CurrentAuth, client_ip, require_admin, revoke_user_sessions
from app.db.models import Invite, User, utcnow
from app.db.session import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _invite_out(inv: Invite) -> InviteOut:
    return InviteOut(
        id=inv.public_id,
        email=inv.email,
        note=inv.note,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
        status=invite_status(inv),
    )


@router.post("/invites", response_model=InviteCreatedOut, status_code=status.HTTP_201_CREATED)
def new_invite(
    body: InviteIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_admin),
) -> InviteCreatedOut:
    inv, token = create_invite(db, created_by=auth.user.id, email=body.email, note=body.note)
    audit(
        db,
        "admin.invite_created",
        user_id=auth.user.id,
        ip=client_ip(request),
        target_type="invite",
        target_id=str(inv.public_id),
    )
    db.commit()
    db.refresh(inv)
    # The raw token is returned exactly once; only its hash is stored.
    return InviteCreatedOut(**_invite_out(inv).model_dump(), invite_url=invite_url(token))


@router.get("/invites", response_model=list[InviteOut])
def list_invites(
    db: Session = Depends(get_db), _: CurrentAuth = Depends(require_admin)
) -> list[InviteOut]:
    rows = db.scalars(select(Invite).order_by(Invite.created_at.desc()).limit(200))
    return [_invite_out(i) for i in rows]


@router.post("/invites/{invite_id}/revoke", response_model=InviteOut)
def revoke_invite(
    invite_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_admin),
) -> InviteOut:
    inv = db.scalar(select(Invite).where(Invite.public_id == invite_id))
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found.")
    if invite_status(inv) == "pending":
        inv.revoked_at = utcnow()
        audit(
            db,
            "admin.invite_revoked",
            user_id=auth.user.id,
            ip=client_ip(request),
            target_type="invite",
            target_id=str(inv.public_id),
        )
        db.commit()
    return _invite_out(inv)


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    db: Session = Depends(get_db), _: CurrentAuth = Depends(require_admin)
) -> list[AdminUserOut]:
    rows = db.scalars(select(User).order_by(User.created_at))
    return [
        AdminUserOut(
            id=u.public_id,
            email=u.email,
            display_name=u.display_name,
            role=u.role,
            status=u.status,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
        )
        for u in rows
    ]


@router.post("/users/{user_id}/status", response_model=AdminUserOut)
def set_user_status(
    user_id: uuid.UUID,
    body: UserStatusIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_admin),
) -> AdminUserOut:
    u = db.scalar(select(User).where(User.public_id == user_id))
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if u.id == auth.user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own status.")
    if u.status != body.status:
        u.status = body.status
        if body.status == "disabled":
            revoke_user_sessions(db, u.id)
        audit(
            db,
            f"admin.user_{body.status}",
            user_id=u.id,
            actor_user_id=auth.user.id,
            ip=client_ip(request),
            target_type="user",
            target_id=str(u.public_id),
        )
        db.commit()
    return AdminUserOut(
        id=u.public_id,
        email=u.email,
        display_name=u.display_name,
        role=u.role,
        status=u.status,
        created_at=u.created_at,
        last_login_at=u.last_login_at,
    )
