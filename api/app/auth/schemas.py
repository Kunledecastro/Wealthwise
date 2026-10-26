import uuid
from datetime import datetime
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_TIMEZONES = frozenset(available_timezones())


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RegisterIn(Strict):
    invite_token: str = Field(min_length=20, max_length=128)
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class ForgotIn(Strict):
    email: EmailStr


class ResetIn(Strict):
    token: str = Field(min_length=20, max_length=128)
    new_password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(Strict):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class PreferencesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    timezone: str
    week_start: int
    budget_alert_thresholds: list[int]
    notify_in_app: bool
    notify_email: bool
    ai_enabled: bool
    external_ai_consent: bool


class PreferencesPatch(Strict):
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = None
    week_start: int | None = Field(default=None, ge=1, le=7)
    budget_alert_thresholds: list[int] | None = None
    notify_in_app: bool | None = None
    notify_email: bool | None = None
    ai_enabled: bool | None = None
    external_ai_consent: bool | None = None

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is not None and v not in _TIMEZONES:
            raise ValueError("Unknown timezone.")
        return v

    @field_validator("budget_alert_thresholds")
    @classmethod
    def _thresholds(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if not 1 <= len(v) <= 5:
            raise ValueError("Provide between 1 and 5 thresholds.")
        if any(t < 1 or t > 200 for t in v):
            raise ValueError("Thresholds must be between 1 and 200 percent.")
        if len(set(v)) != len(v):
            raise ValueError("Thresholds must be unique.")
        return sorted(v)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    preferences: PreferencesOut


class CsrfOut(BaseModel):
    csrf_token: str


class MessageOut(BaseModel):
    message: str


class InviteIn(Strict):
    email: EmailStr | None = None
    note: str | None = Field(default=None, max_length=120)


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str | None
    note: str | None
    created_at: datetime
    expires_at: datetime
    status: str


class InviteCreatedOut(InviteOut):
    invite_url: str


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    status: str
    created_at: datetime
    last_login_at: datetime | None


class UserStatusIn(Strict):
    status: str = Field(pattern="^(active|disabled)$")
