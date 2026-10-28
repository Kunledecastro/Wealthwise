"""Dashboard overview and report exports (Phase 5)."""

import csv
import io

import pytest

from tests.conftest import db_exec, db_scalar
from tests.test_finance import add, new_account

OCT = "date_from=2026-10-01&date_to=2026-10-31"


@pytest.fixture
def me(api, make_user):
    make_user("rep@example.com")
    api.login("rep@example.com")
    return api


def seed(api):
    a = new_account(api)
    b = new_account(api, "Kuda", 0)
    add(api, a, "income", 500_000_00, merchant="SALARY ACME", transaction_date="2026-10-01")
    add(api, a, "expense", 20_000_00, merchant="Shoprite Lekki", transaction_date="2026-10-02")
    add(api, a, "expense", 5_000_00, merchant="Shoprite Ikeja", transaction_date="2026-10-02")
    add(api, b, "expense", 3_500_00, merchant="Bolt ride", transaction_date="2026-10-05")
    add(api, a, "refund", 1_000_00, merchant="Shoprite Lekki", transaction_date="2026-10-06")
    add(api, a, "fee", 50_00, narration="SMS ALERT", transaction_date="2026-10-06")
    add(api, a, "expense", 9_999_00, status="failed", transaction_date="2026-10-07")
    add(api, a, "expense", 2_000_00, status="pending", transaction_date="2026-10-08")
    add(api, a, "expense", 10_000_00, merchant="Shoprite Lekki", transaction_date="2026-09-03")
    add(api, a, "income", 400_000_00, merchant="SALARY ACME", transaction_date="2026-09-01")
    return a, b


def test_overview_totals_series_and_comparison(me):
    seed(me)
    r = me.get(f"/api/reports/overview?{OCT}")
    assert r.status_code == 200, r.text
    o = r.json()
    s = o["summary"]
    assert s["income"] == 500_000_00
    assert s["gross_spending"] == 20_000_00 + 5_000_00 + 3_500_00 + 50_00
    assert s["net_spending"] == s["gross_spending"] - 1_000_00
    assert s["pending_out"] == 2_000_00
    assert o["granularity"] == "day" and len(o["series"]) == 31
    # buckets add up to the period (R16)
    assert sum(p["net_spending"] for p in o["series"]) == s["net_spending"]
    assert sum(p["income"] for p in o["series"]) == s["income"]
    assert o["series"][1]["date_from"] == "2026-10-02"
    assert o["series"][1]["gross_spending"] == 25_000_00
    # R18: whole October vs whole September
    assert (o["previous"]["date_from"], o["previous"]["date_to"]) == ("2026-09-01", "2026-09-30")
    assert o["previous"]["summary"]["net_spending"] == 10_000_00
    assert o["changes"]["income"] == 25
    assert o["changes"]["net_spending"] == round((s["net_spending"] - 10_000_00) / 10_000_00 * 100)
    assert o["generated_on"]


def test_overview_categories_and_merchants_add_up(me):
    seed(me)
    o = me.get(f"/api/reports/overview?{OCT}").json()
    spend = o["spending_by_category"]
    assert sum(c["net_spending"] for c in spend) == o["summary"]["net_spending"]
    assert spend[0]["name"] == "Food & groceries"
    assert spend[0]["net_spending"] == 24_000_00
    assert [c["name"] for c in o["income_by_category"]] == ["Salary"]
    merchants = o["top_merchants"]
    total = sum(m["net_spending"] for m in merchants) + (
        o["other_merchants"]["net_spending"] if o["other_merchants"] else 0
    )
    assert total == o["summary"]["net_spending"]
    assert merchants[0]["merchant"] == "SHOPRITE LEKKI"
    assert merchants[0]["net_spending"] == 19_000_00
    assert all(m["merchant"] for m in merchants)  # unrecognised spending is never ranked


def test_overview_granularity_rules(me):
    seed(me)
    assert (
        me.get("/api/reports/overview?date_from=2026-08-01&date_to=2026-10-31").json()[
            "granularity"
        ]
        == "week"
    )
    y = me.get("/api/reports/overview?date_from=2026-01-01&date_to=2026-12-31").json()
    assert y["granularity"] == "month" and len(y["series"]) == 12
    assert (y["previous"]["date_from"], y["previous"]["date_to"]) == ("2025-01-01", "2025-12-31")
    w = me.get(f"/api/reports/overview?{OCT}&granularity=week").json()
    assert w["series"][0]["date_from"] == "2026-10-01"  # clipped partial week
    assert w["series"][1]["date_from"] == "2026-10-05"  # Monday (default week start)
    long_days = "/api/reports/overview?date_from=2020-01-01&date_to=2026-01-01&granularity=day"
    assert me.get(long_days).status_code == 422
    assert (
        me.get("/api/reports/overview?date_from=2026-10-02&date_to=2026-10-01").status_code == 422
    )
    assert (
        me.get("/api/reports/overview?date_from=2000-01-01&date_to=2026-01-01").status_code == 422
    )
    assert me.get(f"/api/reports/overview?{OCT}&granularity=year").status_code == 422


def test_week_start_preference_is_used(me):
    seed(me)
    assert me.patch("/api/me/preferences", {"week_start": 7}).status_code == 200
    w = me.get(f"/api/reports/overview?{OCT}&granularity=week").json()
    assert w["week_start"] == 7
    assert w["series"][1]["date_from"] == "2026-10-04"  # Sunday


