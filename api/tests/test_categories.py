"""Categories, rules, review queue, learning from corrections, spending by category."""

import pytest

from tests import statement_fixtures as fx
from tests.conftest import db_exec, db_scalar
from tests.test_finance import D, add, new_account


@pytest.fixture
def me(api, make_user):
    make_user("cat@example.com")
    api.login("cat@example.com")
    return api


def cats(api, include_archived=False):
    q = "?include_archived=true" if include_archived else ""
    return {c["slug"] or c["name"]: c for c in api.get(f"/api/categories{q}").json()}


def txn(api, t):
    return api.get(f"/api/transactions/{t['id']}").json()


# ---------------- defaults & automatic categorisation ----------------


def test_new_user_gets_default_categories(me):
    c = cats(me)
    assert len(c) == 22
    assert c["bank_fees"]["locked"] and c["transfers"]["locked"]
    assert c["salary"]["kind"] == "income"


def test_automatic_categories_with_reasons(me):
    a = new_account(me)
    shop = add(me, a, "expense", 1000, merchant="Shoprite Lekki")
    assert (shop["category_name"], shop["category_source"]) == ("Food & groceries", "system")
    assert "SHOPRITE" in shop["category_reason"] and not shop["needs_review"]
    fee = add(me, a, "fee", 50, narration="SMS ALERT")
    assert fee["category_name"] == "Bank fees" and fee["category_confidence"] == 100
    sal = add(me, a, "income", 100, merchant="SALARY ACME")
    assert sal["category_name"] == "Salary"
    unknown = add(me, a, "expense", 10, narration="NIP TRF TO CHIOMA")
    assert unknown["category_id"] is None and unknown["needs_review"]
    generic = add(me, a, "expense", 10, merchant="Big Supermarket")
    assert generic["category_name"] == "Food & groceries" and generic["needs_review"]
    assert me.get("/api/categories/review-count").json()["count"] == 2
    assert me.get("/api/transactions?needs_review=true").json()["total"] == 2


def test_transfers_and_adjustments(me):
    a, b = new_account(me), new_account(me, "Kuda", 0)
    tr = me.post(
        "/api/transactions/transfers",
        {
            "from_account_id": a["id"],
            "to_account_id": b["id"],
            "amount_minor": 100,
            "transaction_date": D,
        },
    ).json()
    assert (
        tr["debit"]["category_name"]
        == tr["credit"]["category_name"]
        == "Transfers between my accounts"
    )
    adj = add(me, a, "adjustment", 5, direction="credit")
    assert adj["category_id"] is None and not adj["needs_review"]
    bad = me.patch(
        f"/api/transactions/{tr['debit']['id']}", {"category_id": cats(me)["shopping"]["id"]}
    )
    assert bad.status_code == 422


def test_explicit_choice_and_validation(me, make_user, api_factory):
    a = new_account(me)
    c = cats(me)
    t = add(me, a, "expense", 1000, merchant="Shoprite", category_id=c["family"]["id"])
    assert (t["category_name"], t["category_source"]) == ("Family support", "user")
    bad = me.post(
        "/api/transactions",
        {
            "account_id": a["id"],
            "kind": "expense",
            "amount_minor": 1,
            "transaction_date": D,
            "category_id": c["salary"]["id"],
        },
    )
    assert bad.status_code == 422  # income category on spending
    make_user("other@example.com")
    other = api_factory()
    other.login("other@example.com")
    theirs = cats(other)["shopping"]["id"]
    r = me.post(
        "/api/transactions",
        {
            "account_id": a["id"],
            "kind": "expense",
            "amount_minor": 1,
            "transaction_date": D,
            "category_id": theirs,
        },
    )
    assert r.status_code == 404


def test_user_choice_is_never_overwritten(me):
    a = new_account(me)
    c = cats(me)
    t = add(me, a, "expense", 1000, merchant="Shoprite")
    me.patch(f"/api/transactions/{t['id']}", {"category_id": c["shopping"]["id"]})
    me.patch(f"/api/transactions/{t['id']}", {"merchant": "Netflix"})
    after = txn(me, t)
    assert (after["category_name"], after["category_source"]) == ("Shopping", "user")
    me.post("/api/categories/reapply", {})
    assert txn(me, t)["category_name"] == "Shopping"
    hist = [r for r in after["revisions"] if "category" in r["changes"]]
    assert hist[0]["changes"]["category"] == ["Food & groceries", "Shopping"]


