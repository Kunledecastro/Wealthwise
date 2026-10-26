"""Structured logging with redaction of personal and financial data.

Anything that could identify a user or reveal their finances is masked before it
is written. Request bodies are never logged.
"""

import logging
import re
from collections.abc import MutableMapping
from typing import Any

import structlog

SENSITIVE_KEYS = {
    "password",
    "new_password",
    "current_password",
    "password_hash",
    "token",
    "invite_token",
    "session",
    "cookie",
    "authorization",
    "csrf",
    "email",
    "amount",
    "amount_minor",
    "balance",
    "narration",
    "merchant",
    "account_number",
    "secret",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 10+ consecutive digits: NUBAN account numbers, card PANs, phone numbers.
LONG_DIGITS_RE = re.compile(r"\b\d{10,19}\b")
TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")


def redact_text(value: str) -> str:
    value = EMAIL_RE.sub("[email]", value)
    value = LONG_DIGITS_RE.sub("[digits]", value)
    return TOKEN_RE.sub("[token]", value)


def _redact(value: Any, key: str | None = None) -> Any:
    if key is not None and any(s in key.lower() for s in SENSITIVE_KEYS):
        return "[redacted]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(v) for v in value]
    return value


def redaction_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for k in list(event_dict.keys()):
        event_dict[k] = _redact(event_dict[k], None if k == "event" else k)
    return event_dict


class _RedactingFilter(logging.Filter):
    """Applies the same masking to stdlib loggers (uvicorn, sqlalchemy)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - malformed record
            return True
        record.msg = redact_text(msg)
        record.args = None
        return True


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(message)s")
    redacting = _RedactingFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(redacting)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redaction_processor,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "wealthwise") -> Any:
    return structlog.get_logger(name)