def test_account_filter_and_isolation(me, make_user, api_factory):
    a, b = seed(me)
    o = me.get(f"/api/reports/overview?{OCT}&account_id={b['id']}").json()
    assert o["summary"]["net_spending"] == 3_500_00
    assert [x["id"] for x in o["accounts"]] == [b["id"]]

    make_user("other@example.com")
    other = api_factory()
    other.login("other@example.com")
    assert other.get(f"/api/reports/overview?{OCT}&account_id={a['id']}").status_code == 404
    mine = other.get(f"/api/reports/overview?{OCT}").json()
    assert mine["summary"]["transaction_count"] == 0
    assert mine["top_merchants"] == [] and mine["accounts"] == []
    assert other.get(f"/api/reports/export.csv?{OCT}&account_id={a['id']}").status_code == 404


@pytest.fixture
def usd_enabled():
    existed = db_scalar("select count(*) from currencies where code = 'USD'")
    was_active = db_scalar(
        "select coalesce(bool_or(is_active), false) from currencies where code = 'USD'"
    )
    db_exec(
        "insert into currencies (code, name, symbol, exponent, is_active) "
        "values ('USD', 'US dollar', '$', 2, true) "
        "on conflict (code) do update set is_active = true"
    )
    yield
    # accounts are truncated after the test; put the currency back as it was
    db_exec("update currencies set is_active = :a where code = 'USD'", a=was_active)
    if not existed:
        db_exec(
            "delete from currencies where code = 'USD' and not exists "
            "(select 1 from accounts where currency = 'USD')"
        )


def test_other_currencies_are_flagged_not_added(me, usd_enabled):
    a = new_account(me)
    usd = new_account(me, "Dom account", 0, currency="USD")
    add(me, a, "expense", 1_000_00, transaction_date="2026-10-03")
    add(me, usd, "expense", 50_00, transaction_date="2026-10-03")
    o = me.get(f"/api/reports/overview?{OCT}").json()
    assert o["summary"]["gross_spending"] == 1_000_00
    assert o["other_currencies"] == ["USD"]
    u = me.get(f"/api/reports/overview?{OCT}&currency=usd").json()
    assert u["currency"] == "USD" and u["summary"]["gross_spending"] == 50_00


def test_empty_overview(me):
    o = me.get(f"/api/reports/overview?{OCT}").json()
    assert o["summary"]["transaction_count"] == 0
    assert o["changes"] == {
        "income": None,
        "net_spending": None,
        "net_cash_flow": None,
        "transaction_count": None,
    }
    assert o["balances_are_estimated"] is True
    assert o["other_merchants"] is None


def rows(resp):
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    return list(csv.reader(io.StringIO(resp.text.lstrip("﻿"))))


def test_csv_exports(me):
    seed(me)
    period = rows(me.get(f"/api/reports/export.csv?report=period&{OCT}"))
    assert period[0][0] == "Wealthwise period report"
    assert period[1][:3] == ["from", "to", "income"]
    assert len(period) == 2 + 31 + 1
    total = period[-1]
    assert total[0] == "total" and total[2] == "500000.00"
    assert total[5] == f"{(28_550_00 - 1_000_00) // 100}.{(28_550_00 - 1_000_00) % 100:02d}"
    # the daily rows add up to the total row (exact decimals, no float drift)
    assert sum(int(r[5].replace(".", "")) for r in period[2:-1]) == int(total[5].replace(".", ""))

    cats = rows(me.get(f"/api/reports/export.csv?report=categories&{OCT}"))
    assert ["spending", "Food & groceries", "24000.00", "3"] in cats
    assert ["income", "Salary", "500000.00", "1"] in cats

    merch = rows(me.get(f"/api/reports/export.csv?report=merchants&{OCT}"))
    assert merch[2] == ["SHOPRITE LEKKI", "19000.00", "2"]
    assert me.get(f"/api/reports/export.csv?report=secrets&{OCT}").status_code == 422
    assert db_scalar("select count(*) from audit_events where action='data.export_report_csv'") == 3


def test_csv_neutralises_formulas(me):
    a = new_account(me, "=HYPERLINK(evil)")
    add(me, a, "expense", 100, merchant="=cmd|calc", transaction_date="2026-10-03")
    acct = rows(me.get(f"/api/reports/export.csv?report=period&{OCT}&account_id={a['id']}"))
    assert "'=HYPERLINK" in acct[0][2]
    merch = rows(me.get(f"/api/reports/export.csv?report=merchants&{OCT}"))
    assert all(not r[0].startswith("=") for r in merch)


def test_merchant_filter_drills_down(me):
    seed(me)
    r = me.get(
        "/api/transactions?merchant=SHOPRITE%20LEKKI&date_from=2026-10-01&date_to=2026-10-31"
    )
    assert r.json()["total"] == 2
    none = me.get("/api/transactions?merchant=none&date_from=2026-10-01&date_to=2026-10-31").json()
    assert none["total"] == 2  # the failed and pending rows have no merchant or description


def test_reports_require_login(api):
    assert api.get(f"/api/reports/overview?{OCT}").status_code == 401
    assert api.get(f"/api/reports/export.csv?{OCT}").status_code == 401
