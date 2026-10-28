import logging

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from app.core.config import get_settings
from app.core.logging import redact_text
from tests.conftest import PASSWORD, db_scalar

# ---------- CSRF ----------


def test_state_change_without_csrf_token_rejected(api, make_user):
    make_user("c@example.com")
    r = api.client.post("/api/auth/login", json={"email": "c@example.com", "password": PASSWORD})
    assert r.status_code == 403


def test_csrf_token_mismatch_rejected(api, make_user):
    make_user("c2@example.com")
    r = api.client.post(
        "/api/auth/login",
        json={"email": "c2@example.com", "password": PASSWORD},
        headers={"X-CSRF-Token": "not-the-cookie-value"},
    )
    assert r.status_code == 403


def test_cross_origin_rejected_even_with_token(api, make_user):
    make_user("c3@example.com")
    r = api.post(
        "/api/auth/login",
        {"email": "c3@example.com", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403
    ok = api.post(
        "/api/auth/login",
        {"email": "c3@example.com", "password": PASSWORD},
        headers={"Origin": "http://testserver"},
    )
    assert ok.status_code == 200


# ---------- authorisation ----------

# Everything else under /api requires a signed-in user. New routes are protected by
# default in this test: making one public requires adding it here deliberately.
PUBLIC = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/csrf"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/password/forgot"),
    ("POST", "/api/auth/password/reset"),
}


def _all_routes():
    from app.main import app

    return sorted(
        (method.upper(), path) for path, ops in app.openapi()["paths"].items() for method in ops
    )


def test_route_listing_works():
    routes = _all_routes()
    assert len(routes) > 20
    assert set(routes) >= PUBLIC, "a PUBLIC entry no longer exists"


@pytest.mark.parametrize(("method", "path"), [r for r in _all_routes() if r not in PUBLIC])
def test_every_non_public_route_rejects_anonymous(api, method, path):
    url = path
    for param in ("{invite_id}", "{user_id}", "{account_id}", "{txn_id}", "{batch_id}"):
        url = url.replace(param, "00000000-0000-4000-8000-000000000000")
    assert "{" not in url, f"add a placeholder for {path}"
    hdr = {"X-CSRF-Token": api.client.cookies.get("ww_csrf")}
    r = api.client.request(method, url, json={}, headers=hdr)
    assert r.status_code == 401, (method, path, r.status_code)


def test_users_only_see_and_change_their_own_preferences(api_factory, make_user):
    make_user("a@example.com")
    make_user("b@example.com")
    a, b = api_factory(), api_factory()
    a.login("a@example.com")
    b.login("b@example.com")
    assert a.patch("/api/me/preferences", {"timezone": "Europe/London"}).status_code == 200
    assert b.get("/api/me/preferences").json()["timezone"] == "Africa/Lagos"
    assert a.get("/api/me").json()["email"] == "a@example.com"
    assert b.get("/api/me").json()["email"] == "b@example.com"


def test_preferences_reject_unknown_fields(api, make_user):
    make_user("x@example.com")
    api.login("x@example.com")
    # e.g. attempting to smuggle a user id or role
    assert api.patch("/api/me/preferences", {"user_id": 1}).status_code == 422
    assert api.patch("/api/me/preferences", {"role": "admin"}).status_code == 422


def test_member_cannot_use_admin_endpoints(api, make_user):
    make_user("m@example.com")
    api.login("m@example.com")
    assert api.get("/api/admin/users").status_code == 404
    assert api.post("/api/admin/invites", {}).status_code == 404


def test_admin_invite_lifecycle(api_factory, make_user):
    make_user("boss@example.com", role="admin")
    admin = api_factory()
    admin.login("boss@example.com")
    r = admin.post("/api/admin/invites", {"email": "new@example.com", "note": "Ada"})
    assert r.status_code == 201
    url = r.json()["invite_url"]
    assert url.startswith("http://testserver/register#invite=")
    # raw token is never stored
    assert url.split("=")[1] not in str(db_scalar("SELECT token_hash FROM invites"))
    listed = admin.get("/api/admin/invites").json()
    assert "invite_url" not in listed[0] and listed[0]["status"] == "pending"

    joiner = api_factory()
    reg = joiner.post(
        "/api/auth/register",
        {
            "invite_token": url.split("=")[1],
            "email": "new@example.com",
            "display_name": "Ada",
            "password": PASSWORD,
        },
    )
    assert reg.status_code == 201
    assert admin.get("/api/admin/invites").json()[0]["status"] == "used"


def test_admin_can_disable_user_and_their_sessions_end(api_factory, make_user):
    make_user("boss2@example.com", role="admin")
    make_user("u@example.com")
    admin, user = api_factory(), api_factory()
    admin.login("boss2@example.com")
    user.login("u@example.com")
    uid = next(
        u["id"] for u in admin.get("/api/admin/users").json() if u["email"] == "u@example.com"
    )
    assert admin.post(f"/api/admin/users/{uid}/status", {"status": "disabled"}).status_code == 200
    assert user.get("/api/me").status_code == 401


# ---------- audit ----------


def test_audit_events_written(api, make_user):
    make_user("aud@example.com")
    api.login("aud@example.com", "Wrong-password-123")
    api.login("aud@example.com")
    api.patch("/api/me/preferences", {"week_start": 7})
    api.post("/api/auth/logout")
    actions = db_scalar("SELECT string_agg(action, ',' ORDER BY id) FROM audit_events")
    assert actions == "auth.login_failed,auth.login,preferences.update,auth.logout"


def test_app_role_cannot_alter_audit_trail():
    eng = create_engine(get_settings().database_url)
    for stmt in ("DELETE FROM audit_events", "UPDATE audit_events SET action='x'"):
        with eng.connect() as conn, pytest.raises(ProgrammingError):
            conn.execute(text(stmt))
    eng.dispose()


# ---------- logging & response hygiene ----------


def test_logs_do_not_contain_credentials(api, make_user, caplog):
    make_user("secret.person@example.com")
    with caplog.at_level(logging.DEBUG):
        api.login("secret.person@example.com", "Wrong-password-123")
        api.login("secret.person@example.com")
    text_out = "\n".join(r.getMessage() for r in caplog.records)
    assert "secret.person@example.com" not in text_out
    assert PASSWORD not in text_out
    assert "Wrong-password-123" not in text_out


def test_redaction_rules():
    s = redact_text("user ada@example.com acct 0123456789 tok " + "A" * 43)
    assert "ada@example.com" not in s and "0123456789" not in s and "A" * 43 not in s


def test_validation_errors_do_not_echo_input(api):
    r = api.post("/api/auth/login", {"email": "not-an-email", "password": "Sup3r$ecretValue"})
    assert r.status_code == 422
    assert "Sup3r$ecretValue" not in r.text and "not-an-email" not in r.text


def test_security_headers(api):
    r = api.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_production_config_guard(monkeypatch):
    from app.core.config import Settings

    s = Settings(app_env="production", cookie_secure=False, secret_key="dev-short-secret-x")
    with pytest.raises(RuntimeError):
        s.validate_for_production()
