"""Pure ingestion tests: readers, date/amount parsing, column detection, normalisation."""

from datetime import date

import pytest

from app.ingestion.detect import find_header_row, guess_mapping, role_for, validate_mapping
from app.ingestion.normalise import mask_sensitive, normalise, suggest_kind
from app.ingestion.parse import guess_date_order, parse_amount, parse_date, parse_signed
from app.ingestion.readers import ReadError, read_any
from tests import statement_fixtures as fx

# ---------- dates ----------


@pytest.mark.parametrize(
    ("raw", "order", "expected"),
    [
        ("24/10/2026", "DMY", date(2026, 10, 24)),
        ("05/10/2026", "DMY", date(2026, 10, 5)),
        ("10/05/2026", "MDY", date(2026, 10, 5)),
        ("24-10-2026", "DMY", date(2026, 10, 24)),
        ("24.10.26", "DMY", date(2026, 10, 24)),
        ("2026-10-24", "DMY", date(2026, 10, 24)),
        ("2026-10-24 13:45:00", "DMY", date(2026, 10, 24)),
        ("2026/10/24", "DMY", date(2026, 10, 24)),
        ("24-Oct-2026", "MDY", date(2026, 10, 24)),
        ("24 OCT 26", "DMY", date(2026, 10, 24)),
        ("24-Sept-2026", "DMY", date(2026, 9, 24)),
        ("Oct 24, 2026", "DMY", date(2026, 10, 24)),
        ("24/10/2026 09:12", "DMY", date(2026, 10, 24)),
        ("46319", "DMY", date(2026, 10, 24)),  # Excel serial as text
    ],
)
def test_parse_date(raw, order, expected):
    assert parse_date(raw, order) == expected


@pytest.mark.parametrize(
    "raw", ["", "31/02/2026", "hello", "13/13/2026", "24-Foo-2026", "1/1/1800"]
)
def test_parse_date_rejects(raw):
    assert parse_date(raw) is None


def test_guess_date_order():
    assert guess_date_order(["05/10/2026", "24/10/2026"]) == "DMY"
    assert guess_date_order(["10/05/2026", "10/24/2026"]) == "MDY"
    assert guess_date_order(["01/02/2026"]) == "DMY"  # ambiguous → Nigerian default


# ---------- amounts ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("25,000.50", (2500050, False)),
        ("₦25,000.50", (2500050, False)),
        ("NGN 1,000", (100000, False)),
        ("N1,000.00", (100000, False)),
        ("(1,200.00)", (120000, True)),
        ("-500", (50000, True)),
        ("+750.5", (75050, False)),
        ("1,000.00 DR", (100000, True)),
        ("750CR", (75000, False)),
        ("0.29", (29, False)),
        (".5", (50, False)),
        ("25000.5", (2500050, False)),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw", ["", "-", "0.00", "0", "nil", "N/A"])
def test_parse_amount_blank_like(raw):
    assert parse_amount(raw) is None


@pytest.mark.parametrize("raw", ["abc", "1.234", "12,50.5.0", "1e5"])
def test_parse_amount_rejects(raw):
    with pytest.raises(ValueError):
        parse_amount(raw)


def test_parse_signed_balance():
    assert parse_signed("-1,000.00") == -100000
    assert parse_signed("0.00") == 0
    assert parse_signed("") is None


# ---------- masking & kinds ----------


def test_masks_nuban_and_card_numbers_keeping_last4():
    s = mask_sensitive("TRF TO JOHN/0123456789 CARD 5399 8312 3456 7895 REF 987654321098765432109")
    assert "0123456789" not in s and "••••••6789" in s
    assert "5399 8312 3456 7895" not in s and "••••7895" in s
    assert "987654321098765432109" in s  # long session id is not an account number


def test_non_luhn_16_digits_kept():
    assert "1234567890123456" in mask_sensitive("REF 1234567890123456")


@pytest.mark.parametrize(
    ("direction", "narr", "kind"),
    [
        ("debit", "SMS ALERT CHARGES", "fee"),
        ("debit", "VAT ON CHARGES", "fee"),
        ("debit", "STAMP DUTY", "fee"),
        ("debit", "ELECTRONIC MONEY TRANSFER LEVY", "fee"),
        ("debit", "SCHOOL FEES PAYMENT", "expense"),
        ("debit", "POS PURCHASE SHOPRITE", "expense"),
        ("credit", "SALARY", "income"),
        ("credit", "REFUND FROM JUMIA", "refund"),
        ("credit", "REVERSAL WEB PURCHASE", "reversal"),
        ("credit", "RVSL NIP TRF", "reversal"),
    ],
)
def test_suggest_kind(direction, narr, kind):
    assert suggest_kind(direction, narr) == kind


# ---------- header detection ----------


@pytest.mark.parametrize(
    ("header", "role"),
    [
        ("Trans. Date", "date"),
        ("Value Date", "posting_date"),
        ("Narration", "description"),
        ("Reference/Narration", "description"),
        ("Transaction Reference", "reference"),
        ("Withdrawals (DR)", "debit"),
        ("Lodgements", "credit"),
        ("Money In", "credit"),
        ("Money Out", "debit"),
        ("Amount (NGN)", "amount"),
        ("Closing Balance", "balance"),
        ("DR/CR", "indicator"),
        ("Something else", None),
    ],
)
def test_role_for(header, role):
    assert role_for(header) == role


def test_find_header_row_skips_preamble():
    grid = read_any(fx.csv_debit_credit_newest_first(), "s.csv").rows
    assert find_header_row(grid) == 4


def test_no_header_found():
    m = guess_mapping([["hello", "world"], ["1", "2"]])
    assert m["header_row"] is None
    assert validate_mapping(m, 2)