def test_editing_text_recomputes_automatic_category(me):
    a = new_account(me)
    t = add(me, a, "expense", 1000, merchant="Shoprite")
    r = me.patch(f"/api/transactions/{t['id']}", {"merchant": "Bolt ride"}).json()
    assert r["category_name"] == "Transport"


def test_leave_uncategorised_on_purpose(me):
    a = new_account(me)
    t = add(me, a, "expense", 10, narration="NIP TRF TO CHIOMA")
    r = me.patch(f"/api/transactions/{t['id']}", {"category_id": None}).json()
    assert r["category_id"] is None and not r["needs_review"] and r["category_source"] == "user"


def test_kind_change_drops_unfitting_user_choice(me):
    a = new_account(me)
    t = add(me, a, "expense", 10, merchant="SALARY ACME", category_id=cats(me)["shopping"]["id"])
    r = me.patch(f"/api/transactions/{t['id']}", {"kind": "income"}).json()
    assert r["category_name"] == "Salary" and r["category_source"] == "system"


def test_refund_and_reversal_inherit_category(me):
    a = new_account(me)
    c = cats(me)
    buy = add(me, a, "expense", 2000, merchant="Corner shop", category_id=c["shopping"]["id"])
    refund = add(me, a, "refund", 500, refund_of_id=buy["id"])
    assert (refund["category_name"], refund["category_source"]) == ("Shopping", "linked")
    rev = me.post(f"/api/transactions/{buy['id']}/reverse", {}).json()
    assert rev["category_name"] == "Shopping"


# ---------------- rules & learning from corrections ----------------


def test_rule_suggestion_after_correction(me):
    a = new_account(me)
    c = cats(me)
    t1 = add(me, a, "expense", 100, narration="POS PURCHASE MAMA PUT LEKKI")
    add(me, a, "expense", 200, narration="POS PURCHASE MAMA PUT IKEJA")
    add(
        me, a, "expense", 300, narration="POS PURCHASE MAMA PUT VI", category_id=c["family"]["id"]
    )  # the user's own choice: never changed
    me.patch(f"/api/transactions/{t1['id']}", {"category_id": c["eating_out"]["id"]})
    s = me.get(f"/api/categories/suggestion?transaction_id={t1['id']}").json()
    assert s["pattern"] == "MAMA" and s["category_name"] == "Eating out"
    assert s["similar_count"] == 1


