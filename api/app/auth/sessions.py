"""Server-side sessions and request-level auth dependencies (decision D-003)."""

import ipaddress
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_token, new_token
from app.db.models import AuthSession, User, utcnow
from app.db.session import get_db

TOUCH_INTERVAL = timedelta(seconds=60)


def client_ip(request: Request) -> str | None:
    # Uvicorn runs with --proxy-headers and a restricted --forwarded-allow-ips, so
    # request.client already reflects the real client behind our own proxy only.
    host = request.client.host if request.client else None
    if not host:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def create_session(db: Session, user: User, request: Request) -> str:
    s = get_settings()
    token = new_token()
    now = utcnow()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            last_seen_at=now,
            expires_at=now + timedelta(days=s.session_absolute_days),
            ip=client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:256] or None,
        )
    )
    return token


def set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name,
        token,
        max_age=s.session_absolute_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(
        s.session_cookie_name, path="/", secure=s.cookie_secure, httponly=True, samesite="lax"
    )


def revoke_user_sessions(db: Session, user_id: int, except_id: int | None = None) -> None:
    stmt = (
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    if except_id is not None:
        stmt = stmt.where(AuthSession.id != except_id)
    db.execute(stmt)


@dataclass
class CurrentAuth:
    user: User
    session: AuthSession


def _load_session(db: Session, request: Request) -> CurrentAuth | None:
    s = get_settings()
    token = request.cookies.get(s.session_cookie_name)
    if not token or len(token) > 128:
        return None
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if sess is None or sess.revoked_at is not None:
        return None
    now = utcnow()
    idle_limit = sess.last_seen_at + timedelta(minutes=s.session_idle_minutes)
    if now >= sess.expires_at or now >= idle_limit:
        sess.revoked_at = now
        db.commit()
        return None
    user = db.get(User, sess.user_id)
    if user is None or user.status != "active":
        return None
    if now - sess.last_seen_at >= TOUCH_INTERVAL:
        sess.last_seen_at = now
        db.commit()
    return CurrentAuth(user=user, session=sess)


def optional_auth(request: Request, db: Session = Depends(get_db)) -> CurrentAuth | None:
    return _load_session(db, request)


def require_auth(request: Request, db: Session = Depends(get_db)) -> CurrentAuth:
    auth = _load_session(db, request)
    if auth is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    return auth


def require_admin(auth: CurrentAuth = Depends(require_auth)) -> CurrentAuth:
    if auth.user.role != "admin":
        # 404 rather than 403: don't advertise admin endpoints to members.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return auth
