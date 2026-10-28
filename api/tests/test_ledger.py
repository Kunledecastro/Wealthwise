"""Ledger engine tests — one or more per rule in app/ledger/RULES.md, plus property tests.
Pure functions: no database needed."""

from datetime import date, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.ledger.engine import Entry, account_balance, summarize, total_balances

D = date(2026, 10, 15)


def e(kind, direction, amount, status="posted", d=D, cur="NGN", acct=1, deleted=False):
    return Entry(kind, direction, amount, cur, status, d, acct, deleted)


def S(entries, **kw):
    return summarize(entries, **kw).get("NGN")


# ---------- Entry validation ----------


@pytest.mark.parametrize("amount", [0, -5])
def test_amount_must_be_positive(amount):
    with pytest.raises(ValueError):
        e("expense", "debit", amount)


def test_amount_must_be_int_not_float():
    with pytest.raises(TypeError):
        e("expense", "debit", 10.5)
    with pytest.raises(TypeError):
        e("expense", "debit", True)


def test_direction_validated():
    with pytest.raises(ValueError):
        e("expense", "out", 100)


def test_unknown_kind_fails_loudly():
    with pytest.raises(ValueError):
        summarize([e("bonus", "credit", 1)])


# ---------- R1-R12 ----------


def test_r1_r6_r7_basic_income_and_spending():
    s = S([e("income", "credit", 500_000_00), e("expense", "debit", 12_500_50)])
    assert s.income == 500_000_00
    assert s.gross_spending == 12_500_50
    assert s.net_cash_flow == 500_000_00 - 12_500_50


def test_r2_pending_reported_separately():
    s = S(
        [
            e("expense", "debit", 1000, "pending"),
            e("income", "credit", 700, "pending"),
            e("expense", "debit", 50),
        ]
    )
    assert s.gross_spending == 50
    assert (s.pending_out, s.pending_in) == (1000, 700)
    assert s.transaction_count == 1


def test_r3_failed_ignored():
    s = S([e("expense", "debit", 1000, "failed"), e("income", "credit", 5, "failed")])
    assert s is None or (s.gross_spending, s.income, s.pending_out) == (0, 0, 0)


def test_r4_deleted_ignored():
    s = S([e("expense", "debit", 1000, deleted=True)])
    assert s is None


def test_r5_reversal_pair_cancels():
    original = e("expense", "debit", 9999, status="reversed")
    reversal = e("reversal", "credit", 9999)
    assert S([original, reversal]) is None
    bal = account_balance(
        currency="NGN", opening_minor=100, opening_date=D, entries=[original, reversal]
    )
    assert bal.posted_minor == 100


def test_r7_fees_are_spending_and_reported():
    s = S([e("fee", "debit", 52_50), e("expense", "debit", 1000)])
    assert s.gross_spending == 52_50 + 1000
    assert s.fees == 52_50


def test_r8_refund_reduces_spending_not_income():
    s = S([e("expense", "debit", 20_000_00), e("refund", "credit", 5_000_00)])
    assert s.income == 0
    assert s.refunds == 5_000_00
    assert s.net_spending == 15_000_00
    assert s.net_cash_flow == -15_000_00


