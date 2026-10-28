"""Statement import through the API: upload → review → commit → undo, duplicates, transfer and
reversal matching, reconciliation, isolation."""

from datetime import date, timedelta

import pytest

from tests import statement_fixtures as fx
from tests.conftest import db_scalar
from tests.test_finance import add, balance

OPEN_DATE = "2026-09-30"


@pytest.fixture
def me(api, make_user):
    make_user("imp@example.com")
    api.login("imp@example.com")
    return api


def acct(api, name="GTBank", opening=fx.OPENING, **kw):
    r = api.post(
        "/api/accounts",
        {
            "type": "bank",
            "display_name": name,
            "opening_balance_minor": opening,
            "opening_balance_date": OPEN_DATE,
            **kw,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def upload(api, a, content=None, name="statement.csv"):
    r = api.upload(
        "/api/imports",
        {"account_id": a["id"]},
        name,
        content if content is not None else fx.csv_debit_credit_newest_first(),
    )
    assert r.status_code == 201, r.text
    return r.json()


def commit(api, b, **kw):
    r = api.post(f"/api/imports/{b['id']}/commit", kw)
    assert r.status_code == 200, r.text
    return r.json()


def rows(api, b, outcome=None):
    q = f"?outcome={outcome}" if outcome else ""
    return api.get(f"/api/imports/{b['id']}{q}").json()["rows"]


# ---------------- happy path ----------------


def test_upload_detects_columns_and_stages_rows(me):
    a = acct(me)
    b = upload(me, a)
    assert b["status"] == "staged"
    assert b["mapping"]["amount_mode"] == "debit_credit"
    assert b["headers"][:4] == ["Trans. Date", "Value Date", "Reference", "Narration"]
    assert b["counts"]["new"] == len(fx.ROWS) and b["counts"]["included"] == len(fx.ROWS)
    assert b["statement_closing_balance_minor"] == fx.CLOSING
    assert b["warnings"] == []
    # nothing saved yet
    assert me.get("/api/transactions").json()["total"] == 0
    kinds = {r["narration"]: r["kind"] for r in b["rows"]}
    assert kinds["SMS ALERT CHARGES"] == "fee"
    assert kinds["REVERSAL WEB PURCHASE NETFLIX"] == "reversal"


def test_commit_creates_transactions_links_reversal_and_reconciles(me):
    a = acct(me)
    b = upload(me, a)
    res = commit(me, b)
    assert res["created"] == len(fx.ROWS)
    assert res["reversals_linked"] == 1
    assert res["reconciliation"]["matches"] is True
    bal = balance(me, a)
    assert bal["posted_minor"] == fx.CLOSING
    assert bal["status"] == "reconciled"
    assert bal["statement_as_of"] == "2026-10-06"
    netflix = me.get("/api/transactions?q=netflix").json()["items"]
    statuses = sorted((t["kind"], t["status"]) for t in netflix)
    assert statuses == [("expense", "reversed"), ("reversal", "posted")]
    s = me.get("/api/ledger/summary?date_from=2026-10-01&date_to=2026-10-31").json()["summaries"][0]
    assert s["income"] == 45_000_000
    assert s["fees"] == 5250 + 394
    assert me.get(f"/api/accounts/{a['id']}").json()["source"] == "imported"
    # imported rows carry their source and revision history
    t = me.get("/api/transactions?q=salary").json()["items"][0]
    assert t["source"] == "csv"
    detail = me.get(f"/api/transactions/{t['id']}").json()
    assert detail["revisions"][0]["reason"] == "Imported from statement.csv"


def test_reimporting_same_file_adds_nothing(me):
    a = acct(me)
    commit(me, upload(me, a))
    b2 = upload(me, a)
    assert b2["counts"]["duplicate"] == len(fx.ROWS)
    assert b2["counts"]["included"] == 0
    assert b2["same_file_imported_at"] is not None
    assert me.post(f"/api/imports/{b2['id']}/commit", {}).status_code == 422
    # and the same transactions from an Excel export of the same statement are also caught
    b3 = upload(me, a, fx.xlsx_money_in_out(), "statement.xlsx")
    assert b3["counts"]["duplicate"] == len(fx.ROWS)


def test_genuine_identical_twins_both_kept(me):
    a = acct(me)
    commit(me, upload(me, a))
    bolts = me.get("/api/transactions?q=bolt").json()["items"]
    assert len(bolts) == 2


def test_manual_entry_flagged_as_possible_duplicate(me):
    a = acct(me)
    add(me, a, "expense", 2_500_050, merchant="Shoprite", transaction_date="2026-10-03")
    b = upload(me, a)
    poss = rows(me, b, "possible_duplicate")
    assert len(poss) == 1 and not poss[0]["include"]
    assert "Shoprite" in poss[0]["note"]
    res = commit(me, b)
    assert res["created"] == len(fx.ROWS) - 1
    assert balance(me, a)["status"] == "reconciled"


def test_transfer_matched_across_accounts_not_counted_twice(me):
    gt = acct(me, "GTBank")
    commit(me, upload(me, gt))
    kuda = acct(me, "Kuda", 0)
    data = (
        b"Date,Description,Money In,Money Out,Balance\n"
        b"03/10/2026,TRF FROM GTB JOHN DOE,100000.00,,100000.00\n"
    )
    b = upload(me, kuda, data, "kuda.csv")
    r = b["rows"][0]
    assert r["kind"] == "transfer" and "GTBank" in r["note"]
    res = commit(me, b)
    assert res["transfers_linked"] == 1
    legs = me.get("/api/transactions?kind=transfer").json()["items"]
    assert len(legs) == 2 and {t["account_name"] for t in legs} == {"GTBank", "Kuda"}
    s = me.get("/api/ledger/summary?date_from=2026-10-01&date_to=2026-10-31").json()["summaries"][0]
    # the ₦100,000 is neither spending nor income (and the reversed Netflix charge cancels out)
    assert s["gross_spending"] == 2_500_050 + 5250 + 50_000 + 50_000 + 394
    assert s["income"] == 45_000_000
    # GTBank still matches its statement after its row became a transfer leg
    assert balance(me, gt)["status"] == "reconciled"


def test_user_can_decline_transfer_suggestion(me):
    gt = acct(me, "GTBank")
    commit(me, upload(me, gt))
    kuda = acct(me, "Kuda", 0)
    data = b"Date,Description,Money In,Money Out\n03/10/2026,GIFT,100000.00,\n"
    b = upload(me, kuda, data, "kuda.csv")
    row = b["rows"][0]
    assert "transfer" in row["allowed_kinds"]
    me.post(f"/api/imports/{b['id']}/rows", {"updates": [{"id": row["id"], "kind": "income"}]})
    assert commit(me, b)["transfers_linked"] == 0
    assert me.get("/api/transactions?kind=transfer").json()["total"] == 0


def test_review_edits_and_validation(me):
    a = acct(me)
    b = upload(me, a)
    sms = next(r for r in b["rows"] if r["narration"] == "SMS ALERT CHARGES")
    salary = next(r for r in b["rows"] if r["narration"].startswith("SALARY"))
    bad = me.post(
        f"/api/imports/{b['id']}/rows", {"updates": [{"id": salary["id"], "kind": "fee"}]}
    )
    assert bad.status_code == 422  # a credit can't be a fee
    ok = me.post(
        f"/api/imports/{b['id']}/rows",
        {
            "updates": [
                {"id": sms["id"], "include": False},
                {"id": salary["id"], "kind": "adjustment"},
            ]
        },
    )
    assert ok.status_code == 200 and ok.json()["counts"]["included"] == len(fx.ROWS) - 1
    res = commit(me, b)
    assert res["created"] == len(fx.ROWS) - 1
    assert res["reconciliation"]["matches"] is False  # skipped a real row → balance differs
    assert res["reconciliation"]["difference_minor"] == -5250
    assert balance(me, a)["status"] == "unreconciled"
    assert me.get("/api/transactions?kind=adjustment").json()["total"] == 1


def test_remap_columns(me):
    a = acct(me)
    b = upload(me, a)
    m = b["mapping"]
    m["columns"]["debit"], m["columns"]["credit"] = m["columns"]["credit"], m["columns"]["debit"]
    m.pop("from_profile", None)
    r = me.post(f"/api/imports/{b['id']}/mapping", m)
    assert r.status_code == 200, r.text
    assert any("swapped" in w for w in r.json()["warnings"])
    m["columns"]["debit"], m["columns"]["credit"] = m["columns"]["credit"], m["columns"]["debit"]
    r2 = me.post(f"/api/imports/{b['id']}/mapping", m)
    assert r2.json()["warnings"] == []
    bad = dict(m, columns={**m["columns"], "balance": m["columns"]["date"]})
    assert me.post(f"/api/imports/{b['id']}/mapping", bad).status_code == 422


def test_mapping_is_remembered_per_account(me):
    a = acct(me)
    data = b"When,What,Out,In\n01/10/2026,Thing,100.00,\n"
    b = upload(me, a, data, "odd.csv")
    assert b["warnings"]  # headers not recognised
    m = {
        "header_row": 0,
        "columns": {"date": 0, "description": 1, "debit": 2, "credit": 3},
        "amount_mode": "debit_credit",
        "date_order": "DMY",
    }
    b = me.post(f"/api/imports/{b['id']}/mapping", m).json()
    assert b["counts"]["new"] == 1
    commit(me, b)
    again = upload(me, a, b"When,What,Out,In\n02/10/2026,Other,50.00,\n", "odd2.csv")
    assert again["mapping"].get("from_profile") is True
    assert again["counts"]["new"] == 1


def test_set_opening_balance_from_statement(me):
    a = acct(me, opening=0)
    b = upload(me, a)
    assert b["can_set_opening"] is True
    res = commit(me, b, set_opening_from_statement=True)
    assert res["opening_balance_set"] is True
    acc = me.get(f"/api/accounts/{a['id']}").json()
    assert acc["opening_balance_minor"] == fx.OPENING
    assert acc["opening_balance_date"] == "2026-10-01"
    assert acc["balance"]["status"] == "reconciled"


def test_set_opening_refused_when_account_has_transactions(me):
    a = acct(me, opening=0)
    add(me, a, "income", 1, transaction_date="2026-10-01")
    b = upload(me, a)
    assert b["can_set_opening"] is False
    r = me.post(f"/api/imports/{b['id']}/commit", {"set_opening_from_statement": True})
    assert r.status_code == 422


def test_undo_removes_everything_and_allows_reimport(me):
    gt = acct(me, "GTBank")
    b = upload(me, gt)
    commit(me, b)
    kuda = acct(me, "Kuda", 0)
    kb = upload(
        me, kuda, b"Date,Description,Money In,Money Out\n03/10/2026,TRF,100000.00,\n", "k.csv"
    )
    commit(me, kb)
    # undo the GTBank import: its rows go, and Kuda's transfer leg reverts to income
    r = me.post(f"/api/imports/{b['id']}/undo", {})
    assert r.status_code == 200 and r.json()["status"] == "undone"
    assert me.get(f"/api/transactions?account_id={gt['id']}").json()["total"] == 0
    k = me.get(f"/api/transactions?account_id={kuda['id']}").json()["items"][0]
    assert k["kind"] == "income" and k["transfer_group_id"] is None
    gb = balance(me, gt)
    assert gb["posted_minor"] == fx.OPENING
    assert gb["status"] == "estimated"  # statement from an undone import is ignored
    again = upload(me, gt)
    assert again["counts"]["new"] == len(fx.ROWS)
    assert me.post(f"/api/imports/{b['id']}/undo", {}).status_code == 409


def test_undo_restores_manual_transaction_converted_to_transfer(me):
    gt = acct(me, "GTBank")
    kuda = acct(me, "Kuda", 0)
    manual = add(me, kuda, "income", 10_000_000, merchant="From GTB", transaction_date="2026-10-03")
    b = upload(me, gt)
    assert any(r["kind"] == "transfer" for r in b["rows"])
    commit(me, b)
    assert me.get(f"/api/transactions/{manual['id']}").json()["kind"] == "transfer"
    me.post(f"/api/imports/{b['id']}/undo", {})
    restored = me.get(f"/api/transactions/{manual['id']}").json()
    assert restored["kind"] == "income" and restored["transfer_group_id"] is None
    assert [r["action"] for r in restored["revisions"]] == ["create", "update", "update"]


def test_reversal_of_existing_manual_transaction(me):
    a = acct(me)
    t = add(me, a, "expense", 440_000, merchant="Netflix", transaction_date="2026-10-04")
    data = b"Date,Narration,Debit,Credit\n05/10/2026,REVERSAL NETFLIX,,4400.00\n"
    b = upload(me, a, data, "rev.csv")
    assert b["rows"][0]["kind"] == "reversal"
    commit(me, b)
    assert me.get(f"/api/transactions/{t['id']}").json()["status"] == "reversed"
    me.post(f"/api/imports/{b['id']}/undo", {})
    assert me.get(f"/api/transactions/{t['id']}").json()["status"] == "posted"


def test_unmatched_reversal_becomes_refund(me):
    a = acct(me)
    b = upload(me, a, b"Date,Narration,Debit,Credit\n05/10/2026,REVERSAL XYZ,,700.00\n", "r.csv")
    row = b["rows"][0]
    assert row["kind"] == "refund" and "wasn't found" in row["note"]


def test_discard_and_stale_cleanup(me):
    a = acct(me)
    b = upload(me, a)
    assert me.post(f"/api/imports/{b['id']}/discard", {}).json()["status"] == "discarded"
    assert db_scalar("SELECT count(*) FROM import_rows") == 0
    assert db_scalar("SELECT grid IS NULL FROM import_batches") is True
    assert me.post(f"/api/imports/{b['id']}/commit", {}).status_code == 409


def test_grid_cleared_after_commit(me):
    a = acct(me)
    commit(me, upload(me, a))
    assert db_scalar("SELECT grid IS NULL FROM import_batches") is True


def test_sensitive_numbers_masked_in_saved_transactions(me):
    a = acct(me)
    commit(me, upload(me, a))
    assert db_scalar("SELECT count(*) FROM transactions WHERE narration LIKE '%0123456789%'") == 0
    assert (
        db_scalar("SELECT count(*) FROM transactions WHERE narration LIKE '%5399831234567895%'")
        == 0
    )


@pytest.mark.parametrize(
    ("content", "name", "msg"),
    [
        (b"<html></html>", "s.xls", "web page"),
        (b"%PDF-1.4", "s.pdf", "PDF"),
        (b"", "s.csv", "empty"),
    ],
)
def test_bad_files_rejected_helpfully(me, content, name, msg):
    a = acct(me)
    r = me.upload("/api/imports", {"account_id": a["id"]}, name, content)
    assert r.status_code == 422 and msg in r.json()["detail"]


def test_file_size_limit(me, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_max_mb", 1)
    a = acct(me)
    r = me.upload("/api/imports", {"account_id": a["id"]}, "big.csv", b"x" * (1024 * 1024 + 1))
    assert r.status_code == 413


def test_every_layout_imports(me):
    for i, (make, name) in enumerate(
        [
            (fx.csv_signed_amount, "s.csv"),
            (fx.csv_indicator_semicolon, "i.csv"),
            (fx.xlsx_money_in_out, "x.xlsx"),
            (fx.xls_debit_credit, "x.xls"),
        ]
    ):
        a = acct(me, f"A{i}")
        b = upload(me, a, make(), name)
        assert b["counts"]["new"] == len(fx.ROWS), (name, b["warnings"])
        res = commit(me, b)
        assert res["created"] == len(fx.ROWS)
        assert balance(me, a)["posted_minor"] == fx.CLOSING


# ---------------- isolation ----------------


def test_users_cannot_touch_each_others_imports(api_factory, make_user):
    make_user("a@example.com")
    make_user("b@example.com")
    alice, bob = api_factory(), api_factory()
    alice.login("a@example.com")
    bob.login("b@example.com")
    a = acct(alice)
    b = upload(alice, a)
    rid = b["rows"][0]["id"]
    assert bob.get("/api/imports").json() == []
    assert bob.get(f"/api/imports/{b['id']}").status_code == 404
    assert (
        bob.post(
            f"/api/imports/{b['id']}/rows", {"updates": [{"id": rid, "include": False}]}
        ).status_code
        == 404
    )
    assert bob.post(f"/api/imports/{b['id']}/commit", {}).status_code == 404
    assert bob.post(f"/api/imports/{b['id']}/discard", {}).status_code == 404
    assert bob.post(
        f"/api/imports/{b['id']}/mapping", b["mapping"] | {"from_profile": None}
    ).status_code in (404, 422)
    r = bob.upload("/api/imports", {"account_id": a["id"]}, "s.csv", fx.csv_signed_amount())
    assert r.status_code == 404
    assert (
        bob.post(
            f"/api/accounts/{a['id']}/reconcile",
            {"as_of_date": "2026-10-06", "statement_balance_minor": 1},
        ).status_code
        == 404
    )
    commit(alice, b)
    assert bob.post(f"/api/imports/{b['id']}/undo", {}).status_code == 404
    # Bob's own import never matches Alice's transactions as transfers or duplicates
    bacct = acct(bob, "Bob bank", 0)
    bb = upload(
        bob, bacct, b"Date,Description,Money In,Money Out\n03/10/2026,TRF,100000.00,\n", "k.csv"
    )
    assert bb["rows"][0]["kind"] == "income"


# ---------------- manual reconciliation ----------------


def test_manual_reconcile(me):
    a = acct(me)
    add(me, a, "expense", 1000, transaction_date="2026-10-02")
    r = me.post(
        f"/api/accounts/{a['id']}/reconcile",
        {"as_of_date": "2026-10-02", "statement_balance_minor": fx.OPENING - 1000},
    )
    assert r.status_code == 201 and r.json()["difference_minor_now"] == 0
    assert balance(me, a)["status"] == "reconciled"
    # an edit to an older transaction breaks the match (B5)
    t = me.get("/api/transactions").json()["items"][0]
    me.patch(f"/api/transactions/{t['id']}", {"amount_minor": 1500})
    b = balance(me, a)
    assert b["status"] == "unreconciled" and b["difference_minor"] == 500
    hist = me.get(f"/api/accounts/{a['id']}/reconciliations").json()
    assert hist[0]["computed_balance_minor_then"] != hist[0]["computed_balance_minor_now"]
    future = (date.today() + timedelta(days=3)).isoformat()
    assert (
        me.post(
            f"/api/accounts/{a['id']}/reconcile",
            {"as_of_date": future, "statement_balance_minor": 1},
        ).status_code
        == 422
    )
    assert (
        me.post(
            f"/api/accounts/{a['id']}/reconcile",
            {"as_of_date": "2026-01-01", "statement_balance_minor": 1},
        ).status_code
        == 422
    )


# ---------------- simulated events ----------------


def test_simulate_requires_demo_mode(me):
    assert me.post("/api/imports/simulate", {"days": 10}).status_code == 404


def test_simulated_events_flow(me, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    r = me.post("/api/imports/simulate", {"days": 40})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["adapter"] == "simulated" and b["warnings"] == []
    assert b["counts"]["new"] > 10
    res = commit(me, b)
    assert res["reconciliation"]["matches"] is True
    accts = me.get("/api/accounts").json()
    demo = next(a for a in accts if a["source"] == "simulated")
    assert demo["balance"]["status"] == "reconciled"
    assert db_scalar("SELECT bool_and(is_demo) FROM transactions WHERE source='simulated'") is True
    # nothing new until tomorrow
    assert me.post("/api/imports/simulate", {"days": 40}).status_code == 422
