"""Accounts, transactions, transfers, reversals, summary: API behaviour and data isolation."""

from datetime import date, timedelta

import pytest

from tests.conftest import db_exec, db_scalar

TODAY = date.today()
D = (TODAY - timedelta(days=3)).isoformat()


@pytest.fixture
def me(api, make_user):
    make_user("owner@example.com")
    api.login("owner@example.com")
    return api


def new_account(api, name="GTBank", opening=100_000_00, type_="bank", **kw):
    body = {
        "type": type_,
        "display_name": name,
        "opening_balance_minor": opening,
        "opening_balance_date": (TODAY - timedelta(days=30)).isoformat(),
        **kw,
    }
    r = api.post("/api/accounts", body)
    assert r.status_code == 201, r.text
    return r.json()


def add(api, account, kind="expense", amount=1000, status="posted", **kw):
    body = {
        "account_id": account["id"],
        "kind": kind,
        "amount_minor": amount,
        "status": status,
        "transaction_date": D,
        **kw,
    }
    r = api.post("/api/transactions", body)
    assert r.status_code == 201, r.text
    return r.json()


def balance(api, account):
    return api.get(f"/api/accounts/{account['id']}").json()["balance"]


def summary(api, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return api.get(f"/api/ledger/summary?{q}").json()


# ---------------- accounts ----------------


def test_create_account_is_manual_and_estimated(me):
    a = new_account(me, mask="1234", institution_name="Guaranty Trust")
    assert a["source"] == "manual"
    assert a["currency"] == "NGN"
    assert a["balance"]["status"] == "estimated"
    assert a["balance"]["posted_minor"] == 100_000_00
    assert a["mask"] == "1234"


@pytest.mark.parametrize(
    "bad",
    [
        {"mask": "12345"},
        {"mask": "12ab"},
        {"type": "crypto"},
        {"currency": "USD"},  # not enabled yet
        {"opening_balance_minor": 10**16},
        {"opening_balance_date": (TODAY + timedelta(days=5)).isoformat()},
        {"source": "connected"},  # clients can never claim a live bank connection
    ],
)
def test_account_validation(me, bad):
    body = {
        "type": "bank",
        "display_name": "X",
        "opening_balance_minor": 0,
        "opening_balance_date": TODAY.isoformat(),
        **bad,
    }
    assert me.post("/api/accounts", body).status_code == 422


def test_negative_opening_balance_for_card(me):
    a = new_account(me, "Card", opening=-25_000_00, type_="card")
    assert a["balance"]["posted_minor"] == -25_000_00


def test_archive_hides_account_and_blocks_new_transactions(me):
    a = new_account(me)
    assert me.patch(f"/api/accounts/{a['id']}", {"is_archived": True}).status_code == 200
    assert me.get("/api/accounts").json() == []
    assert len(me.get("/api/accounts?include_archived=true").json()) == 1
    r = me.post(
        "/api/transactions",
        {"account_id": a["id"], "kind": "expense", "amount_minor": 1, "transaction_date": D},
    )
    assert r.status_code == 422


def test_delete_account_only_when_never_used(me):
    a = new_account(me)
    b = new_account(me, "Cash", type_="cash")
    add(me, b)
    assert (
        me.client.delete(
            f"/api/accounts/{b['id']}", headers={"X-CSRF-Token": me._hdr()["X-CSRF-Token"]}
        ).status_code
        == 422
    )
    assert (
        me.client.delete(
            f"/api/accounts/{a['id']}", headers={"X-CSRF-Token": me._hdr()["X-CSRF-Token"]}
        ).status_code
        == 204
    )


def test_opening_balance_edit_is_audited(me):
    a = new_account(me)
    me.patch(f"/api/accounts/{a['id']}", {"opening_balance_minor": 5})
    assert db_scalar("SELECT count(*) FROM audit_events WHERE action='account.updated'") == 1
    assert balance(me, a)["posted_minor"] == 5


# ---------------- transactions & ledger rules end-to-end ----------------


def test_expense_and_income_update_balance_and_summary(me):
    a = new_account(me)
    add(me, a, "income", 250_000_00, merchant="Employer")
    add(me, a, "expense", 12_500_50, merchant="Shoprite")
    add(me, a, "fee", 52_50, narration="SMS alert")
    assert balance(me, a)["posted_minor"] == 100_000_00 + 250_000_00 - 12_500_50 - 52_50
    s = summary(me, date_from=D, date_to=D)["summaries"][0]
    assert (s["income"], s["gross_spending"], s["fees"]) == (250_000_00, 12_553_00, 52_50)
    assert s["net_cash_flow"] == 250_000_00 - 12_553_00


def test_direction_is_set_by_server(me):
    a = new_account(me)
    t = add(me, a, "income", 10)
    assert t["direction"] == "credit"
    r = me.post(
        "/api/transactions",
        {
            "account_id": a["id"],
            "kind": "expense",
            "direction": "credit",
            "amount_minor": 1,
            "transaction_date": D,
        },
    )
    assert r.status_code == 422


def test_adjustment_requires_direction_and_skips_pnl(me):
    a = new_account(me)
    r = me.post(
        "/api/transactions",
        {"account_id": a["id"], "kind": "adjustment", "amount_minor": 1, "transaction_date": D},
    )
    assert r.status_code == 422
    add(me, a, "adjustment", 300, direction="debit")
    assert balance(me, a)["posted_minor"] == 100_000_00 - 300
    s = summary(me, date_from=D, date_to=D)["summaries"]
    assert s == [] or (s[0]["income"], s[0]["gross_spending"]) == (0, 0)


@pytest.mark.parametrize("amount", [0, -1, 10**16, 1.5, "100"])
def test_amount_validation(me, amount):
    a = new_account(me)
    r = me.post(
        "/api/transactions",
        {"account_id": a["id"], "kind": "expense", "amount_minor": amount, "transaction_date": D},
    )
    assert r.status_code == 422


def test_posting_date_before_transaction_date_rejected(me):
    a = new_account(me)
    r = me.post(
        "/api/transactions",
        {
            "account_id": a["id"],
            "kind": "expense",
            "amount_minor": 1,
            "transaction_date": D,
            "posting_date": (TODAY - timedelta(days=10)).isoformat(),
        },
    )
    assert r.status_code == 422


def test_pending_then_posted(me):
    a = new_account(me)
    t = add(me, a, "expense", 5000, status="pending")
    b = balance(me, a)
    assert b["posted_minor"] == 100_000_00
    assert b["available_incl_pending"] == 100_000_00 - 5000
    s = summary(me, date_from=D, date_to=D)["summaries"][0]
    assert (s["gross_spending"], s["pending_out"]) == (0, 5000)
    r = me.patch(f"/api/transactions/{t['id']}", {"status": "posted"})
    assert r.status_code == 200 and r.json()["posting_date"] == D
    assert balance(me, a)["posted_minor"] == 100_000_00 - 5000


def test_failed_never_counts(me):
    a = new_account(me)
    add(me, a, "expense", 5000, status="failed")
    assert balance(me, a)["available_incl_pending"] == 100_000_00
    s = summary(me, date_from=D, date_to=D)["summaries"]
    assert s == [] or s[0]["gross_spending"] == 0


def test_refund_reduces_spending(me):
    a = new_account(me)
    buy = add(me, a, "expense", 20_000_00, merchant="Jumia")
    r = add(me, a, "refund", 5_000_00, merchant="Jumia", refund_of_id=buy["id"])
    assert r["refund_of_id"] == buy["id"]
    s = summary(me, date_from=D, date_to=D)["summaries"][0]
    assert (s["income"], s["net_spending"]) == (0, 15_000_00)


def test_refund_can_only_link_to_expense_or_fee(me):
    a = new_account(me)
    inc = add(me, a, "income", 100)
    r = me.post(
        "/api/transactions",
        {
            "account_id": a["id"],
            "kind": "refund",
            "amount_minor": 1,
            "transaction_date": D,
            "refund_of_id": inc["id"],
        },
    )
    assert r.status_code == 422


def test_transfer_two_legs_atomic_and_not_pnl(me):
    a = new_account(me, "GTBank", 100_000_00)
    b = new_account(me, "Kuda", 0, type_="wallet")
    r = me.post(
        "/api/transactions/transfers",
        {
            "from_account_id": a["id"],
            "to_account_id": b["id"],
            "amount_minor": 40_000_00,
            "transaction_date": D,
        },
    )
    assert r.status_code == 201, r.text
    tr = r.json()
    assert tr["debit"]["counterpart_account_name"] == "Kuda"
    assert balance(me, a)["posted_minor"] == 60_000_00
    assert balance(me, b)["posted_minor"] == 40_000_00
    s = summary(me, date_from=D, date_to=D)
    assert s["balance_totals"] == {"NGN": 100_000_00}
    assert s["summaries"] == [] or s["summaries"][0]["net_cash_flow"] == 0


def test_transfer_validation(me):
    a = new_account(me)
    same = me.post(
        "/api/transactions/transfers",
        {
            "from_account_id": a["id"],
            "to_account_id": a["id"],
            "amount_minor": 1,
            "transaction_date": D,
        },
    )
    assert same.status_code == 422


def test_editing_a_transfer_updates_both_legs(me):
    a, b = new_account(me), new_account(me, "Kuda", 0)
    tr = me.post(
        "/api/transactions/transfers",
        {
            "from_account_id": a["id"],
            "to_account_id": b["id"],
            "amount_minor": 1000,
            "transaction_date": D,
        },
    ).json()
    r = me.patch(f"/api/transactions/{tr['credit']['id']}", {"amount_minor": 2500})
    assert r.status_code == 200
    assert balance(me, a)["posted_minor"] == 100_000_00 - 2500
    assert balance(me, b)["posted_minor"] == 2500
    bad = me.patch(f"/api/transactions/{tr['debit']['id']}", {"account_id": b["id"]})
    assert bad.status_code == 422


def test_deleting_a_transfer_deletes_both_legs(me):
    a, b = new_account(me), new_account(me, "Kuda", 0)
    tr = me.post(
        "/api/transactions/transfers",
        {
            "from_account_id": a["id"],
            "to_account_id": b["id"],
            "amount_minor": 1000,
            "transaction_date": D,
        },
    ).json()
    r = me.post(f"/api/transactions/{tr['debit']['id']}/delete", {})
    assert r.status_code == 200 and len(r.json()) == 2
    assert balance(me, a)["posted_minor"] == 100_000_00
    assert balance(me, b)["posted_minor"] == 0


def test_edit_creates_revision_history(me):
    a = new_account(me)
    t = add(me, a, "expense", 1000, merchant="Bolt")
    me.patch(f"/api/transactions/{t['id']}", {"amount_minor": 1500, "reason": "typo"})
    me.patch(f"/api/transactions/{t['id']}", {"amount_minor": 1500})  # no-op: no revision
    detail = me.get(f"/api/transactions/{t['id']}").json()
    assert [r["action"] for r in detail["revisions"]] == ["create", "update"]
    assert detail["revisions"][1]["changes"] == {"amount_minor": [1000, 1500]}
    assert detail["revisions"][1]["reason"] == "typo"


def test_change_kind_recomputes_direction(me):
    a = new_account(me)
    t = add(me, a, "expense", 1000)
    r = me.patch(f"/api/transactions/{t['id']}", {"kind": "income"})
    assert r.json()["direction"] == "credit"
    assert balance(me, a)["posted_minor"] == 100_000_00 + 1000


def test_soft_delete_excluded_but_audited(me):
    a = new_account(me)
    t = add(me, a, "expense", 1000)
    assert (
        me.post(f"/api/transactions/{t['id']}/delete", {"reason": "duplicate"}).status_code == 200
    )
    assert balance(me, a)["posted_minor"] == 100_000_00
    assert me.get("/api/transactions").json()["total"] == 0
    assert me.get(f"/api/transactions/{t['id']}").status_code == 404
    assert db_scalar("SELECT count(*) FROM transactions WHERE deleted_at IS NOT NULL") == 1
    assert (
        db_scalar("SELECT action FROM transaction_revisions ORDER BY id DESC LIMIT 1") == "delete"
    )


def test_reverse_cancels_out_and_locks(me):
    a = new_account(me)
    t = add(me, a, "expense", 7000, merchant="Netflix")
    r = me.post(f"/api/transactions/{t['id']}/reverse", {"reason": "bank reversed"})
    assert r.status_code == 201, r.text
    rev = r.json()
    assert rev["kind"] == "reversal" and rev["direction"] == "credit"
    assert balance(me, a)["posted_minor"] == 100_000_00
    s = summary(me, date_from=D, date_to=TODAY.isoformat())["summaries"]
    assert s == [] or s[0]["gross_spending"] == 0
    orig = me.get(f"/api/transactions/{t['id']}").json()
    assert orig["status"] == "reversed" and orig["reversed_by_id"] == rev["id"]
    assert me.patch(f"/api/transactions/{t['id']}", {"amount_minor": 1}).status_code == 422
    assert me.patch(f"/api/transactions/{t['id']}", {"notes": "ok"}).status_code == 200
    assert me.post(f"/api/transactions/{t['id']}/reverse", {}).status_code == 422


def test_deleting_reversal_restores_original(me):
    a = new_account(me)
    t = add(me, a, "expense", 7000)
    rev = me.post(f"/api/transactions/{t['id']}/reverse", {}).json()
    me.post(f"/api/transactions/{rev['id']}/delete", {})
    assert me.get(f"/api/transactions/{t['id']}").json()["status"] == "posted"
    assert balance(me, a)["posted_minor"] == 100_000_00 - 7000


def test_only_posted_can_be_reversed(me):
    a = new_account(me)
    t = add(me, a, "expense", 7000, status="pending")
    assert me.post(f"/api/transactions/{t['id']}/reverse", {}).status_code == 422


def test_transactions_before_opening_date_excluded_from_balance(me):
    a = new_account(me)
    add(me, a, "expense", 999, transaction_date=(TODAY - timedelta(days=60)).isoformat())
    assert balance(me, a)["posted_minor"] == 100_000_00


# ---------------- list, filter, search ----------------


def test_list_filters_search_and_pagination(me):
    a, b = new_account(me), new_account(me, "Cash", 0, type_="cash")
    for i in range(7):
        add(me, a, "expense", 100 + i, merchant=f"Shop {i}")
    add(me, b, "income", 50, merchant="Gift 100%")
    add(me, a, "fee", 10, status="pending")
    page1 = me.get("/api/transactions?page_size=4").json()
    assert page1["total"] == 9 and len(page1["items"]) == 4
    assert len(me.get("/api/transactions?page_size=4&page=3").json()["items"]) == 1
    assert me.get(f"/api/transactions?account_id={b['id']}").json()["total"] == 1
    assert me.get("/api/transactions?kind=fee&kind=income").json()["total"] == 2
    assert me.get("/api/transactions?status=pending").json()["total"] == 1
    assert me.get("/api/transactions?q=shop%203").json()["total"] == 1
    # % is matched literally, not as a wildcard
    assert me.get("/api/transactions?q=100%25").json()["total"] == 1
    assert me.get("/api/transactions?min_amount=105").json()["total"] == 2
    assert me.get("/api/transactions?page_size=500").status_code == 422


def test_summary_defaults_to_current_month(me):
    s = summary(me)
    assert s["date_from"] == TODAY.replace(day=1).isoformat()
    assert s["timezone"] == "Africa/Lagos"
    assert s["balances_are_estimated"] is True


# ---------------- isolation ----------------


def test_users_cannot_see_or_touch_each_others_data(api_factory, make_user):
    make_user("a@example.com")
    make_user("b@example.com")
    alice, bob = api_factory(), api_factory()
    alice.login("a@example.com")
    bob.login("b@example.com")
    acct = new_account(alice)
    t = add(alice, acct)

    assert bob.get("/api/accounts").json() == []
    assert bob.get("/api/transactions").json()["total"] == 0
    assert bob.get(f"/api/accounts/{acct['id']}").status_code == 404
    assert bob.get(f"/api/transactions/{t['id']}").status_code == 404
    assert bob.patch(f"/api/accounts/{acct['id']}", {"display_name": "pwned"}).status_code == 404
    assert bob.patch(f"/api/transactions/{t['id']}", {"amount_minor": 1}).status_code == 404
    assert bob.post(f"/api/transactions/{t['id']}/delete", {}).status_code == 404
    assert bob.post(f"/api/transactions/{t['id']}/reverse", {}).status_code == 404
    assert bob.get(f"/api/transactions?account_id={acct['id']}").status_code == 404
    assert bob.get(f"/api/ledger/summary?account_id={acct['id']}").status_code == 404
    # Bob cannot post into Alice's account, or transfer from it, or refund against her txn
    assert (
        bob.post(
            "/api/transactions",
            {"account_id": acct["id"], "kind": "income", "amount_minor": 1, "transaction_date": D},
        ).status_code
        == 404
    )
    bob_acct = new_account(bob)
    assert (
        bob.post(
            "/api/transactions/transfers",
            {
                "from_account_id": acct["id"],
                "to_account_id": bob_acct["id"],
                "amount_minor": 1,
                "transaction_date": D,
            },
        ).status_code
        == 404
    )
    assert (
        bob.post(
            "/api/transactions",
            {
                "account_id": bob_acct["id"],
                "kind": "refund",
                "amount_minor": 1,
                "transaction_date": D,
                "refund_of_id": t["id"],
            },
        ).status_code
        == 404
    )
    # Alice's data is unchanged
    assert balance(alice, acct)["posted_minor"] == 100_000_00 - 1000


def test_database_rejects_cross_user_account_link(make_user):
    """Defence in depth: even a buggy query can't attach a transaction to another user's
    account, because of the composite foreign key."""
    import sqlalchemy

    a = make_user("x1@example.com")
    b = make_user("x2@example.com")
    db_exec(
        "INSERT INTO accounts (public_id, user_id, type, display_name, currency, "
        "opening_balance_minor, opening_balance_date) VALUES "
        "(gen_random_uuid(), :u, 'bank', 'A', 'NGN', 0, now())",
        u=a,
    )
    acct = db_scalar("SELECT id FROM accounts WHERE user_id=:u", u=a)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db_exec(
            "INSERT INTO transactions (public_id, user_id, account_id, kind, direction, "
            "amount_minor, currency, status, transaction_date) VALUES "
            "(gen_random_uuid(), :u, :a, 'expense', 'debit', 1, 'NGN', 'posted', now())",
            u=b,
            a=acct,
        )
