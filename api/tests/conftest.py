"""Test harness: real PostgreSQL, real migrations, the real app DB role.

Requires a Postgres test database (default: wealthwise_test on localhost) with the
migrator and app roles created as in docs/TESTING.md or docker compose.
"""

import os

TEST_DB = os.environ.get("TEST_DB_NAME", "wealthwise_test")
PG_HOST = os.environ.get("TEST_PG_HOST", "localhost")
os.environ.update(
    {
        "APP_ENV": "test",
        "APP_BASE_URL": "http://testserver",
        "DATABASE_URL": f"postgresql+psycopg://wealthwise_app:devpass@{PG_HOST}:5432/{TEST_DB}",
        "MIGRATOR_DATABASE_URL": (
            f"postgresql+psycopg://wealthwise_migrator:devpass@{PG_HOST}:5432/{TEST_DB}"
        ),
        "SECRET_KEY": "test-secret-key-not-for-production-0123456789",
        "EMAIL_BACKEND": "console",
        "COOKIE_SECURE": "false",
    }
)

from collections.abc import Iterator  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.auth.service import create_invite, create_user  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402

PASSWORD = "Correct-Horse-7-Battery"
TABLES = (
    "users, user_preferences, sessions, password_reset_tokens, invites, auth_attempts, "
    "accounts, transactions, transaction_revisions, import_batches, import_rows, "
    "import_profiles, reconciliation_points"
)


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> Iterator[None]:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_db() -> Iterator[None]:
    yield
    # The app role cannot truncate audit_events, so clean up as the migrator.
    eng = create_engine(get_settings().migrator_database_url)
    with eng.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES}, audit_events RESTART IDENTITY CASCADE"))
    eng.dispose()


@dataclass
class Api:
    client: TestClient
    csrf: str = ""
    sent: list[dict[str, str]] = field(default_factory=list)

    def refresh_csrf(self) -> None:
        self.csrf = self.client.get("/api/auth/csrf").json()["csrf_token"]

    def _hdr(self) -> dict[str, str]:
        cookie = self.client.cookies.get(get_settings().csrf_cookie_name)
        return {"X-CSRF-Token": cookie or self.csrf}

    def post(self, url: str, json: Any = None, **kw: Any) -> Any:
        return self.client.post(url, json=json, headers={**self._hdr(), **kw.pop("headers", {})})

    def patch(self, url: str, json: Any = None) -> Any:
        return self.client.patch(url, json=json, headers=self._hdr())

    def upload(self, url: str, data: dict[str, str], name: str, content: bytes) -> Any:
        return self.client.post(
            url, data=data, files={"file": (name, content)}, headers=self._hdr()
        )

    def get(self, url: str) -> Any:
        return self.client.get(url)

    def login(self, email: str, password: str = PASSWORD) -> Any:
        return self.post("/api/auth/login", {"email": email, "password": password})


def _new_api(monkeypatch: pytest.MonkeyPatch) -> Api:
    from app.main import app

    api = Api(TestClient(app, base_url="http://testserver"))

    def fake_send(to: str, subject: str, body: str) -> None:
        api.sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr("app.auth.router.send_email", fake_send)
    api.refresh_csrf()
    return api


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Api:
    return _new_api(monkeypatch)


@pytest.fixture
def api_factory(monkeypatch: pytest.MonkeyPatch) -> Any:
    return lambda: _new_api(monkeypatch)


@pytest.fixture
def make_user() -> Any:
    def _make(email: str, role: str = "member", name: str = "Test User") -> int:
        db = get_sessionmaker()()
        try:
            u = create_user(db, email=email, password=PASSWORD, display_name=name, role=role)
            db.commit()
            return u.id
        finally:
            db.close()

    return _make


@pytest.fixture
def make_invite() -> Any:
    def _make(email: str | None = None) -> str:
        db = get_sessionmaker()()
        try:
            _, token = create_invite(db, created_by=None, email=email, note=None)
            db.commit()
            return token
        finally:
            db.close()

    return _make


def db_scalar(sql: str, **params: Any) -> Any:
    eng = create_engine(get_settings().migrator_database_url)
    with eng.connect() as conn:
        value = conn.execute(text(sql), params).scalar()
    eng.dispose()
    return value


def db_exec(sql: str, **params: Any) -> None:
    eng = create_engine(get_settings().migrator_database_url)
    with eng.begin() as conn:
        conn.execute(text(sql), params)
    eng.dispose()