def test_create_rule_applies_to_existing_but_not_user_choices(me):
    a = new_account(me)
    c = cats(me)
    auto = add(me, a, "expense", 100, narration="POS PURCHASE MAMA PUT LEKKI")
    mine = add(
        me, a, "expense", 300, narration="POS PURCHASE MAMA PUT VI", category_id=c["family"]["id"]
    )
    prev = me.post(
        "/api/categories/rules/preview",
        {"category_id": c["eating_out"]["id"], "pattern": "mama put"},
    )
    assert prev.json()["updated"] == 1
    r = me.post(
        "/api/categories/rules",
        {
            "category_id": c["eating_out"]["id"],
            "pattern": "mama put",
            "apply_to_existing": True,
            "created_from": "user_correction",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["pattern"] == "MAMA PUT" and r.json()["applied_to"] == 1
    a1 = txn(me, auto)
    assert (a1["category_name"], a1["category_source"]) == ("Eating out", "rule")
    assert "MAMA PUT" in a1["category_reason"]
    assert txn(me, mine)["category_name"] == "Family support"
    # new transactions follow the rule, and it counts its hits
    new = add(me, a, "expense", 50, narration="MAMA PUT YABA")
    assert new["category_name"] == "Eating out" and not new["needs_review"]
    rules = me.get("/api/categories/rules").json()
    assert rules[0]["hit_count"] >= 2


def test_rule_beats_builtin_and_respects_filters(me):
    a, b = new_account(me), new_account(me, "Business", 0)
    c = cats(me)
    me.post(
        "/api/categories/rules",
        {"category_id": c["family"]["id"], "pattern": "SHOPRITE", "account_id": b["id"]},
    )
    assert add(me, a, "expense", 1, merchant="Shoprite")["category_name"] == "Food & groceries"
    assert add(me, b, "expense", 1, merchant="Shoprite")["category_name"] == "Family support"


def test_rule_validation(me):
    c = cats(me)
    assert (
        me.post(
            "/api/categories/rules", {"category_id": c["transfers"]["id"], "pattern": "X1"}
        ).status_code
        == 422
    )
    assert (
        me.post(
            "/api/categories/rules", {"category_id": c["shopping"]["id"], "pattern": " a "}
        ).status_code
        == 422
    )
    assert (
        me.post(
            "/api/categories/rules",
            {"category_id": c["shopping"]["id"], "pattern": "AB", "match_type": "regex"},
        ).status_code
        == 422
    )


def test_delete_rule_keeps_categories_until_reapply(me):
    a = new_account(me)
    c = cats(me)
    r = me.post(
        "/api/categories/rules", {"category_id": c["family"]["id"], "pattern": "ZENITH GIFT"}
    ).json()
    t = add(me, a, "expense", 1, narration="ZENITH GIFT TO MUM")
    assert txn(me, t)["category_name"] == "Family support"
    me.client.delete(f"/api/categories/rules/{r['id']}", headers=me._hdr())
    assert txn(me, t)["category_name"] == "Family support"
    assert me.post("/api/categories/reapply", {}).json()["updated"] == 1
    assert txn(me, t)["category_id"] is None


def test_bulk_assign_modes(me):
    a, b = new_account(me), new_account(me, "Kuda", 0)
    c = cats(me)
    t1 = add(me, a, "expense", 1, narration="UNKNOWN 1")
    t2 = add(me, a, "expense", 2, narration="UNKNOWN 2")
    inc = add(me, a, "income", 3, narration="FROM ADA")
    sug = add(me, a, "expense", 4, merchant="Big Supermarket")
    tr = me.post(
        "/api/transactions/transfers",
        {
            "from_account_id": a["id"],
            "to_account_id": b["id"],
            "amount_minor": 5,
            "transaction_date": D,
        },
    ).json()
    r = me.post(
        "/api/categories/assign",
        {
            "ids": [t1["id"], t2["id"], inc["id"], tr["debit"]["id"]],
            "category_id": c["family"]["id"],
        },
    ).json()
    assert r == {"updated": 2, "skipped": 2}  # income doesn't fit; transfer is automatic
    r2 = me.post("/api/categories/assign", {"ids": [inc["id"]], "uncategorised": True}).json()
    assert r2["updated"] == 1 and not txn(me, inc)["needs_review"]
    r3 = me.post("/api/categories/assign", {"ids": [sug["id"]], "accept_suggestions": True}).json()
    assert r3["updated"] == 1
    s = txn(me, sug)
    assert (s["category_name"], s["category_source"], s["needs_review"]) == (
        "Food & groceries",
        "user",
        False,
    )
    assert me.get("/api/categories/review-count").json()["count"] == 0
    assert me.post("/api/categories/assign", {"ids": [t1["id"]]}).status_code == 422


# ---------------- managing categories ----------------


def test_create_rename_archive_delete(me):
    r = me.post(
        "/api/categories", {"name": "Generator diesel", "kind": "expense", "color": "#123abc"}
    )
    assert r.status_code == 201
    cid = r.json()["id"]
    assert (
        me.post("/api/categories", {"name": "generator DIESEL", "kind": "expense"}).status_code
        == 409
    )
    assert me.patch(f"/api/categories/{cid}", {"name": "Diesel"}).json()["name"] == "Diesel"
    assert me.patch(f"/api/categories/{cid}", {"is_archived": True}).json()["is_archived"]
    assert "Diesel" not in cats(me) and "Diesel" in cats(me, include_archived=True)
    assert me.client.delete(f"/api/categories/{cid}", headers=me._hdr()).status_code == 204
    c = cats(me)
    assert (
        me.patch(f"/api/categories/{c['bank_fees']['id']}", {"is_archived": True}).status_code
        == 422
    )
    assert (
        me.client.delete(f"/api/categories/{c['transfers']['id']}", headers=me._hdr()).status_code
        == 422
    )
    assert (
        me.post("/api/categories", {"name": "Bad", "kind": "expense", "color": "red"}).status_code
        == 422
    )


def test_archived_category_not_used_for_new_transactions(me):
    a = new_account(me)
    me.patch(f"/api/categories/{cats(me)['groceries']['id']}", {"is_archived": True})
    t = add(me, a, "expense", 1, merchant="Shoprite")
    assert t["category_id"] is None and t["needs_review"]


def test_delete_used_category_refused_merge_instead(me):
    a = new_account(me)
    c = cats(me)
    src = me.post("/api/categories", {"name": "Food stuff", "kind": "expense"}).json()
    t = add(me, a, "expense", 1, narration="X MARKET", category_id=src["id"])
    me.post("/api/categories/rules", {"category_id": src["id"], "pattern": "X MARKET"})
    assert me.client.delete(f"/api/categories/{src['id']}", headers=me._hdr()).status_code == 422
    assert (
        me.post(f"/api/categories/{src['id']}/merge", {"into_id": c["salary"]["id"]}).status_code
        == 422
    )
    m = me.post(f"/api/categories/{src['id']}/merge", {"into_id": c["groceries"]["id"]})
    assert m.status_code == 200 and m.json()["rule_count"] == 1
    after = txn(me, t)
    assert (after["category_name"], after["category_source"]) == ("Food & groceries", "user")
    assert "Food stuff" not in cats(me, include_archived=True)


# ---------------- spending by category ----------------


def test_spending_by_category_adds_up(me):
    a = new_account(me)
    c = cats(me)
    buy = add(me, a, "expense", 20_000, merchant="Jumia")
    add(me, a, "refund", 5_000, refund_of_id=buy["id"])
    add(me, a, "expense", 3_000, merchant="Bolt")
    add(me, a, "fee", 50)
    add(me, a, "expense", 7, narration="MYSTERY")
    add(me, a, "income", 900, merchant="Salary")
    rows = me.get(f"/api/ledger/by-category?date_from={D}&date_to={D}").json()["rows"]
    by = {r["name"]: r for r in rows}
    assert by["Shopping"]["net_spending"] == 15_000  # refund reduces its own category
    assert by["Transport"]["net_spending"] == 3_000
    assert by["Bank fees"]["net_spending"] == 50
    assert by["Uncategorised"]["net_spending"] == 7
    assert by["Salary"]["income"] == 900
    s = me.get(f"/api/ledger/summary?date_from={D}&date_to={D}").json()["summaries"][0]
    assert sum(r["net_spending"] for r in rows) == s["net_spending"]
    assert rows[0]["name"] == "Shopping"  # largest first
    assert c  # categories loaded


# ---------------- import integration ----------------


def test_import_suggests_categories_and_honours_changes(me):
    a = me.post(
        "/api/accounts",
        {
            "type": "bank",
            "display_name": "GT",
            "opening_balance_minor": fx.OPENING,
            "opening_balance_date": "2026-09-30",
        },
    ).json()
    b = me.upload(
        "/api/imports", {"account_id": a["id"]}, "s.csv", fx.csv_debit_credit_newest_first()
    ).json()
    rows = {r["narration"]: r for r in b["rows"]}
    assert rows["SMS ALERT CHARGES"]["category_name"] == "Bank fees"
    assert rows["WEB PURCHASE NETFLIX"]["category_name"] == "Entertainment & subscriptions"
    assert rows["SALARY OCT 2026 ACME LTD"]["category_name"] == "Salary"
    nip = next(r for k, r in rows.items() if k.startswith("NIP TRF"))
    assert nip["category_id"] is None
    c = cats(me)
    me.post(
        f"/api/imports/{b['id']}/rows",
        {"updates": [{"id": nip["id"], "category_id": c["family"]["id"]}]},
    )
    bad = me.post(
        f"/api/imports/{b['id']}/rows",
        {
            "updates": [
                {
                    "id": rows["REVERSAL WEB PURCHASE NETFLIX"]["id"],
                    "category_id": c["family"]["id"],
                }
            ]
        },
    )
    assert bad.status_code == 422
    me.post(f"/api/imports/{b['id']}/commit", {})
    t = me.get("/api/transactions?q=NIP").json()["items"][0]
    assert (t["category_name"], t["category_source"]) == ("Family support", "user")
    rev = me.get("/api/transactions?kind=reversal").json()["items"][0]
    assert rev["category_name"] == "Entertainment & subscriptions"


def test_transfer_match_recategorises_partner_and_undo_restores(me):
    gt = me.post(
        "/api/accounts",
        {
            "type": "bank",
            "display_name": "GT",
            "opening_balance_minor": fx.OPENING,
            "opening_balance_date": "2026-09-30",
        },
    ).json()
    kuda = me.post(
        "/api/accounts",
        {
            "type": "wallet",
            "display_name": "Kuda",
            "opening_balance_minor": 0,
            "opening_balance_date": "2026-09-30",
        },
    ).json()
    manual = add(
        me, kuda, "income", 10_000_000, narration="FROM GTB", transaction_date="2026-10-03"
    )
    assert manual["category_id"] is None
    b = me.upload(
        "/api/imports", {"account_id": gt["id"]}, "s.csv", fx.csv_debit_credit_newest_first()
    ).json()
    me.post(f"/api/imports/{b['id']}/commit", {})
    assert txn(me, manual)["category_name"] == "Transfers between my accounts"
    me.post(f"/api/imports/{b['id']}/undo", {})
    back = txn(me, manual)
    assert back["kind"] == "income" and back["category_name"] is None and back["needs_review"]


# ---------------- CLI backfill ----------------


def test_cli_categorise_pending(me):
    from app.cli import main

    a = new_account(me)
    t = add(me, a, "expense", 1, merchant="Shoprite")
    db_exec(
        "UPDATE transactions SET category_id = NULL, category_source = 'none', "
        "merchant_normalised = NULL"
    )
    assert main(["categorise-pending"]) == 0
    after = txn(me, t)
    assert (
        after["category_name"] == "Food & groceries" and after["merchant_normalised"] == "SHOPRITE"
    )
    assert db_scalar("SELECT count(*) FROM categories") == 22


# ---------------- isolation ----------------


def test_users_cannot_touch_each_others_categories(api_factory, make_user):
    make_user("a@example.com")
    make_user("b@example.com")
    alice, bob = api_factory(), api_factory()
    alice.login("a@example.com")
    bob.login("b@example.com")
    ac = cats(alice)
    r = alice.post(
        "/api/categories/rules", {"category_id": ac["shopping"]["id"], "pattern": "SECRETSHOP"}
    ).json()
    assert bob.get("/api/categories/rules").json() == []
    cid = ac["shopping"]["id"]
    assert bob.patch(f"/api/categories/{cid}", {"name": "pwned"}).status_code == 404
    assert bob.client.delete(f"/api/categories/{cid}", headers=bob._hdr()).status_code == 404
    assert (
        bob.post(f"/api/categories/{cid}/merge", {"into_id": cats(bob)["family"]["id"]}).status_code
        == 404
    )
    assert (
        bob.post("/api/categories/rules", {"category_id": cid, "pattern": "XX"}).status_code == 404
    )
    assert bob.patch(f"/api/categories/rules/{r['id']}", {"pattern": "YY"}).status_code == 404
    assert (
        bob.client.delete(f"/api/categories/rules/{r['id']}", headers=bob._hdr()).status_code == 404
    )
    # Alice's rule never affects Bob's transactions
    acct = new_account(bob)
    assert add(bob, acct, "expense", 1, narration="SECRETSHOP")["category_id"] is None
    assert cats(alice)["shopping"]["name"] == "Shopping"
