"""Categorisation engine (pure, deterministic; no database, no AI).

Order of precedence for one transaction:
  1. The user's own choice (never overwritten by anything automatic).
  2. Fixed by type: transfers → Transfers; bank fees → Bank fees; a linked refund or a
     reversal takes the category of the transaction it cancels; adjustments stay
     uncategorised (they are not income or spending).
  3. The user's rules (exact merchant > merchant starts with > text contains; then priority).
  4. Built-in recognition of common Nigerian merchants and words.
  5. Nothing → uncategorised and flagged for review.

Every result carries a confidence (0-100) and a plain-English reason. Confidence is a hint
for ordering the review queue, never proof of correctness.
"""

import re
from dataclasses import dataclass

REVIEW_THRESHOLD = 70
PNL_KINDS = frozenset({"income", "expense", "fee", "refund"})

# ---------------------------------------------------------------- merchant normalisation

_PREFIXES = [
    "POS/WEB PURCHASE",
    "POS PURCHASE",
    "POS PUR",
    "POS TRAN",
    "POS",
    "WEB PURCHASE",
    "WEB PUR",
    "WEB",
    "CARD PURCHASE",
    "PURCHASE",
    "PAYMENT TO",
    "PAYMENT FOR",
    "BILL PAYMENT",
    "BILLS PAYMENT",
    "BILLPAY",
    "NIP TRANSFER TO",
    "NIP TRANSFER FROM",
    "NIP TRF TO",
    "NIP TRF FROM",
    "NIP TRF",
    "NIP",
    "MOB TRF TO",
    "MOB TRF",
    "TRF TO",
    "TRF FROM",
    "TRF",
    "TRANSFER TO",
    "TRANSFER FROM",
    "TRANSFER",
    "FIP",
    "USSD",
    "REVERSAL OF",
    "REVERSAL",
    "RVSL",
    "REFUND FROM",
    "REFUND",
    "ONLINE",
    "DEBIT",
    "CREDIT",
    "VIA",
    "AT",
]
_PREFIX_RE = re.compile(
    r"^(?:(?:"
    + "|".join(re.escape(p) for p in sorted(_PREFIXES, key=len, reverse=True))
    + r")\b[\s:/\-*]*)+"
)
_NOISE_TOKEN = re.compile(
    r"^(?:•+\d*|\d[\d\-/.:]*|[A-Z]*\d{4,}[A-Z\d]*|NG|NGA|LA|LAG|LAGOS|ABUJA|ABJ)$"
)


def normalise_merchant(text: str | None) -> str | None:
    """'POS PURCHASE SHOPRITE LEKKI 5399…' → 'SHOPRITE LEKKI'. Best effort, for matching."""
    if not text:
        return None
    s = text.upper().replace("•", " •")
    s = re.sub(r"[^\w\s•&'.\-/*]", " ", s)  # also drops "@"
    s = re.sub(r"\s+", " ", s).strip()
    s = _PREFIX_RE.sub("", s)
    s = re.split(r"\s*[/|*]\s*", s, maxsplit=1)[0]  # 'KUDA/JOHN DOE/…' → 'KUDA'
    tokens = [t.strip(".-'") for t in s.split(" ")]
    tokens = [t for t in tokens if t and not _NOISE_TOKEN.match(t)]
    out = " ".join(tokens[:3]).strip()
    return out[:120] or None


def suggest_pattern(merchant_normalised: str | None) -> str | None:
    """The part of a merchant worth remembering in a rule: 'SHOPRITE LEKKI' → 'SHOPRITE'."""
    if not merchant_normalised:
        return None
    words = merchant_normalised.split()
    if len(words[0]) >= 4 or len(words) == 1:
        return words[0][:100]
    return " ".join(words[:2])[:100]


# ---------------------------------------------------------------- built-in recognition