# ---------- readers + full normalisation, every layout ----------

LAYOUTS = {
    "csv_debit_credit": (fx.csv_debit_credit_newest_first, "csv", "debit_credit"),
    "csv_signed": (fx.csv_signed_amount, "csv", "signed"),
    "csv_indicator": (fx.csv_indicator_semicolon, "csv", "indicator"),
    "xlsx": (fx.xlsx_money_in_out, "xlsx", "debit_credit"),
    "xls": (fx.xls_debit_credit, "xls", "debit_credit"),
}


@pytest.mark.parametrize("name", LAYOUTS)
def test_every_layout_parses_identically(name):
    make, adapter, mode = LAYOUTS[name]
    grid = read_any(make(), f"x.{adapter}")
    assert grid.adapter == adapter
    m = guess_mapping(grid.rows)
    assert m["amount_mode"] == mode, m
    assert validate_mapping(m, max(len(r) for r in grid.rows)) == []
    res = normalise(grid.rows, m, account_id=7)
    good = [r for r in res.rows if r.error is None]
    assert len(good) == len(fx.ROWS), [r.error for r in res.rows]
    by_day = sorted(good, key=lambda r: (r.transaction_date, r.row_number))
    total = sum(r.amount_minor if r.direction == "credit" else -r.amount_minor for r in good)
    assert total == fx.CLOSING - fx.OPENING
    assert {r.transaction_date for r in by_day} == {d for d, *_ in fx.ROWS}
    if name != "csv_indicator":  # that layout has no balance column
        assert res.opening_balance_minor == fx.OPENING
        assert res.closing_balance_minor == fx.CLOSING
        assert res.warnings == []
    kinds = sorted(r.suggested_kind for r in good)
    assert kinds.count("fee") == 2 and kinds.count("reversal") == 1 and kinds.count("income") == 1
    # twins get different fingerprints; every fingerprint is unique within the file
    assert len({r.fingerprint for r in good}) == len(good)
    # sensitive numbers are masked in stored narration
    assert all("0123456789" not in (r.narration or "") for r in good)
    assert all("5399831234567895" not in (r.narration or "") for r in good)


def test_fingerprints_stable_across_formats_and_reimports():
    def fps(make):
        g = read_any(make(), "f").rows
        return {r.fingerprint for r in normalise(g, guess_mapping(g), 1).rows}

    assert fps(fx.csv_debit_credit_newest_first) == fps(fx.csv_debit_credit_newest_first)
    assert fps(fx.xlsx_money_in_out) == fps(fx.xls_debit_credit)


def test_fingerprint_depends_on_account():
    g = read_any(fx.csv_signed_amount(), "f").rows
    m = guess_mapping(g)
    a = {r.fingerprint for r in normalise(g, m, 1).rows}
    b = {r.fingerprint for r in normalise(g, m, 2).rows}
    assert a.isdisjoint(b)


def test_swapped_columns_detected():
    g = read_any(fx.csv_debit_credit_newest_first(), "f").rows
    m = guess_mapping(g)
    m["columns"]["debit"], m["columns"]["credit"] = m["columns"]["credit"], m["columns"]["debit"]
    res = normalise(g, m, 1)
    assert any("swapped" in w for w in res.warnings)
    assert res.closing_balance_minor is None


def test_bad_rows_become_errors_not_crashes():
    data = (
        b"Date,Narration,Debit,Credit,Balance\n"
        b"01/10/2026,OK,100.00,,\n"
        b"99/99/2026,BAD DATE,100.00,,\n"
        b"02/10/2026,BAD AMOUNT,abc,,\n"
        b"03/10/2026,BOTH,1.00,2.00,\n"
        b"Opening balance,,,,5000\n"
        b"04/10/2026,TOO PRECISE,1.234,,\n"
    )
    g = read_any(data, "f.csv").rows
    res = normalise(g, guess_mapping(g), 1)
    errs = {r.narration: r.error for r in res.rows if r.error}
    assert set(errs) == {"BAD DATE", "BAD AMOUNT", "BOTH", "TOO PRECISE"}
    assert res.skipped == 1  # the opening-balance line
    assert sum(1 for r in res.rows if r.error is None) == 1


@pytest.mark.parametrize(
    ("data", "msg"),
    [
        (b"<html><table><tr><td>x</td></tr></table></html>", "web page"),
        (b"%PDF-1.7 ...", "PDF"),
        (b"\x00\x01\x02binary", "isn't supported"),
        (b"", "empty"),
        (b"PK\x03\x04garbage", "damaged"),
    ],
)
def test_reader_rejections(data, msg):
    with pytest.raises(ReadError, match=msg):
        read_any(data, "x")


def test_row_limit(monkeypatch):
    monkeypatch.setattr("app.ingestion.readers.MAX_ROWS", 5)
    data = ("Date,Amount\n" + "01/10/2026,1\n" * 10).encode()
    with pytest.raises(ReadError, match="more than"):
        read_any(data, "x.csv")


def test_xlsx_ignores_hidden_sheets_and_keeps_exact_money():
    g = read_any(fx.xlsx_money_in_out(), "x.xlsx")
    assert g.sheet_name == "Statement"
    assert [
        "2026-10-02",
        "POS PURCHASE SHOPRITE LEKKI 5399831234567895",
        "",
        "25000.5",
        "524999.5",
    ] in g.rows  # raw grid; masking happens during normalisation


def test_cp1252_csv():
    data = "Date,Narration,Amount\n01/10/2026,Caf\xe9 Lagos,-1000\n".encode("cp1252")
    g = read_any(data, "x.csv").rows
    assert g[1][1] == "Café Lagos"
