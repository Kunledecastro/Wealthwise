"""Auth domain logic shared by the HTTP API and the admin CLI."""

from datetime import timedelta

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password, hash_token, new_token, password_problems
from app.db.models import Invite, PasswordResetToken, User, UserPreferences, utcnow


def validate_new_password(password: str, email: str | None) -> None:
    problems = password_problems(password, email)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problems[0])


def create_user(
    db: Session, *, email: str, password: str, display_name: str, role: str = "member"
) -> User:
    s = get_settings()
    # Same validation the login form applies, so every account can actually sign in
    # (the CLI path bypasses the HTTP schema).
    try:
        email = validate_email(email.strip(), check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid email address: {exc}"
        ) from exc
    validate_new_password(password, email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        role=role,
        password_changed_at=utcnow(),
    )
    user.preferences = UserPreferences(currency=s.default_currency, timezone=s.default_timezone)
    db.add(user)
    db.flush()
    return user


def create_invite(
    db: Session, *, created_by: int | None, email: str | None, note: str | None
) -> tuple[Invite, str]:
    s = get_settings()
    token = new_token()
    invite = Invite(
        token_hash=hash_token(token),
        email=email,
        note=note,
        created_by=created_by,
        expires_at=utcnow() + timedelta(days=s.invite_valid_days),
    )
    db.add(invite)
    db.flush()
    return invite, token


def invite_url(token: str) -> str:
    # Token goes in the URL fragment: browsers never send fragments to servers,
    # so it does not appear in proxy or server access logs.
    return f"{get_settings().app_base_url.rstrip('/')}/register#invite={token}"


def invite_status(invite: Invite) -> str:
    if invite.revoked_at:
        return "revoked"
    if invite.used_at:
        return "used"
    if invite.expires_at <= utcnow():
        return "expired"
    return "pending"


def find_usable_invite(db: Session, token: str) -> Invite | None:
    invite = db.scalar(
        select(Invite).where(Invite.token_hash == hash_token(token)).with_for_update()
    )
    if invite is None or invite_status(invite) != "pending":
        return None
    return invite


def issue_reset_token(db: Session, user: User) -> str:
    s = get_settings()
    # Only the newest reset link is valid.
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    token = new_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(minutes=s.password_reset_valid_minutes),
        )
    )
    return token


def reset_url(token: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}/reset-password#token={token}"