# (slug, confidence, words). Brand names are fairly certain (80); generic words are only a
# suggestion (60) and still go to review.
BUILTIN: list[tuple[str, int, tuple[str, ...]]] = [
    (
        "groceries",
        80,
        (
            "SHOPRITE",
            "SPAR",
            "JUSTRITE",
            "EBEANO",
            "PRINCE EBEANO",
            "HUBMART",
            "ADDIDE",
            "FOODCO",
            "MARKET SQUARE",
            "BLENCO",
            "GRAND SQUARE",
        ),
    ),
    ("groceries", 60, ("SUPERMARKET", "GROCERY", "GROCERIES", "MINIMART", "PROVISIONS")),
    (
        "eating_out",
        80,
        (
            "CHICKEN REPUBLIC",
            "KFC",
            "DOMINOS",
            "DOMINO S",
            "MR BIGGS",
            "TANTALIZERS",
            "SWEET SENSATION",
            "COLD STONE",
            "COLDSTONE",
            "CAFE NEO",
            "KILIMANJARO",
            "CHOWDECK",
            "GLOVO",
            "HEYFOOD",
            "FOODCOURT",
            "BUKKA HUT",
            "BURGER KING",
            "PIZZA HUT",
            "THE PLACE",
        ),
    ),
    ("eating_out", 60, ("RESTAURANT", "EATERY", "CAFE", "LOUNGE", "SUYA", "BUKKA")),
    (
        "transport",
        80,
        (
            "BOLT",
            "UBER",
            "INDRIVE",
            "RIDA",
            "LAGRIDE",
            "TOTALENERGIES",
            "TOTAL ENERGIES",
            "MOBIL",
            "CONOIL",
            "OANDO",
            "ARDOVA",
            "NNPC",
            "MRS OIL",
            "AIR PEACE",
            "ARIK",
            "IBOM AIR",
            "UNITED NIGERIA",
            "LCC",
            "COWRY CARD",
            "GIG MOBILITY",
            "GUO",
        ),
    ),
    ("transport", 60, ("FUEL", "FILLING STATION", "PETROL", "PARKING", "TOLL", "BRT", "TAXI")),
    (
        "utilities",
        80,
        (
            "IKEJA ELECTRIC",
            "IKEDC",
            "EKEDC",
            "EKO ELECTRIC",
            "AEDC",
            "PHED",
            "IBEDC",
            "KEDCO",
            "EEDC",
            "JED",
            "BEDC",
            "LAWMA",
        ),
    ),
    ("utilities", 60, ("ELECTRICITY", "PREPAID METER", "POWER", "WATER", "WASTE")),
    (
        "airtime_data",
        80,
        (
            "MTN",
            "AIRTEL",
            "GLO",
            "9MOBILE",
            "SPECTRANET",
            "SMILE",
            "STARLINK",
            "IPNX",
            "TIZETI",
            "FIBERONE",
        ),
    ),
    ("airtime_data", 70, ("AIRTIME", "DATA BUNDLE", "DATA SUB", "RECHARGE")),
    (
        "entertainment",
        80,
        (
            "NETFLIX",
            "DSTV",
            "GOTV",
            "MULTICHOICE",
            "SHOWMAX",
            "SPOTIFY",
            "APPLE COM",
            "APPLE.COM",
            "YOUTUBE",
            "BOOMPLAY",
            "PRIME VIDEO",
            "FILMHOUSE",
            "GENESIS CINEMA",
            "SILVERBIRD",
            "AUDIOMACK",
            "STARTIMES",
        ),
    ),
    ("entertainment", 60, ("CINEMA", "SUBSCRIPTION", "BETTING", "BET9JA", "SPORTYBET")),
    (
        "shopping",
        80,
        (
            "JUMIA",
            "KONGA",
            "AMAZON",
            "ALIEXPRESS",
            "TEMU",
            "SLOT",
            "PAYPORTE",
            "POINTEK",
            "ZARA",
            "H&M",
            "WOODIN",
            "MR PRICE",
        ),
    ),
    (
        "health",
        80,
        (
            "MEDPLUS",
            "HEALTHPLUS",
            "HEALTH PLUS",
            "RELIANCE HMO",
            "AXA MANSARD",
            "HYGEIA",
            "LEADWAY HEALTH",
            "AVON HMO",
            "ALPHA PHARMACY",
        ),
    ),
    ("health", 60, ("PHARMACY", "HOSPITAL", "CLINIC", "HMO", "LABORATORY", "DIAGNOSTIC")),
    ("education", 80, ("WAEC", "JAMB", "NECO", "COURSERA", "UDEMY", "ULESSON")),
    ("education", 60, ("SCHOOL FEES", "SCHOOL FEE", "TUITION", "UNIVERSITY", "COLLEGE", "ACADEMY")),
    ("housing", 60, ("RENT", "HOUSE RENT", "ESTATE DUES", "AGENCY FEE")),
    ("giving", 70, ("TITHE", "OFFERING", "ZAKAT", "SADAQAH", "DONATION")),
    ("giving", 60, ("CHURCH", "MOSQUE", "PARISH", "MINISTRY")),
    (
        "debt",
        80,
        ("CARBON", "FAIRMONEY", "PALMCREDIT", "RENMONEY", "AELLA", "QUICKCHECK", "LOAN REPAYMENT"),
    ),
    (
        "savings_investments",
        80,
        (
            "PIGGYVEST",
            "COWRYWISE",
            "RISEVEST",
            "BAMBOO",
            "TROVE",
            "CHAKA",
            "GETEQUITY",
            "KUDA SAVE",
        ),
    ),
    ("personal_care", 60, ("SALON", "BARBER", "SPA", "COSMETICS")),
    ("salary", 80, ("SALARY", "PAYROLL", "WAGES")),
    ("interest", 80, ("INTEREST", "INT PAID", "DIVIDEND")),
]