def test_r8_refund_in_later_period_reduces_that_period():
    buy = e("expense", "debit", 3000, d=date(2026, 9, 30))
    refund = e("refund", "credit", 3000, d=date(2026, 10, 2))
    oct_ = S([buy, refund], date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
    assert oct_.net_spending == -3000  # money came back this month
    sep = S([buy, refund], date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    assert sep.net_spending == 3000


def test_r9_transfers_not_income_or_spending_but_move_balances():
    out_leg = e("transfer", "debit", 50_000_00, acct=1)
    in_leg = e("transfer", "credit", 50_000_00, acct=2)
    s = S([out_leg, in_leg])
    assert (s.income, s.gross_spending, s.net_cash_flow) == (0, 0, 0)
    a = account_balance(currency="NGN", opening_minor=60_000_00, opening_date=D, entries=[out_leg])
    b = account_balance(currency="NGN", opening_minor=0, opening_date=D, entries=[in_leg])
    assert (a.posted_minor, b.posted_minor) == (10_000_00, 50_000_00)
    assert total_balances([a, b]) == {"NGN": 60_000_00}


def test_r10_adjustment_moves_balance_only():
    adj = e("adjustment", "credit", 777)
    s = S([adj])
    assert (s.income, s.gross_spending) == (0, 0)
    assert (
        account_balance(currency="NGN", opening_minor=0, opening_date=D, entries=[adj]).posted_minor
        == 777
    )


def test_r12_period_inclusive_both_ends():
    entries = [
        e("expense", "debit", 1, d=date(2026, 10, 1)),
        e("expense", "debit", 10, d=date(2026, 10, 31)),
        e("expense", "debit", 100, d=date(2026, 11, 1)),
        e("expense", "debit", 1000, d=date(2026, 9, 30)),
    ]
    s = S(entries, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
    assert s.gross_spending == 11


def test_currencies_never_mixed():
    out = summarize([e("expense", "debit", 100, cur="NGN"), e("expense", "debit", 7, cur="USD")])
    assert out["NGN"].gross_spending == 100 and out["USD"].gross_spending == 7
    a = account_balance(currency="NGN", opening_minor=5, opening_date=D, entries=[])
    b = account_balance(currency="USD", opening_minor=5, opening_date=D, entries=[])
    assert total_balances([a, b]) == {"NGN": 5, "USD": 5}


def test_balance_rejects_other_currency_entries():
    with pytest.raises(ValueError):
        account_balance(
            currency="NGN",
            opening_minor=0,
            opening_date=D,
            entries=[e("expense", "debit", 1, cur="USD")],
        )


# ---------- B1-B3 ----------


def test_b1_transactions_before_opening_date_excluded_from_balance():
    before = e("expense", "debit", 400, d=D - timedelta(days=1))
    on = e("expense", "debit", 100, d=D)
    bal = account_balance(currency="NGN", opening_minor=1000, opening_date=D, entries=[before, on])
    assert bal.posted_minor == 900
    # ...but still appear in period reports
    assert S([before, on]).gross_spending == 500


def test_b1_balance_can_go_negative():
    bal = account_balance(
        currency="NGN", opening_minor=0, opening_date=D, entries=[e("expense", "debit", 5000)]
    )
    assert bal.posted_minor == -5000


def test_b2_all_posted_kinds_move_balance():
    entries = [
        e("income", "credit", 1000),
        e("expense", "debit", 300),
        e("fee", "debit", 50),
        e("refund", "credit", 100),
        e("transfer", "debit", 200),
        e("adjustment", "credit", 25),
    ]
    bal = account_balance(currency="NGN", opening_minor=0, opening_date=D, entries=entries)
    assert bal.posted_minor == 1000 - 300 - 50 + 100 - 200 + 25


def test_b3_available_including_pending():
    entries = [
        e("expense", "debit", 300, "pending"),
        e("income", "credit", 1000, "pending"),
        e("expense", "debit", 100),
    ]
    bal = account_balance(currency="NGN", opening_minor=500, opening_date=D, entries=entries)
    assert bal.posted_minor == 400
    assert bal.available_incl_pending == 400 + 1000 - 300


def test_as_of_date_cutoff():
    entries = [e("expense", "debit", 100, d=D), e("expense", "debit", 10, d=D + timedelta(days=5))]
    bal = account_balance(currency="NGN", opening_minor=0, opening_date=D, entries=entries, as_of=D)
    assert bal.posted_minor == -100


def test_large_amounts_exact():
    big = 10**15
    s = S([e("income", "credit", big), e("income", "credit", big), e("expense", "debit", 1)])
    assert s.net_cash_flow == 2 * 10**15 - 1  # exact integer arithmetic, no float drift


# ---------- property tests ----------

kinds = st.sampled_from(["income", "expense", "fee", "refund", "adjustment"])
statuses = st.sampled_from(["posted", "pending", "failed"])
amounts = st.integers(min_value=1, max_value=10**12)
dates = st.dates(min_value=date(2026, 1, 1), max_value=date(2026, 12, 31))

DIRECTION = {"income": "credit", "refund": "credit", "expense": "debit", "fee": "debit"}


@st.composite
def entries(draw):
    k = draw(kinds)
    direction = DIRECTION.get(k) or draw(st.sampled_from(["debit", "credit"]))
    return Entry(k, direction, draw(amounts), "NGN", draw(statuses), draw(dates), 1)


@settings(max_examples=200)
@given(st.lists(entries(), max_size=40))
def test_prop_order_does_not_matter(es):
    a = summarize(es).get("NGN")
    b = summarize(list(reversed(es))).get("NGN")
    assert (a.as_dict() if a else None) == (b.as_dict() if b else None)


@settings(max_examples=200)
@given(st.lists(entries(), max_size=40), amounts, dates)
def test_prop_transfer_pairs_never_change_pnl_or_total_balance(es, amt, d):
    base = summarize(es).get("NGN")
    pair = [
        Entry("transfer", "debit", amt, "NGN", "posted", d, 1),
        Entry("transfer", "credit", amt, "NGN", "posted", d, 2),
    ]
    after = summarize(es + pair).get("NGN")
    for f in ("income", "gross_spending", "refunds", "net_cash_flow", "pending_in"):
        assert getattr(after, f) == (getattr(base, f) if base else 0)
    opening = date(2026, 1, 1)
    b1 = account_balance(
        currency="NGN", opening_minor=0, opening_date=opening, entries=es + pair[:1]
    )
    b2 = account_balance(currency="NGN", opening_minor=0, opening_date=opening, entries=pair[1:])
    b0 = account_balance(currency="NGN", opening_minor=0, opening_date=opening, entries=es)
    assert b1.posted_minor + b2.posted_minor == b0.posted_minor


@settings(max_examples=200)
@given(st.lists(entries(), max_size=40), entries())
def test_prop_reversing_any_posted_entry_is_like_it_never_happened(es, x):
    x = Entry(x.kind, x.direction, x.amount_minor, "NGN", "posted", x.transaction_date, 1)
    without = summarize(es).get("NGN")
    reversed_x = Entry(
        x.kind, x.direction, x.amount_minor, "NGN", "reversed", x.transaction_date, 1
    )
    rev_row = Entry(
        "reversal",
        "credit" if x.direction == "debit" else "debit",
        x.amount_minor,
        "NGN",
        "posted",
        x.transaction_date,
        1,
    )
    with_rev = summarize([*es, reversed_x, rev_row]).get("NGN")
    assert (with_rev.as_dict() if with_rev else None) == (without.as_dict() if without else None)


@settings(max_examples=200)
@given(st.lists(entries(), max_size=40), st.integers(-(10**12), 10**12))
def test_prop_balance_equals_opening_plus_signed_posted(es, opening):
    d0 = date(2026, 1, 1)
    bal = account_balance(currency="NGN", opening_minor=opening, opening_date=d0, entries=es)
    expected = opening + sum(x.signed for x in es if x.status == "posted")
    assert bal.posted_minor == expected


@settings(max_examples=200)
@given(st.lists(entries(), max_size=40), dates, dates)
def test_prop_period_split_adds_up(es, d1, d2):
    lo = min(d1, d2)
    whole = summarize(es, date_from=date(2026, 1, 1), date_to=date(2026, 12, 31)).get("NGN")
    left = summarize(es, date_from=date(2026, 1, 1), date_to=lo).get("NGN")
    right = summarize(es, date_from=lo + timedelta(days=1), date_to=date(2026, 12, 31)).get("NGN")
    tot = (left.net_cash_flow if left else 0) + (right.net_cash_flow if right else 0)
    assert tot == (whole.net_cash_flow if whole else 0)


# ---------- B5 reconciliation ----------


def test_b5_reconcile_matches_and_breaks_after_old_edit():
    from app.ledger.engine import reconcile

    entries = [
        e("income", "credit", 1000, d=D),
        e("expense", "debit", 300, d=D + timedelta(days=1)),
    ]
    r = reconcile(
        currency="NGN",
        opening_minor=500,
        opening_date=D,
        entries=entries,
        as_of=D + timedelta(days=1),
        statement_minor=1200,
    )
    assert r.matches and r.difference_minor == 0
    # a later transaction doesn't affect a statement balance dated earlier
    later = [*entries, e("expense", "debit", 99, d=D + timedelta(days=5))]
    assert reconcile(
        currency="NGN",
        opening_minor=500,
        opening_date=D,
        entries=later,
        as_of=D + timedelta(days=1),
        statement_minor=1200,
    ).matches
    # editing an older transaction does
    edited = [e("income", "credit", 900, d=D), entries[1]]
    r2 = reconcile(
        currency="NGN",
        opening_minor=500,
        opening_date=D,
        entries=edited,
        as_of=D + timedelta(days=1),
        statement_minor=1200,
    )
    assert not r2.matches and r2.difference_minor == 100
