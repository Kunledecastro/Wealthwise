from tests.conftest import PASSWORD, db_exec, db_scalar


def test_health(api):
    r = api.get("/api/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


# ---------- registration (invite-only) ----------


def test_register_with_invite_sets_defaults_and_signs_in(api, make_invite):
    token = make_invite()
    r = api.post(
        "/api/auth/register",
        {
            "invite_token": token,
            "email": "ada@example.com",
            "display_name": "Ada",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["preferences"]["currency"] == "NGN"
    assert body["preferences"]["timezone"] == "Africa/Lagos"
    assert body["role"] == "member"
    assert api.get("/api/me").status_code == 200


def test_register_without_valid_invite_rejected(api):
    r = api.post(
        "/api/auth/register",
        {
            "invite_token": "x" * 43,
            "email": "a@example.com",
            "display_name": "A",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 400


def test_invite_is_single_use(api_factory, make_invite):
    token = make_invite()
    a = api_factory()
    assert (
        a.post(
            "/api/auth/register",
            {
                "invite_token": token,
                "email": "one@example.com",
                "display_name": "One",
                "password": PASSWORD,
            },
        ).status_code
        == 201
    )
    b = api_factory()
    r = b.post(
        "/api/auth/register",
        {
            "invite_token": token,
            "email": "two@example.com",
            "display_name": "Two",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 400


def test_invite_bound_to_email(api, make_invite):
    token = make_invite(email="invited@example.com")
    r = api.post(
        "/api/auth/register",
        {
            "invite_token": token,
            "email": "other@example.com",
            "display_name": "X",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 400


def test_weak_password_rejected(api, make_invite):
    token = make_invite()
    for weak in ["short", "password123", "aaaaaaaaaaaa"]:
        r = api.post(
            "/api/auth/register",
            {
                "invite_token": token,
                "email": "w@example.com",
                "display_name": "W",
                "password": weak,
            },
        )
        assert r.status_code == 422, weak
    # invite still usable after failed attempts
    assert (
        api.post(
            "/api/auth/register",
            {
                "invite_token": token,
                "email": "w@example.com",
                "display_name": "W",
                "password": PASSWORD,
            },
        ).status_code
        == 201
    )


def test_registration_closed_mode(api, make_invite, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "registration_mode", "closed")
    r = api.post(
        "/api/auth/register",
        {
            "invite_token": make_invite(),
            "email": "c@example.com",
            "display_name": "C",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 403


# ---------- login / sessions ----------


def test_password_stored_as_argon2id(make_user):
    make_user("h@example.com")
    h = db_scalar("SELECT password_hash FROM users WHERE email='h@example.com'")
    assert h.startswith("$argon2id$")
    assert PASSWORD not in h


def test_login_success_and_cookie_flags(api, make_user):
    make_user("bola@example.com")
    r = api.login("bola@example.com")
    assert r.status_code == 200
    cookie = next(h for h in r.headers.get_list("set-cookie") if h.startswith("ww_session="))
    low = cookie.lower()
    assert "httponly" in low and "samesite=lax" in low and "path=/" in low
    assert api.get("/api/me").json()["email"] == "bola@example.com"


def test_secure_cookie_when_configured(api, make_user, monkeypatch):
    from app.core.config import get_settings

    make_user("sec@example.com")
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    api.client.cookies.set("__Host-ww_csrf", "t")
    r = api.client.post(
        "/api/auth/login",
        json={"email": "sec@example.com", "password": PASSWORD},
        headers={"X-CSRF-Token": "t"},
    )
    assert r.status_code == 200
    cookie = next(h for h in r.headers.get_list("set-cookie") if h.startswith("__Host-ww_session"))
    assert "secure" in cookie.lower()


def test_login_errors_are_generic(api, make_user):
    make_user("known@example.com")
    a = api.login("known@example.com", "Wrong-password-123")
    b = api.login("unknown@example.com", "Wrong-password-123")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_disabled_user_cannot_login(api, make_user):
    make_user("off@example.com")
    db_exec("UPDATE users SET status='disabled' WHERE email='off@example.com'")
    assert api.login("off@example.com").status_code == 401


def test_lockout_after_max_failed_attempts(api, make_user):
    make_user("lock@example.com")
    for _ in range(5):
        assert api.login("lock@example.com", "Wrong-password-123").status_code == 401
    r = api.login("lock@example.com", "Wrong-password-123")
    assert r.status_code == 429
    # even the right password is refused during lockout
    assert api.login("lock@example.com").status_code == 429


def test_successful_login_resets_failure_count(api, make_user):
    make_user("reset@example.com")
    for _ in range(4):
        api.login("reset@example.com", "Wrong-password-123")
    assert api.login("reset@example.com").status_code == 200
    for _ in range(4):
        assert api.login("reset@example.com", "Wrong-password-123").status_code == 401


def test_login_rotates_session(api, make_user):
    make_user("rot@example.com")
    api.login("rot@example.com")
    first = api.client.cookies.get("ww_session")
    api.login("rot@example.com")
    second = api.client.cookies.get("ww_session")
    assert first != second
    assert db_scalar("SELECT count(*) FROM sessions WHERE revoked_at IS NULL") == 1


def test_logout_invalidates_session_server_side(api, make_user):
    make_user("out@example.com")
    api.login("out@example.com")
    token = api.client.cookies.get("ww_session")
    assert api.post("/api/auth/logout").status_code == 200
    api.client.cookies.set("ww_session", token)  # replaying the old cookie must fail
    assert api.get("/api/me").status_code == 401


def test_logout_all_devices(api_factory, make_user):
    make_user("many@example.com")
    phone, laptop = api_factory(), api_factory()
    phone.login("many@example.com")
    laptop.login("many@example.com")
    assert laptop.post("/api/auth/logout-all").status_code == 200
    assert phone.get("/api/me").status_code == 401


def test_idle_timeout(api, make_user):
    make_user("idle@example.com")
    api.login("idle@example.com")
    db_exec("UPDATE sessions SET last_seen_at = now() - interval '31 minutes'")
    assert api.get("/api/me").status_code == 401


def test_absolute_expiry(api, make_user):
    make_user("abs@example.com")
    api.login("abs@example.com")
    db_exec("UPDATE sessions SET expires_at = now() - interval '1 second'")
    assert api.get("/api/me").status_code == 401


# ---------- password reset / change ----------


def _reset_token(api) -> str:
    body = api.sent[-1]["body"]
    return body.split("#token=")[1].split()[0]


def test_forgot_password_same_response_for_unknown_email(api, make_user):
    make_user("fp@example.com")
    a = api.post("/api/auth/password/forgot", {"email": "fp@example.com"})
    b = api.post("/api/auth/password/forgot", {"email": "nobody@example.com"})
    assert a.status_code == b.status_code == 202
    assert a.json() == b.json()
    assert len(api.sent) == 1 and api.sent[0]["to"] == "fp@example.com"


def test_password_reset_flow(api_factory, make_user):
    make_user("rp@example.com")
    other_device = api_factory()
    other_device.login("rp@example.com")

    api = api_factory()
    api.post("/api/auth/password/forgot", {"email": "rp@example.com"})
    token = _reset_token(api)
    new = "Brand-New-Passphrase-42"
    r = api.post("/api/auth/password/reset", {"token": token, "new_password": new})
    assert r.status_code == 200
    # token is single use
    assert (
        api.post(
            "/api/auth/password/reset", {"token": token, "new_password": "Another-Passphrase-43"}
        ).status_code
        == 400
    )
    # all sessions revoked, old password dead, new password works
    assert other_device.get("/api/me").status_code == 401
    assert api.login("rp@example.com").status_code == 401
    assert api.login("rp@example.com", new).status_code == 200


def test_expired_reset_token_rejected(api, make_user):
    make_user("exp@example.com")
    api.post("/api/auth/password/forgot", {"email": "exp@example.com"})
    db_exec("UPDATE password_reset_tokens SET expires_at = now() - interval '1 minute'")
    r = api.post(
        "/api/auth/password/reset",
        {"token": _reset_token(api), "new_password": "Brand-New-Passphrase-42"},
    )
    assert r.status_code == 400


def test_newer_reset_link_invalidates_older(api, make_user):
    make_user("two@example.com")
    api.post("/api/auth/password/forgot", {"email": "two@example.com"})
    old = _reset_token(api)
    api.post("/api/auth/password/forgot", {"email": "two@example.com"})
    r = api.post("/api/auth/password/reset", {"token": old, "new_password": "Brand-New-Pass-42x"})
    assert r.status_code == 400


def test_forgot_password_rate_limited(api, make_user):
    make_user("spam@example.com")
    for _ in range(3):
        assert (
            api.post("/api/auth/password/forgot", {"email": "spam@example.com"}).status_code == 202
        )
    assert api.post("/api/auth/password/forgot", {"email": "spam@example.com"}).status_code == 429


def test_change_password_signs_out_other_devices(api_factory, make_user):
    make_user("chg@example.com")
    other = api_factory()
    other.login("chg@example.com")
    me = api_factory()
    me.login("chg@example.com")
    bad = me.post(
        "/api/auth/password/change",
        {"current_password": "nope-nope-nope", "new_password": "Brand-New-Pass-42x"},
    )
    assert bad.status_code == 400
    ok = me.post(
        "/api/auth/password/change",
        {"current_password": PASSWORD, "new_password": "Brand-New-Pass-42x"},
    )
    assert ok.status_code == 200
    assert me.get("/api/me").status_code == 200
    assert other.get("/api/me").status_code == 401


def test_create_user_rejects_emails_login_would_reject():
    """Regression: CLI-created accounts must be able to sign in."""
    import pytest
    from fastapi import HTTPException

    from app.auth.service import create_user
    from app.db.session import get_sessionmaker

    db = get_sessionmaker()()
    try:
        with pytest.raises(HTTPException) as exc:
            create_user(db, email="admin@wealthwise.local", password=PASSWORD, display_name="A")
        assert exc.value.status_code == 422
    finally:
        db.close()
