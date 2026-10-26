import smtplib
import sys
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


def send_email(to: str, subject: str, body: str) -> None:
    """Send a plain-text email. Called from background tasks so response timing
    does not reveal whether an address exists."""
    s = get_settings()
    if s.email_backend == "console":
        if s.app_env == "production":
            # Never print tokens into production logs. Admin can issue links via CLI.
            log.warning("email.suppressed", reason="EMAIL_BACKEND=console in production")
            return
        # Development only: printed directly (bypasses log redaction on purpose so
        # developers can click the link). Never enabled in production.
        banner = "=" * 21
        sys.stdout.write(
            f"\n===== DEV EMAIL =====\nTo: {to}\nSubject: {subject}\n\n{body}\n{banner}\n"
        )
        sys.stdout.flush()
        return

    msg = EmailMessage()
    msg["From"] = s.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        log.error("email.failed", error=type(exc).__name__)
