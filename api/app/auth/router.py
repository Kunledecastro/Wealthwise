from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record as audit
from app.auth import ratelimit
from app.auth.schemas import (
    ChangePasswordIn,
    CsrfOut,
    ForgotIn,
    LoginIn,
    MessageOut,
    RegisterIn,
    ResetIn,
    UserOut,
)
from app.auth.service import (
    create_user,
    find_usable_invite,
    issue_reset_token,
    reset_url,
    validate_new_password,
)
from app.auth.sessions import (
    CurrentAuth,
    clear_session_cookie,
    client_ip,
    create_session,
    optional_auth,
    require_auth,
    revoke_user_sessions,
    set_session_cookie,
)
from app.core.config import get_settings
from app.core.csrf import issue_csrf_cookie
from app.core.email import send_email
from app.core.security import (
    hash_identifier,
    hash_password,
    hash_token,
    needs_rehash,
    verify_password,
)
from app.db.models import PasswordResetToken, User, utcnow
from app.db.session import get_db
from app.users.router import user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Incorrect email or password."


@router.get("/csrf", response_model=CsrfOut)
def csrf(response: Response) -> CsrfOut:
    return CsrfOut(csrf_token=issue_csrf_cookie(response))


@router.post("/login", response_model=UserOut)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    existing: CurrentAuth | None = Depends(optional_auth),
) -> UserOut:
    s = get_settings()
    ip = client_ip(request)
    ident = hash_identifier(body.email)
    ratelimit.check_login_allowed(
        db,
        ident,
        ip,
        s.login_max_attempts,
        timedelta(minutes=s.login_lockout_minutes),
        s.ip_max_failed_attempts,
    )

    user = db.scalar(select(User).where(User.email == body.email))
    ok = verify_password(user.password_hash if user else None, body.password)
    if not ok or user is None or user.status != "active":
        ratelimit.record_attempt(db, "login", identifier_hash=ident, ip=ip, success=False)
        audit(
            db,
            "auth.login_failed",
            user_id=user.id if user else None,
            ip=ip,
            details={"reason": "disabled" if (user and ok) else "bad_credentials"},
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_LOGIN_ERROR)

    ratelimit.record_attempt(db, "login", identifier_hash=ident, ip=ip, success=True)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    if existing is not None:  # session fixation: always issue a fresh session
        existing.session.revoked_at = utcnow()
    token = create_session(db, user, request)
    user.last_login_at = utcnow()
    audit(db, "auth.login", user_id=user.id, ip=ip)
    db.commit()
    set_session_cookie(response, token)
    issue_csrf_cookie(response)  # rotate CSRF token with the new session
    return user_out(user)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    s = get_settings()
    if s.registration_mode == "closed":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is closed.")
    ip = client_ip(request)
    ratelimit.check_generic(
        db, "register", window=timedelta(hours=1), limit=20, ip=ip, failures_only=True
    )

    invite = find_usable_invite(db, body.invite_token)
    if invite is None or (invite.email and invite.email.lower() != body.email.lower()):
        ratelimit.record_attempt(db, "register", identifier_hash=None, ip=ip, success=False)
        db.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This invite link is invalid, expired or already used. Ask your admin for a new one.",
        )

    user = create_user(db, email=body.email, password=body.password, display_name=body.display_name)
    invite.used_at = utcnow()
    invite.used_by = user.id
    ratelimit.record_attempt(db, "register", identifier_hash=None, ip=ip, success=True)
    audit(
        db,
        "auth.register",
        user_id=user.id,
        ip=ip,
        target_type="invite",
        target_id=str(invite.public_id),
    )
    token = create_session(db, user, request)
    user.last_login_at = utcnow()
    db.commit()
    set_session_cookie(response, token)
    issue_csrf_cookie(response)
    return user_out(user)


