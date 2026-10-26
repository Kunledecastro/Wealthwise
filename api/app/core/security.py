import hashlib
import hmac
import secrets
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

# argon2-cffi defaults follow RFC 9106 low-memory profile (Argon2id, t=3, m=64 MiB, p=4).
_hasher = PasswordHasher()
# Used to equalise timing when the email does not exist.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")

PASSWORD_MIN = 10
PASSWORD_MAX = 128
_COMMON_FILE = Path(__file__).with_name("common_passwords.txt")
_COMMON: frozenset[str] = frozenset(
    line.strip().lower() for line in _COMMON_FILE.read_text().splitlines() if line.strip()
)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problems(password: str, email: str | None = None) -> list[str]:
    problems = []
    if len(password) < PASSWORD_MIN:
        problems.append(f"Password must be at least {PASSWORD_MIN} characters.")
    if len(password) > PASSWORD_MAX:
        problems.append(f"Password must be at most {PASSWORD_MAX} characters.")
    if password.lower() in _COMMON:
        problems.append("This password is too common. Choose something less predictable.")
    local = email.split("@")[0].lower() if email else ""
    if len(local) > 3 and local in password.lower():
        problems.append("Password must not contain your email name.")
    if len(set(password)) < 4:
        problems.append("Password is too repetitive.")
    return problems


def new_token() -> str:
    """256-bit URL-safe random token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Tokens are stored only as SHA-256 hashes; they are high-entropy so no salt is needed."""
    return hashlib.sha256(token.encode()).hexdigest()


def hash_identifier(value: str) -> str:
    """Keyed hash for identifiers (e.g. emails in rate-limit rows) so they are not stored."""
    key = get_settings().secret_key.encode()
    return hmac.new(key, value.strip().lower().encode(), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
