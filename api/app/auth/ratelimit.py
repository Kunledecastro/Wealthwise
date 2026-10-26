"""Postgres-backed rate limiting (decision D-012). Survives restarts; no Redis needed."""

from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AuthAttempt, utcnow


def record_attempt(
    db: Session, kind: str, *, identifier_hash: str | None, ip: str | None, success: bool
) -> None:
    db.add(AuthAttempt(kind=kind, identifier_hash=identifier_hash, ip=ip, success=success))


def _count(
    db: Session,
    kind: str,
    window: timedelta,
    *,
    identifier_hash: str | None = None,
    ip: str | None = None,
    failures_only: bool = True,
    since_last_success: bool = False,
) -> int:
    start = utcnow() - window
    conds = [AuthAttempt.kind == kind, AuthAttempt.created_at >= start]
    if identifier_hash is not None:
        conds.append(AuthAttempt.identifier_hash == identifier_hash)
    if ip is not None:
        conds.append(AuthAttempt.ip == ip)
    if since_last_success and identifier_hash is not None:
        last_ok = db.scalar(
            select(func.max(AuthAttempt.created_at)).where(
                AuthAttempt.kind == kind,
                AuthAttempt.identifier_hash == identifier_hash,
                AuthAttempt.success.is_(True),
            )
        )
        if last_ok is not None and last_ok > start:
            conds.append(AuthAttempt.created_at > last_ok)
    if failures_only:
        conds.append(AuthAttempt.success.is_(False))
    return db.scalar(select(func.count()).select_from(AuthAttempt).where(*conds)) or 0


def too_many() -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Too many attempts. Please wait a few minutes and try again.",
    )


def check_login_allowed(
    db: Session,
    identifier_hash: str,
    ip: str | None,
    max_attempts: int,
    lockout: timedelta,
    ip_max: int,
) -> None:
    if (
        _count(db, "login", lockout, identifier_hash=identifier_hash, since_last_success=True)
        >= max_attempts
    ):
        raise too_many()
    if ip and _count(db, "login", lockout, ip=ip) >= ip_max:
        raise too_many()


def check_generic(
    db: Session,
    kind: str,
    *,
    window: timedelta,
    limit: int,
    identifier_hash: str | None = None,
    ip: str | None = None,
    failures_only: bool = False,
) -> None:
    if (
        _count(
            db, kind, window, identifier_hash=identifier_hash, ip=ip, failures_only=failures_only
        )
        >= limit
    ):
        raise too_many()
