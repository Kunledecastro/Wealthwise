"""Export, account deletion, email change, admin roles."""

import csv
import io

from tests.conftest import PASSWORD, db_scalar
from tests.test_finance import D, add, new_account


def signed_in(api, make_user, email="d@example.com", role="member"):
    make_user(email, role=role)
    api.login(email)
    return api


# ---------- export ----------


def test_json_export_contains_everything_and_is_audited(api, make_user):
    me = signed_in(api, make_user)
    a = new_account(me)
    t = add(me, a, "expense", 1234, merchant="Chicken Republic")
    gone = add(me, a, "expense", 5)
    me.post(f"/api/transactions/{gone['id']}/delete", {})
    r = me.get("/api/me/export")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["format"] == "wealthwise-export"
    assert data["user"]["email"] == "d@example.com"
    assert [x["id"] for x in data["accounts"]] == [a["id"]]
    assert [x["id"] for x in data["transactions"]] == [t["id"]]
    assert data["deleted_transaction_count"] == 1
    assert {r["action"] for r in data["revisions"]} == {"create", "delete"}
    assert "password_hash" not in r.text
    assert db_scalar("SELECT count(*) FROM audit_events WHERE action='data.export_json'") == 1


def test_csv_export_and_formula_injection_guard(api, make_user):
    me = signed_in(api, make_user)
    a = new_account(me, '=HYPERLINK("http://evil")')
    add(me, a, "expense", 12_500_50, merchant="@SUM(A1:A9)", notes="+cmd|' /C calc'!A0")
    add(me, a, "income", 100)
    r = me.get("/api/transactions/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text.lstrip("﻿"))))
    assert len(rows) == 2
    exp = next(x for x in rows if x["type"] == "expense")
    assert exp["amount"] == "-12500.50" and exp["amount_minor"] == "1250050"
    assert exp["merchant"].startswith("'@") and exp["notes"].startswith("'+")
    assert exp["account"].startswith("'=")


# ---------- email change ----------


def test_change_email(api_factory, make_user):
    make_user("old@example.com")
    other_device = api_factory()
    other_device.login("old@example.com")
    me = api_factory()
    me.login("old@example.com")
    bad = me.post("/api/me/email", {"new_email": "new@example.com", "password": "wrong-wrong-1"})
    assert bad.status_code == 400
    r = me.post("/api/me/email", {"new_email": "New@Example.com", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["email"].lower() == "new@example.com"
    assert other_device.get("/api/me").status_code == 401  # other sessions signed out
    me.post("/api/auth/logout")
    assert me.login("old@example.com").status_code == 401
    assert me.login("new@example.com").status_code == 200
    # the audit trail records the change but not the addresses
    details = db_scalar(
        "SELECT details::text FROM audit_events WHERE action='account.email_changed'"
    )
    assert "example.com" not in details


def test_change_email_rejects_taken_and_invalid(api, make_user):
    make_user("taken@example.com")
    me = signed_in(api, make_user, "e@example.com")
    assert (
        me.post(
            "/api/me/email", {"new_email": "taken@example.com", "password": PASSWORD}
        ).status_code
        == 409
    )
    assert (
        me.post("/api/me/email", {"new_email": "x@example.local", "password": PASSWORD}).status_code
        == 422
    )


# ---------- delete account ----------


def test_delete_account_removes_all_data(api, make_user):
    make_user("admin@example.com", role="admin")  # so the member isn't the last admin
    me = signed_in(api, make_user, "bye@example.com")
    a = new_account(me)
    add(me, a)
    assert me.post("/api/me/delete", {"password": PASSWORD, "confirm": "delete"}).status_code == 400
    assert (
        me.post("/api/me/delete", {"password": "nope-nope-1", "confirm": "DELETE"}).status_code
        == 400
    )
    r = me.post("/api/me/delete", {"password": PASSWORD, "confirm": "DELETE"})
    assert r.status_code == 200
    assert me.get("/api/me").status_code == 401
    for table in ("accounts", "transactions", "transaction_revisions", "sessions"):
        assert db_scalar(f"SELECT count(*) FROM {table}") == 0, table  # noqa: S608
    # only the other (admin) user's preferences remain
    assert db_scalar("SELECT count(*) FROM user_preferences") == 1
    assert db_scalar("SELECT count(*) FROM users WHERE email='bye@example.com'") == 0
    assert (
        db_scalar("SELECT count(*) FROM audit_events WHERE action='account.deleted_by_user'") == 1
    )
    assert me.login("bye@example.com").status_code == 401


def test_last_admin_cannot_delete_self(api, make_user):
    me = signed_in(api, make_user, "solo@example.com", role="admin")
    r = me.post("/api/me/delete", {"password": PASSWORD, "confirm": "DELETE"})
    assert r.status_code == 409


def test_admin_can_promote_and_then_delete_self(api_factory, make_user):
    make_user("boss@example.com", role="admin")
    make_user("next@example.com")
    boss = api_factory()
    boss.login("boss@example.com")
    uid = next(
        u["id"] for u in boss.get("/api/admin/users").json() if u["email"] == "next@example.com"
    )
    assert boss.post(f"/api/admin/users/{uid}/role", {"role": "admin"}).status_code == 200
    me_id = next(
        u["id"] for u in boss.get("/api/admin/users").json() if u["email"] == "boss@example.com"
    )
    assert boss.post(f"/api/admin/users/{me_id}/role", {"role": "member"}).status_code == 400
    assert (
        boss.post("/api/me/delete", {"password": PASSWORD, "confirm": "DELETE"}).status_code == 200
    )


def test_password_checks_are_rate_limited(api, make_user):
    me = signed_in(api, make_user, "rl@example.com")
    for _ in range(5):
        me.post("/api/me/email", {"new_email": "z@example.com", "password": "wrong-wrong-1"})
    r = me.post("/api/me/email", {"new_email": "z@example.com", "password": PASSWORD})
    assert r.status_code == 429


def test_unused_import_guard():
    assert D  # imported helpers are shared with test_finance