@dataclass(frozen=True, slots=True)
class CategoryInfo:
    id: int
    slug: str | None
    kind: str  # expense | income | transfer
    name: str
    archived: bool = False


@dataclass(frozen=True, slots=True)
class Rule:
    id: int
    category_id: int
    match_type: str  # contains | starts_with | equals
    pattern: str
    direction: str | None = None
    account_id: int | None = None
    priority: int = 100


@dataclass(frozen=True, slots=True)
class Facts:
    kind: str
    direction: str
    narration: str | None
    merchant: str | None
    merchant_normalised: str | None
    account_id: int = 0
    linked_category_id: int | None = None  # category of the original, for refunds/reversals
    user_category_id: int | None = None  # set only when the user chose explicitly


@dataclass(frozen=True, slots=True)
class Result:
    category_id: int | None
    source: str  # none | user | rule | system | linked
    confidence: int
    reason: str | None
    rule_id: int | None = None


def needs_review(kind: str, r: Result) -> bool:
    if kind not in PNL_KINDS or r.source == "user":
        return False
    return r.category_id is None or r.confidence < REVIEW_THRESHOLD


def norm_pattern(p: str) -> str:
    return re.sub(r"\s+", " ", p.strip().upper())


def _text(f: Facts) -> str:
    return norm_pattern(" ".join(x for x in (f.merchant, f.narration) if x))


def _word_in(word: str, text: str) -> bool:
    return re.search(rf"(?<![A-Z0-9]){re.escape(word)}(?![A-Z0-9])", text) is not None


def rule_matches(rule: Rule, f: Facts) -> bool:
    if rule.direction and rule.direction != f.direction:
        return False
    if rule.account_id and rule.account_id != f.account_id:
        return False
    pat = norm_pattern(rule.pattern)
    merchant = norm_pattern(f.merchant_normalised or "")
    if rule.match_type == "equals":
        return merchant == pat
    if rule.match_type == "starts_with":
        return merchant.startswith(pat)
    return pat in _text(f)


_SPECIFICITY = {"equals": 0, "starts_with": 1, "contains": 2}


def order_rules(rules: list[Rule]) -> list[Rule]:
    return sorted(
        rules, key=lambda r: (r.priority, _SPECIFICITY[r.match_type], -len(r.pattern), r.id)
    )


def _fits(cat: CategoryInfo, f: Facts) -> bool:
    """Spending categories for money out (and refunds of it), income categories for money in."""
    if cat.archived:
        return False
    if f.kind in ("expense", "fee", "refund"):
        return cat.kind == "expense"
    if f.kind == "income":
        return cat.kind == "income"
    return False


_DESCRIBE = {"equals": "merchant is", "starts_with": "merchant starts with", "contains": "contains"}


def categorise(
    f: Facts,
    categories: dict[int, CategoryInfo],
    rules: list[Rule],
) -> Result:
    by_slug = {c.slug: c for c in categories.values() if c.slug and not c.archived}
    # 1. explicit user choice
    if f.user_category_id is not None:
        return Result(f.user_category_id, "user", 100, "You chose this category")
    # 2. fixed by type
    if f.kind == "transfer":
        c = by_slug.get("transfers")
        return Result(c.id if c else None, "system", 100, "Transfer between your own accounts")
    if f.kind == "fee":
        c = by_slug.get("bank_fees")
        return Result(c.id if c else None, "system", 100, "Bank fee")
    if f.kind == "adjustment":
        return Result(None, "none", 0, "Balance adjustments aren't income or spending")
    if f.kind in ("refund", "reversal") and f.linked_category_id is not None:
        what = "purchase it refunds" if f.kind == "refund" else "transaction it reverses"
        return Result(f.linked_category_id, "linked", 100, f"Same as the {what}")
    if f.kind == "reversal":
        return Result(None, "none", 0, None)
    # 3. user rules
    for rule in order_rules(rules):
        cat = categories.get(rule.category_id)
        if cat and _fits(cat, f) and rule_matches(rule, f):
            return Result(
                cat.id,
                "rule",
                95,
                f"Your rule: {_DESCRIBE[rule.match_type]} '{rule.pattern}'",
                rule.id,
            )
    # 4. built-in recognition (most confident match wins; earlier list entries break ties)
    text = _text(f)
    best: tuple[int, CategoryInfo, str] | None = None
    for slug, conf, words in BUILTIN:
        cat = by_slug.get(slug)
        if not cat or not _fits(cat, f) or (best and conf <= best[0]):
            continue
        for w in words:
            if _word_in(w, text):
                best = (conf, cat, w)
                break
    if best:
        conf, cat, w = best
        reason = (
            f"Recognised '{w}'"
            if conf >= REVIEW_THRESHOLD
            else f"Suggested from the word '{w}', please confirm"
        )
        return Result(cat.id, "system", conf, reason)
    return Result(None, "none", 0, None)
