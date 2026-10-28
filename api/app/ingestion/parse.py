"""Exact parsing of statement dates and amounts (no floating point anywhere)."""

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}
MONTHS["sept"] = 9

_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$")
_NUMERIC = re.compile(r"^(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{2,4})(?:[ T].*)?$")
_TEXT_MONTH = re.compile(r"^(\d{1,2})[\s\-/.]*([A-Za-z]{3,9})[\s\-/.,]*(\d{2,4})(?:[ T].*)?$")
_TEXT_MONTH_FIRST = re.compile(r"^([A-Za-z]{3,9})[\s\-/.]*(\d{1,2})[\s,]*(\d{4})(?:[ T].*)?$")


def _year(y: str) -> int:
    n = int(y)
    return 2000 + n if len(y) == 2 else n


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        out = date(y, m, d)
    except ValueError:
        return None
    return out if 1970 <= out.year <= 2100 else None


def parse_date(raw: str, order: str = "DMY") -> date | None:
    """Parse a statement date. `order` resolves numeric dates: DMY (Nigerian default),
    MDY or YMD. Text months ("24-Oct-2026") and ISO dates work regardless of order."""
    s = raw.strip()
    if not s:
        return None
    if m := _ISO.match(s):
        return _mk(int(m[1]), int(m[2]), int(m[3]))
    if m := _TEXT_MONTH.match(s):
        mon = MONTHS.get(m[2].lower()[:4]) or MONTHS.get(m[2].lower()[:3])
        return _mk(_year(m[3]), mon, int(m[1])) if mon else None
    if m := _TEXT_MONTH_FIRST.match(s):
        mon = MONTHS.get(m[1].lower()[:4]) or MONTHS.get(m[1].lower()[:3])
        return _mk(int(m[3]), mon, int(m[2])) if mon else None
    if m := _NUMERIC.match(s):
        a, b, c = m[1], m[2], m[3]
        if len(a) == 4:  # 2026/10/24
            return _mk(int(a), int(b), int(c))
        if order == "MDY":
            return _mk(_year(c), int(a), int(b))
        return _mk(_year(c), int(b), int(a))
    # Excel serial number that arrived as text (e.g. "46319")
    if re.fullmatch(r"\d{5}(\.0+)?", s):
        n = int(float(s))
        if 25569 <= n <= 73050:  # 1970..2100
            return date.fromordinal(datetime(1899, 12, 30).toordinal() + n)
    return None


def guess_date_order(samples: list[str]) -> str:
    """DMY unless the data proves otherwise (a first part > 12 confirms DMY, a second
    part > 12 indicates MDY)."""
    first_big = second_big = False
    for s in samples:
        m = _NUMERIC.match(s.strip())
        if not m or len(m[1]) == 4:
            continue
        a, b = int(m[1]), int(m[2])
        first_big |= a > 12
        second_big |= b > 12
    if second_big and not first_big:
        return "MDY"
    return "DMY"


_AMOUNT_CLEAN = re.compile(r"[₦,\s]|NGN|N(?=\d)", re.IGNORECASE)


def parse_amount(raw: str, exponent: int = 2) -> tuple[int, bool] | None:
    """Parse "25,000.50", "₦25,000.50", "(1,200.00)", "-500", "1,000.00 DR", "750 CR".

    Returns (minor_units >= 0, is_negative_or_debit_marked) or None for blank/zero-like
    cells. Raises ValueError for text that is clearly not an amount, or for more decimal
    places than the currency allows.
    """
    s = raw.strip()
    if s in ("", "-", "--", "—", "0", "0.0", "0.00", ".00", "nil", "NIL", "N/A", "n/a"):
        return None
    negative = False
    upper = s.upper()
    for suffix, neg in ((" DR", True), ("DR", True), (" CR", False), ("CR", False)):
        if upper.endswith(suffix):
            s = s[: -len(suffix)].strip()
            negative = neg
            break
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    s = _AMOUNT_CLEAN.sub("", s)
    if s.startswith("-"):
        negative, s = True, s[1:]
    elif s.startswith("+"):
        s = s[1:]
    if not re.fullmatch(r"\d+(\.\d+)?|\.\d+", s):
        raise ValueError(f"'{raw.strip()[:30]}' is not an amount")
    try:
        d = Decimal(s)
    except InvalidOperation as exc:  # pragma: no cover - regex already guards
        raise ValueError(f"'{raw[:30]}' is not an amount") from exc
    q = d.quantize(Decimal(1).scaleb(-exponent), rounding=ROUND_HALF_UP)
    if abs(q - d) > Decimal("0.000001"):
        raise ValueError(f"'{raw.strip()[:30]}' has more than {exponent} decimal places")
    minor = int(q.scaleb(exponent))
    if minor == 0:
        return None
    return minor, negative


def parse_signed(raw: str) -> int | None:
    """Signed minor units (for balance columns, where negative means overdrawn)."""
    r = parse_amount(raw)
    if r is None:
        return 0 if raw.strip() in ("0", "0.0", "0.00", ".00") else None
    minor, neg = r
    return -minor if neg else minor
