import pytest

from app.categorise.defaults import DEFAULT_CATEGORIES
from app.categorise.engine import (
    BUILTIN,
    CategoryInfo,
    Facts,
    Rule,
    categorise,
    needs_review,
    normalise_merchant,
    suggest_pattern,
)

CATS = {
    i + 1: CategoryInfo(i + 1, slug, kind, name)
    for i, (slug, name, kind, _) in enumerate(DEFAULT_CATEGORIES)
}
BY_SLUG = {c.slug: c.id for c in CATS.values()}


def facts(narration=None, kind="expense", direction="debit", merchant=None, **kw):
    return Facts(
        kind, direction, narration, merchant, normalise_merchant(merchant or narration), **kw
    )


# ---------------- merchant normalisation ----------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("POS PURCHASE SHOPRITE LEKKI ••••7895", "SHOPRITE LEKKI"),
        ("WEB PURCHASE NETFLIX", "NETFLIX"),
        ("NIP TRF TO KUDA/JOHN DOE/••••••6789", "KUDA"),
        ("POS/WEB PURCHASE @ CHICKEN REPUBLIC IKEJA 12345678", "CHICKEN REPUBLIC IKEJA"),
        ("BILL PAYMENT IKEJA ELECTRIC 04123456789", "IKEJA ELECTRIC"),
        ("REVERSAL WEB PURCHASE BOLT RIDE", "BOLT RIDE"),
        ("Shoprite", "SHOPRITE"),
        ("", None),
        ("123456 ••••", None),
    ],
)
def test_normalise_merchant(raw, expected):
    assert normalise_merchant(raw) == expected


def test_suggest_pattern():
    assert suggest_pattern("SHOPRITE LEKKI") == "SHOPRITE"
    assert suggest_pattern("MR BIGGS IKEJA") == "MR BIGGS"
    assert suggest_pattern("KFC") == "KFC"
    assert suggest_pattern(None) is None


# ---------------- precedence ----------------


def test_user_choice_wins_over_everything():
    rule = Rule(1, BY_SLUG["shopping"], "contains", "SHOPRITE")
    r = categorise(facts("POS PURCHASE SHOPRITE", user_category_id=BY_SLUG["family"]), CATS, [rule])
    assert (r.category_id, r.source, r.confidence) == (BY_SLUG["family"], "user", 100)


def test_fixed_by_type():
    assert categorise(facts("SMS ALERT", kind="fee"), CATS, []).category_id == BY_SLUG["bank_fees"]
    t = categorise(facts("TRF", kind="transfer"), CATS, [])
    assert (t.category_id, t.confidence) == (BY_SLUG["transfers"], 100)
    adj = categorise(facts("x", kind="adjustment", direction="credit"), CATS, [])
    assert adj.category_id is None and not needs_review("adjustment", adj)


def test_linked_refund_and_reversal_copy_original_category():
    r = categorise(
        facts(
            "REFUND JUMIA",
            kind="refund",
            direction="credit",
            linked_category_id=BY_SLUG["shopping"],
        ),
        CATS,
        [],
    )
    assert (r.category_id, r.source) == (BY_SLUG["shopping"], "linked")
    v = categorise(
        facts(
            "REVERSAL NETFLIX",
            kind="reversal",
            direction="credit",
            linked_category_id=BY_SLUG["entertainment"],
        ),
        CATS,
        [],
    )
    assert v.category_id == BY_SLUG["entertainment"]


def test_user_rule_beats_builtin():
    rule = Rule(1, BY_SLUG["family"], "contains", "shoprite")  # lower case is normalised
    r = categorise(facts("POS PURCHASE SHOPRITE LEKKI"), CATS, [rule])
    assert (r.category_id, r.source, r.rule_id) == (BY_SLUG["family"], "rule", 1)
    assert "SHOPRITE" in r.reason.upper()


def test_rule_specificity_and_priority():
    contains = Rule(1, BY_SLUG["groceries"], "contains", "SHOP")
    equals = Rule(2, BY_SLUG["shopping"], "equals", "SHOPRITE LEKKI")
    r = categorise(facts("POS PURCHASE SHOPRITE LEKKI"), CATS, [contains, equals])
    assert r.rule_id == 2  # exact merchant beats "contains"
    urgent = Rule(3, BY_SLUG["family"], "contains", "SHOP", priority=1)
    assert (
        categorise(facts("POS PURCHASE SHOPRITE LEKKI"), CATS, [contains, equals, urgent]).rule_id
        == 3
    )


def test_rule_direction_and_account_filters():
    rule = Rule(1, BY_SLUG["salary"], "contains", "ACME", direction="credit", account_id=5)
    assert (
        categorise(
            facts("ACME LTD", kind="income", direction="credit", account_id=5), CATS, [rule]
        ).source
        == "rule"
    )
    assert (
        categorise(
            facts("ACME LTD", kind="income", direction="credit", account_id=6), CATS, [rule]
        ).source
        != "rule"
    )


def test_rule_to_wrong_kind_category_is_ignored():
    rule = Rule(1, BY_SLUG["salary"], "contains", "SHOPRITE")  # income category
    r = categorise(facts("POS PURCHASE SHOPRITE"), CATS, [rule])
    assert r.source == "system" and r.category_id == BY_SLUG["groceries"]


def test_archived_category_never_assigned():
    cats = dict(CATS)
    gid = BY_SLUG["groceries"]
    cats[gid] = CategoryInfo(gid, "groceries", "expense", "Food", archived=True)
    r = categorise(facts("POS PURCHASE SHOPRITE"), cats, [Rule(1, gid, "contains", "SHOPRITE")])
    assert r.category_id != gid


# ---------------- built-in recognition ----------------


@pytest.mark.parametrize(
    ("narration", "slug", "review"),
    [
        ("POS PURCHASE SHOPRITE LEKKI", "groceries", False),
        ("WEB PURCHASE BOLT RIDE", "transport", False),
        ("BILL PAYMENT IKEJA ELECTRIC", "utilities", False),
        ("AIRTIME MTN 08030000000", "airtime_data", False),
        ("WEB PURCHASE NETFLIX", "entertainment", False),
        ("POS PURCHASE MEDPLUS PHARMACY", "health", False),
        ("PIGGYVEST SAVINGS", "savings_investments", False),
        ("POS SOME SUPERMARKET", "groceries", True),  # generic word → suggestion only
        ("POS PURCHASE GLOVO", "eating_out", False),  # not "GLO" airtime
    ],
)
def test_builtin_recognition(narration, slug, review):
    r = categorise(facts(narration), CATS, [])
    assert r.category_id == BY_SLUG[slug], r
    assert needs_review("expense", r) is review


def test_income_recognition_and_unknown():
    s = categorise(facts("SALARY OCT ACME", kind="income", direction="credit"), CATS, [])
    assert s.category_id == BY_SLUG["salary"]
    u = categorise(facts("FROM ADA", kind="income", direction="credit"), CATS, [])
    assert u.category_id is None and needs_review("income", u)


def test_salary_word_does_not_categorise_spending_as_income():
    r = categorise(facts("SALARY ADVANCE REPAYMENT TO X"), CATS, [])
    assert r.category_id is None or CATS[r.category_id].kind == "expense"


def test_unknown_expense_goes_to_review():
    r = categorise(facts("NIP TRF TO CHIOMA"), CATS, [])
    assert r.category_id is None and needs_review("expense", r)


def test_every_builtin_slug_is_a_default_category():
    assert {slug for slug, _, _ in BUILTIN} <= set(BY_SLUG)
