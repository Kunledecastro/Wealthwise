from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditEvent


def record(
    db: Session,
    action: str,
    *,
    user_id: int | None = None,
    actor_user_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an audit event to the current DB transaction.

    It is committed together with the change it describes, so an audit row never
    exists for a change that was rolled back (and vice versa).
    Never put secrets, tokens, passwords or full financial values in `details`.
    """
    db.add(
        AuditEvent(
            action=action,
            user_id=user_id,
            actor_user_id=actor_user_id if actor_user_id is not None else user_id,
            target_type=target_type,
            target_id=target_id,
            ip=ip,
            details=details or {},
        )
    )
