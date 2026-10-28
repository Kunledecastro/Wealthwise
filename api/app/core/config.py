from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Wealthwise"
    app_env: Literal["development", "test", "production"] = "development"
    app_base_url: str = "http://localhost:3000"
    default_currency: str = "NGN"
    default_timezone: str = "Africa/Lagos"
    demo_mode: bool = False
    upload_max_mb: int = Field(default=10, ge=1, le=50)

    database_url: str = "postgresql+psycopg://wealthwise_app:devpass@localhost:5432/wealthwise"
    migrator_database_url: str = (
        "postgresql+psycopg://wealthwise_migrator:devpass@localhost:5432/wealthwise"
    )

    secret_key: str = Field(default="dev-insecure-secret-change-me", min_length=16)
    session_idle_minutes: int = 30
    session_absolute_days: int = 7
    cookie_secure: bool = False
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    ip_max_failed_attempts: int = 30
    invite_valid_days: int = 7
    password_reset_valid_minutes: int = 30
    registration_mode: Literal["invite_only", "open", "closed"] = "invite_only"

    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "no-reply@example.com"

    log_level: str = "INFO"
    log_redact_financial: bool = True

    @property
    def session_cookie_name(self) -> str:
        # __Host- prefix requires Secure, Path=/ and no Domain; only valid over HTTPS.
        return "__Host-ww_session" if self.cookie_secure else "ww_session"

    @property
    def csrf_cookie_name(self) -> str:
        return "__Host-ww_csrf" if self.cookie_secure else "ww_csrf"

    def validate_for_production(self) -> None:
        if self.app_env != "production":
            return
        problems = []
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true")
        if self.secret_key.startswith("dev-") or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be a random value of at least 32 characters")
        if not self.app_base_url.startswith("https://"):
            problems.append("APP_BASE_URL must use https")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