@router.post("/logout", response_model=MessageOut)
def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth | None = Depends(optional_auth),
) -> MessageOut:
    if auth is not None:
        auth.session.revoked_at = utcnow()
        audit(db, "auth.logout", user_id=auth.user.id, ip=client_ip(request))
        db.commit()
    clear_session_cookie(response)
    return MessageOut(message="Signed out.")


@router.post("/logout-all", response_model=MessageOut)
def logout_all(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> MessageOut:
    revoke_user_sessions(db, auth.user.id)
    audit(db, "auth.logout_all", user_id=auth.user.id, ip=client_ip(request))
    db.commit()
    clear_session_cookie(response)
    return MessageOut(message="Signed out on all devices.")


FORGOT_MESSAGE = "If an account exists for that email, a reset link has been sent."


@router.post("/password/forgot", response_model=MessageOut, status_code=202)
def forgot_password(
    body: ForgotIn,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MessageOut:
    s = get_settings()
    ip = client_ip(request)
    ident = hash_identifier(body.email)
    ratelimit.check_generic(db, "reset", window=timedelta(hours=1), limit=3, identifier_hash=ident)
    ratelimit.check_generic(db, "reset", window=timedelta(hours=1), limit=10, ip=ip)
    ratelimit.record_attempt(db, "reset", identifier_hash=ident, ip=ip, success=True)

    user = db.scalar(select(User).where(User.email == body.email))
    if user is not None and user.status == "active":
        token = issue_reset_token(db, user)
        audit(db, "auth.password_reset_requested", user_id=user.id, ip=ip)
        body_text = (
            f"Hello {user.display_name},\n\nSomeone (hopefully you) asked to reset your "
            f"{s.app_name} password. Use this link within "
            f"{s.password_reset_valid_minutes} minutes:\n\n{reset_url(token)}\n\n"
            "If you did not ask for this, ignore this email; your password is unchanged."
        )
        background.add_task(send_email, user.email, f"{s.app_name} password reset", body_text)
    db.commit()
    return MessageOut(message=FORGOT_MESSAGE)


@router.post("/password/reset", response_model=MessageOut)
def reset_password(
    body: ResetIn, request: Request, response: Response, db: Session = Depends(get_db)
) -> MessageOut:
    ip = client_ip(request)
    ratelimit.check_generic(
        db, "reset_use", window=timedelta(hours=1), limit=20, ip=ip, failures_only=True
    )
    rec = db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_token(body.token))
        .with_for_update()
    )
    if rec is None or rec.used_at is not None or rec.expires_at <= utcnow():
        ratelimit.record_attempt(db, "reset_use", identifier_hash=None, ip=ip, success=False)
        db.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This reset link is invalid or has expired. Request a new one.",
        )
    user = db.get(User, rec.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid.")
    validate_new_password(body.new_password, user.email)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = utcnow()
    rec.used_at = utcnow()
    revoke_user_sessions(db, user.id)
    audit(db, "auth.password_reset", user_id=user.id, ip=ip)
    db.commit()
    clear_session_cookie(response)
    return MessageOut(message="Password updated. Please sign in with your new password.")


@router.post("/password/change", response_model=MessageOut)
def change_password(
    body: ChangePasswordIn,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> MessageOut:
    user = auth.user
    ip = client_ip(request)
    ident = hash_identifier(user.email)
    ratelimit.check_generic(
        db,
        "pw_change",
        window=timedelta(minutes=15),
        limit=5,
        identifier_hash=ident,
        failures_only=True,
    )
    if not verify_password(user.password_hash, body.current_password):
        ratelimit.record_attempt(db, "pw_change", identifier_hash=ident, ip=ip, success=False)
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    validate_new_password(body.new_password, user.email)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = utcnow()
    revoke_user_sessions(db, user.id, except_id=auth.session.id)
    audit(db, "auth.password_changed", user_id=user.id, ip=ip)
    db.commit()
    return MessageOut(message="Password changed. Other devices have been signed out.")
