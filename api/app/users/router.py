from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.audit.service import record as audit
from app.auth.schemas import PreferencesOut, PreferencesPatch, UserOut
from app.auth.sessions import CurrentAuth, client_ip, require_auth
from app.core.config import get_settings
from app.db.models import Currency, User
from app.db.session import get_db

router = APIRouter(prefix="/api/me", tags=["me"])


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.public_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        preferences=PreferencesOut.model_validate(user.preferences),
    )


@router.get("", response_model=UserOut)
def me(auth: CurrentAuth = Depends(require_auth)) -> UserOut:
    return user_out(auth.user)


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(auth: CurrentAuth = Depends(require_auth)) -> PreferencesOut:
    return PreferencesOut.model_validate(auth.user.preferences)


@router.patch("/preferences", response_model=PreferencesOut)
def update_preferences(
    body: PreferencesPatch,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(require_auth),
) -> PreferencesOut:
    # Preferences are always loaded through the authenticated user: there is no
    # way to address another user's preferences from this endpoint.
    prefs = auth.user.preferences
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "currency" in changes:
        cur = db.get(Currency, changes["currency"])
        if cur is None or not cur.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsupported currency.")
    changed = [k for k, v in changes.items() if getattr(prefs, k) != v]
    for k in changed:
        setattr(prefs, k, changes[k])
    if changed:
        ip = client_ip(request)
        audit(
            db,
            "preferences.update",
            user_id=auth.user.id,
            ip=ip,
            details={"fields": sorted(changed)},
        )
        if "external_ai_consent" in changed:
            audit(
                db,
                "consent.external_ai",
                user_id=auth.user.id,
                ip=ip,
                details={"granted": prefs.external_ai_consent},
            )
        db.commit()
    return PreferencesOut.model_validate(prefs)


@router.get("/app-config")
def app_config(_: CurrentAuth = Depends(require_auth)) -> dict[str, object]:
    """Feature flags the signed-in UI needs."""
    s = get_settings()
    return {"demo_mode": s.demo_mode, "upload_max_mb": s.upload_max_mb}
