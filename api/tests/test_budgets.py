"""Monthly budgets (Phase 6): lines, thresholds, carry-over, projections, suggestions."""

from datetime import date

import pytest

from tests.conftest import PASSWORD, db_scalar
from tests.test_finance import add, new_account

TODAY = date(2026, 10, 15)
OCT, SEP, AUG, JUL = "2026-10-01", "2026-09-01", "2026-08-01", "2026-07-01"


@pytest.fixture
def me(api, make_user, monkeypatch):
    monkeypatch.setattr("app.budgets.router.today_for", lambda _u: TODAY)
    make_user("budget@example.com")
    api.login("budget@example.com")
    return api


def cats(api):
    return {c["slug"] or c["name"]: c["id"] for c in api.get("/api/categories").json()}


def spend(api, acct, amount, cat, d, kind="expense", **kw):
    return add(api, acct, kind, amount, category_id=cat, transaction_date=d, **kw)


def create(api, month=OCT, **kw):
    r = api.post("/api/budgets", {"month": month, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def save_lines(api, page, lines):
    r = api.put(f"/api/budgets/{page['budget']['id']}/lines", {"lines": lines})
    assert r.status_code == 200, r.text
    return r.json()


def line(page, name):
    return next(x for x in page["budget"]["lines"] if x["name"] == name)


def test_no_budget_yet(me):
    p = me.get("/api/budgets").json()
    assert p["month"] == OCT and p["budget"] is None
    assert p["default_thresholds"] == [70, 90, 100]
    assert p["previous_month_has_budget"] is False


def test_lines_spent_unbudgeted_and_status(me):
    c = cats(me)
    a = new_account(me)
    spend(me, a, 60_000_00, c["groceries"], "2026-10-03")
    spend(me, a, 10_000_00, c["groceries"], "2026-10-05", kind="refund")
    spend(me, a, 30_000_00, c["transport"], "2026-10-04")
    spend(me, a, 5_000_00, c["shopping"], "2026-10-06")
    add(me, a, "expense", 2_000_00, narration="NIP TRF TO ADA", transaction_date="2026-10-06")
    spend(me, a, 99_000_00, c["groceries"], "2026-09-20")  # last month
    spend(me, a, 7_000_00, c["groceries"], "2026-10-07", status="pending")
    spend(me, a, 500_000_00, c["salary"], "2026-10-01", kind="income")

    p = create(me)
    p = save_lines(
        me,
        p,
        [
            {"category_id": c["groceries"], "planned_minor": 50_000_00},
            {"category_id": c["transport"], "planned_minor": 30_000_00},
            {"category_id": None, "planned_minor": 200_000_00},
        ],
    )
    b = p["budget"]
    g = line(p, "Food & groceries")
    assert (g["spent_minor"], g["remaining_minor"], g["percent_used"]) == (50_000_00, 0, 100)
    assert g["threshold_reached"] == 100 and g["status"] == "threshold" and not g["over"]
    t = line(p, "Transport")
    assert t["spent_minor"] == 30_000_00 and t["status"] == "threshold"
    assert b["overall"]["spent_minor"] == 87_000_00  # all net spending incl. uncategorised
    assert b["overall"]["name"] == "Overall spending limit"
    # R19: budgeted + unbudgeted = total spending (matches the reports overview)
    assert b["budgeted_spending"] == 80_000_00
    assert b["unbudgeted_spending"] == 7_000_00
    assert sum(u["net_spending"] for u in b["unbudgeted"]) == 7_000_00
    assert {u["name"] for u in b["unbudgeted"]} == {"Shopping", "Uncategorised"}
    report = me.get("/api/reports/overview?date_from=2026-10-01&date_to=2026-10-31").json()
    assert report["summary"]["net_spending"] == b["total_spending"] == 87_000_00
    assert b["total_planned"] == 80_000_00
    assert b["attention_count"] == 2

    # going over
    spend(me, a, 1_00, c["groceries"], "2026-10-08")
    g = line(me.get("/api/budgets").json(), "Food & groceries")
    assert g["over"] and g["remaining_minor"] == -1_00 and g["status"] == "over"


def test_projection_and_safe_per_day(me):
    c = cats(me)
    a = new_account(me)
    spend(me, a, 15_000_00, c["transport"], "2026-10-02")
    p = save_lines(me, create(me), [{"category_id": c["transport"], "planned_minor": 31_000_00}])
    t = line(p, "Transport")
    # 15 days in, 16 to go: 15,000 + 15,000 x 16/15 = 31,000
    assert t["projected_minor"] == 31_000_00 and not t["projected_over"]
    assert t["days_left"] == 17  # including today
    assert t["safe_per_day_minor"] == 16_000_00 // 17


def test_thresholds_from_settings_and_override(me):
    c = cats(me)
    a = new_account(me)
    spend(me, a, 8_000_00, c["transport"], "2026-10-02")
    assert (
        me.patch("/api/me/preferences", {"budget_alert_thresholds": [50, 100]}).status_code == 200
    )
    p = save_lines(me, create(me), [{"category_id": c["transport"], "planned_minor": 10_000_00}])
    assert p["budget"]["alert_thresholds"] == [50, 100]
    assert line(p, "Transport")["threshold_reached"] == 50
    r = me.patch(f"/api/budgets/{p['budget']['id']}", {"alert_thresholds": [100, 80]})
    assert r.status_code == 200
    assert r.json()["budget"]["alert_thresholds"] == [80, 100]
    assert r.json()["budget"]["thresholds_overridden"] is True
    assert line(r.json(), "Transport")["threshold_reached"] == 80
    back = me.patch(f"/api/budgets/{p['budget']['id']}", {"alert_thresholds": None}).json()
    assert back["budget"]["alert_thresholds"] == [50, 100]
    for bad in ([], [0], [201], [1, 2, 3, 4, 5, 6], ["90"]):
        res = me.patch(f"/api/budgets/{p['budget']['id']}", {"alert_thresholds": bad})
        assert res.status_code == 422, bad


def test_rollover_chains_and_never_carries_overspending(me):
    c = cats(me)
    a = new_account(me)
    for m in (AUG, SEP, OCT):
        save_lines(
            me,
            create(me, month=m, rollover_enabled=True),
            [
                {"category_id": c["transport"], "planned_minor": 10_000_00},
                {"category_id": c["groceries"], "planned_minor": 10_000_00},
            ],
        )
    spend(me, a, 4_000_00, c["transport"], "2026-08-10")  # Aug: 6,000 unspent
    spend(me, a, 12_000_00, c["transport"], "2026-09-10")  # Sep: available 16,000 → 4,000 left
    spend(me, a, 25_000_00, c["groceries"], "2026-09-10")  # overspent by 5,000 (after Aug's 10k)
    p = me.get("/api/budgets?month=2026-10-01").json()
    assert line(p, "Transport")["rollover_minor"] == 4_000_00
    assert line(p, "Transport")["available_minor"] == 14_000_00
    assert line(p, "Food & groceries")["rollover_minor"] == 0
    # editing an old transaction updates the carry-over live
    aug = me.get("/api/transactions?date_from=2026-08-01&date_to=2026-08-31").json()["items"][0]
    assert me.patch(f"/api/transactions/{aug['id']}", {"amount_minor": 1_000_00}).status_code == 200
    p = me.get("/api/budgets?month=2026-10-01").json()
    assert line(p, "Transport")["rollover_minor"] == 7_000_00
    # switching carry-over off in October removes it
    off = me.patch(f"/api/budgets/{p['budget']['id']}", {"rollover_enabled": False}).json()
    assert line(off, "Transport")["rollover_minor"] == 0


def test_rollover_needs_previous_budget(me):
    c = cats(me)
    p = save_lines(
        me,
        create(me, rollover_enabled=True),
        [{"category_id": c["transport"], "planned_minor": 10_000_00}],
    )
    assert line(p, "Transport")["rollover_minor"] == 0


def test_copy_previous_and_suggestions(me):
    c = cats(me)
    a = new_account(me)
    for m, amount in ((JUL, 30_000_00), (AUG, 45_000_50), (SEP, 0)):
        if amount:
            spend(me, a, amount, c["groceries"], m.replace("-01", "-12"))
    spend(me, a, 90_000_00, c["shopping"], "2026-08-12")  # one-off: no suggestion
    spend(me, a, 5_000_00, c["groceries"], "2026-10-02")  # current month is never used

    s = me.get("/api/budgets/suggestions?month=2026-10-01").json()
    assert s["based_on"] == [JUL, AUG, SEP]
    assert [x["name"] for x in s["suggestions"]] == ["Food & groceries"]
    g = s["suggestions"][0]
    assert g["amount_minor"] == 26_000_00
    assert [m["net_spending"] for m in g["months"]] == [30_000_00, 45_000_50, 0]

    oct_page = create(me, start="suggested")
    assert line(oct_page, "Food & groceries")["planned_minor"] == 26_000_00
    nov = create(me, month="2026-11-01", start="copy_previous")
    assert [x["name"] for x in nov["budget"]["lines"]] == ["Food & groceries"]
    assert nov["previous_month_has_budget"] is True
    # future months still base suggestions on complete months only
    assert me.get("/api/budgets/suggestions?month=2027-03-01").json()["based_on"] == [
        JUL,
        AUG,
        SEP,
    ]
    r = me.post("/api/budgets", {"month": "2026-06-01", "start": "copy_previous"})
    assert r.status_code == 422


def test_validation(me):
    c = cats(me)
    p = create(me, month="2026-10-20")  # any day is normalised to the 1st
    assert p["month"] == OCT
    assert me.post("/api/budgets", {"month": OCT}).status_code == 422  # one per month
    bid = p["budget"]["id"]
    bad = [
        [{"category_id": c["salary"], "planned_minor": 100}],  # income category
        [{"category_id": c["transfers"], "planned_minor": 100}],
        [{"category_id": c["transport"], "planned_minor": 0}],
        [{"category_id": c["transport"], "planned_minor": "100"}],
        [{"category_id": c["transport"], "planned_minor": 10**15 + 1}],
        [{"category_id": c["transport"], "planned_minor": 1}] * 2,
        [{"category_id": None, "planned_minor": 1}] * 2,
        [{"category_id": "00000000-0000-0000-0000-000000000000", "planned_minor": 1}],
    ]
    for lines in bad:
        r = me.put(f"/api/budgets/{bid}/lines", {"lines": lines})
        assert r.status_code in (404, 422), (lines, r.text)
    assert me.get("/api/budgets?month=1999-12-01").status_code == 422


def test_archived_category_rules(me):
    c = cats(me)
    p = save_lines(me, create(me), [{"category_id": c["transport"], "planned_minor": 1_000_00}])
    assert me.patch(f"/api/categories/{c['transport']}", {"is_archived": True}).status_code == 200
    assert me.patch(f"/api/categories/{c['shopping']}", {"is_archived": True}).status_code == 200
    # an existing line on an archived category can stay; a new one can't be added
    keep = [{"category_id": c["transport"], "planned_minor": 2_000_00}]
    assert me.put(f"/api/budgets/{p['budget']['id']}/lines", {"lines": keep}).status_code == 200
    add_new = [*keep, {"category_id": c["shopping"], "planned_minor": 1_00}]
    assert me.put(f"/api/budgets/{p['budget']['id']}/lines", {"lines": add_new}).status_code == 422
    nov = create(me, month="2026-11-01", start="copy_previous")
    assert nov["budget"]["lines"] == []  # archived categories are not copied


def test_category_delete_and_merge_keep_budgets_consistent(me):
    c = cats(me)
    r = me.post("/api/categories", {"name": "Generator diesel", "kind": "expense"})
    diesel = r.json()["id"]
    p = save_lines(
        me,
        create(me),
        [
            {"category_id": diesel, "planned_minor": 5_000_00},
            {"category_id": c["utilities"], "planned_minor": 20_000_00},
        ],
    )
    assert me.delete(f"/api/categories/{diesel}").status_code == 422
    assert (
        me.post(f"/api/categories/{diesel}/merge", {"into_id": c["utilities"]}).status_code == 200
    )
    p = me.get("/api/budgets").json()
    assert [(x["name"], x["planned_minor"]) for x in p["budget"]["lines"]] == [
        ("Electricity & utilities", 25_000_00)
    ]


def test_delete_budget_and_isolation(me, make_user, api_factory):
    c = cats(me)
    p = save_lines(me, create(me), [{"category_id": c["transport"], "planned_minor": 1_000_00}])
    bid = p["budget"]["id"]

    make_user("nosy@example.com")
    other = api_factory()
    other.login("nosy@example.com")
    assert other.get("/api/budgets?month=2026-10-01").json()["budget"] is None
    assert other.patch(f"/api/budgets/{bid}", {"rollover_enabled": True}).status_code == 404
    assert other.put(f"/api/budgets/{bid}/lines", {"lines": []}).status_code == 404
    assert other.delete(f"/api/budgets/{bid}").status_code == 404
    # nor can they put my category into their budget
    theirs = other.post("/api/budgets", {"month": OCT}).json()
    r = other.put(
        f"/api/budgets/{theirs['budget']['id']}/lines",
        {"lines": [{"category_id": c["transport"], "planned_minor": 1}]},
    )
    assert r.status_code == 404

    assert me.delete(f"/api/budgets/{bid}").status_code == 204
    assert me.get("/api/budgets").json()["budget"] is None
    assert db_scalar("select count(*) from audit_events where action like 'budget.%'") >= 3


def test_export_and_account_deletion_include_budgets(me, make_user):
    c = cats(me)
    save_lines(me, create(me), [{"category_id": c["transport"], "planned_minor": 1_000_00}])
    data = me.get("/api/me/export").json()
    assert data["budgets"][0]["lines"] == [{"category": "Transport", "planned_minor": 1_000_00}]
    make_user("admin2@example.com", role="admin")
    r = me.post("/api/me/delete", {"password": PASSWORD, "confirm": "DELETE"})
    assert r.status_code == 200
    assert db_scalar("select count(*) from budgets") == 0
    assert db_scalar("select count(*) from budget_lines") == 0


def test_budgets_require_login(api):
    assert api.get("/api/budgets").status_code == 401
