"""Ledger engine: pure, deterministic money calculations (see RULES.md).

No database access, no floats. Callers load rows, convert them to `Entry`, and call these
functions. Keeping this pure makes every rule unit-testable in isolation.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

INCOME_KINDS = frozenset({"income"})
SPEND_KINDS = frozenset({"expense", "fee"})
REFUND_KINDS = frozenset({"refund"})
NON_PNL_KINDS = frozenset({"transfer", "adjustment"})


@dataclass(frozen=True, slots=True)
class Entry:
    kind: str
    direction: str  # "debit" | "credit"
    amount_minor: int
    currency: str
    status: str  # "pending" | "posted" | "failed" | "reversed"
    transaction_date: date
    account_id: int = 0
    deleted: bool = False
    category_id: int | None = None
    merchant: str | None = None  # normalised merchant label, for R17

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int) or isinstance(self.amount_minor, bool):
            raise TypeError("amount_minor must be an int (minor units)")
        if self.amount_minor <= 0:
            raise ValueError("amount_minor must be positive; direction carries the sign")
        if self.direction not in ("debit", "credit"):
            raise ValueError(f"invalid direction {self.direction!r}")

    @property
    def signed(self) -> int:
        return self.amount_minor if self.direction == "credit" else -self.amount_minor


def is_live(e: Entry) -> bool:
    """R3, R4, R5: failed, deleted, reversed originals and reversal rows count nowhere."""
    return not e.deleted and e.status in ("posted", "pending") and e.kind != "reversal"


def in_period(e: Entry, date_from: date | None, date_to: date | None) -> bool:
    """R12: inclusive on both ends."""
    if date_from is not None and e.transaction_date < date_from:
        return False
    return not (date_to is not None and e.transaction_date > date_to)


@dataclass(slots=True)
class Summary:
    currency: str
    income: int = 0
    gross_spending: int = 0
    fees: int = 0
    refunds: int = 0
    pending_in: int = 0
    pending_out: int = 0
    transaction_count: int = 0

    @property
    def net_spending(self) -> int:
        return self.gross_spending - self.refunds  # R8

    @property
    def net_cash_flow(self) -> int:
        return self.income - self.net_spending  # R11

    def as_dict(self) -> dict[str, int | str]:
        return {
            "currency": self.currency,
            "income": self.income,
            "gross_spending": self.gross_spending,
            "fees": self.fees,
            "refunds": self.refunds,
            "net_spending": self.net_spending,
            "net_cash_flow": self.net_cash_flow,
            "pending_in": self.pending_in,
            "pending_out": self.pending_out,
            "transaction_count": self.transaction_count,
        }


def summarize(
    entries: Iterable[Entry], date_from: date | None = None, date_to: date | None = None
) -> dict[str, Summary]:
    """Income/spending summary per currency for a period (R1-R12)."""
    out: dict[str, Summary] = {}
    for e in entries:
        if not is_live(e) or not in_period(e, date_from, date_to):
            continue
        s = out.setdefault(e.currency, Summary(currency=e.currency))
        if e.kind in NON_PNL_KINDS:  # R9, R10
            continue
        if e.status == "pending":  # R2
            if e.direction == "credit":
                s.pending_in += e.amount_minor
            else:
                s.pending_out += e.amount_minor
            continue
        s.transaction_count += 1
        if e.kind in INCOME_KINDS:  # R6
            s.income += e.amount_minor
        elif e.kind in SPEND_KINDS:  # R7
            s.gross_spending += e.amount_minor
            if e.kind == "fee":
                s.fees += e.amount_minor
        elif e.kind in REFUND_KINDS:  # R8
            s.refunds += e.amount_minor
        else:
            raise ValueError(f"unknown transaction kind {e.kind!r}")
    return out


@dataclass(frozen=True, slots=True)
class Balance:
    currency: str
    opening_minor: int
    posted_minor: int  # B1
    pending_in: int
    pending_out: int

    @property
    def available_incl_pending(self) -> int:  # B3
        return self.posted_minor + self.pending_in - self.pending_out


def account_balance(
    *,
    currency: str,
    opening_minor: int,
    opening_date: date,
    entries: Iterable[Entry],
    as_of: date | None = None,
) -> Balance:
    """Balance of one account (B1-B3). `entries` must all belong to that account."""
    posted = opening_minor
    p_in = p_out = 0
    for e in entries:
        if e.currency != currency:
            raise ValueError("entry currency differs from account currency")
        if not is_live(e) or e.transaction_date < opening_date:
            continue
        if as_of is not None and e.transaction_date > as_of:
            continue
        if e.status == "posted":
            posted += e.signed
        elif e.direction == "credit":
            p_in += e.amount_minor
        else:
            p_out += e.amount_minor
    return Balance(
        currency=currency,
        opening_minor=opening_minor,
        posted_minor=posted,
        pending_in=p_in,
        pending_out=p_out,
    )


def total_balances(balances: Iterable[Balance]) -> dict[str, int]:
    """Sum account balances per currency. Never adds different currencies together."""
    out: dict[str, int] = defaultdict(int)
    for b in balances:
        out[b.currency] += b.posted_minor
    return dict(out)


@dataclass(frozen=True, slots=True)
class Reconciliation:
    as_of: date
    statement_minor: int
    computed_minor: int  # balance computed *now* for that date (B5)

    @property
    def difference_minor(self) -> int:
        return self.statement_minor - self.computed_minor

    @property
    def matches(self) -> bool:
        return self.difference_minor == 0


def reconcile(
    *,
    currency: str,
    opening_minor: int,
    opening_date: date,
    entries: Iterable[Entry],
    as_of: date,
    statement_minor: int,
) -> Reconciliation:
    """B5: compare a statement balance with our balance on the same date. Recomputed every
    time, so editing an old transaction afterwards correctly breaks the match."""
    computed = account_balance(
        currency=currency,
        opening_minor=opening_minor,
        opening_date=opening_date,
        entries=entries,
        as_of=as_of,
    ).posted_minor
    return Reconciliation(as_of=as_of, statement_minor=statement_minor, computed_minor=computed)


@dataclass(slots=True)
class CategoryTotal:
    currency: str
    category_id: int | None  # None = uncategorised
    gross_spending: int = 0
    refunds: int = 0
    income: int = 0
    transaction_count: int = 0

    @property
    def net_spending(self) -> int:
        return self.gross_spending - self.refunds  # R14


def by_category(
    entries: Iterable[Entry], date_from: date | None = None, date_to: date | None = None
) -> dict[tuple[str, int | None], CategoryTotal]:
    """R13-R14: posted income and spending per category for a period. Applies exactly the
    same inclusion rules as summarize(), so the categories always add up to the totals."""
    out: dict[tuple[str, int | None], CategoryTotal] = {}
    for e in entries:
        if not is_live(e) or not in_period(e, date_from, date_to) or e.status != "posted":
            continue
        if e.kind in NON_PNL_KINDS:
            continue
        key = (e.currency, e.category_id)
        t = out.setdefault(key, CategoryTotal(currency=e.currency, category_id=e.category_id))
        t.transaction_count += 1
        if e.kind in INCOME_KINDS:
            t.income += e.amount_minor
        elif e.kind in SPEND_KINDS:
            t.gross_spending += e.amount_minor
        elif e.kind in REFUND_KINDS:
            t.refunds += e.amount_minor
        else:
            raise ValueError(f"unknown transaction kind {e.kind!r}")
    return out


# ---------------- time series & comparisons (R15-R18) ----------------

GRANULARITIES = ("day", "week", "month")


def _add_months(d: date, months: int) -> date:
    """Same day `months` later (negative = earlier), clamped to the last day of the month."""
    idx = d.year * 12 + d.month - 1 + months
    y, m = divmod(idx, 12)
    return date(y, m + 1, min(d.day, _month_len(y, m + 1)))


def _month_len(y: int, m: int) -> int:
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return (nxt - date(y, m, 1)).days


def _is_month_end(d: date) -> bool:
    return d.day == _month_len(d.year, d.month)


def bucket_start(d: date, granularity: str, week_start: int = 1) -> date:
    """R15: the first day of the bucket containing `d`. Weeks start on `week_start`
    (ISO weekday: 1 = Monday ... 7 = Sunday)."""
    if granularity == "day":
        return d
    if granularity == "week":
        if not 1 <= week_start <= 7:
            raise ValueError("week_start must be 1..7")
        return d - timedelta(days=(d.isoweekday() - week_start) % 7)
    if granularity == "month":
        return d.replace(day=1)
    raise ValueError(f"invalid granularity {granularity!r}")


def _bucket_end(start: date, granularity: str) -> date:
    if granularity == "day":
        return start
    if granularity == "week":
        return start + timedelta(days=6)
    return start.replace(day=_month_len(start.year, start.month))


def buckets(
    date_from: date, date_to: date, granularity: str, week_start: int = 1
) -> list[tuple[date, date]]:
    """R15: every bucket covering [date_from, date_to], including empty ones, clipped to the
    period so the first and last buckets may be partial."""
    if date_to < date_from:
        raise ValueError("date_to is before date_from")
    out = []
    start = bucket_start(date_from, granularity, week_start)
    while start <= date_to:
        end = _bucket_end(start, granularity)
        out.append((max(start, date_from), min(end, date_to)))
        start = end + timedelta(days=1)
    return out


@dataclass(slots=True)
class SeriesPoint:
    date_from: date
    date_to: date
    summary: Summary


def time_series(
    entries: Iterable[Entry],
    date_from: date,
    date_to: date,
    granularity: str,
    week_start: int = 1,
    currency: str = "NGN",
) -> list[SeriesPoint]:
    """R15-R16: summarize() per bucket for one currency. Each entry lands in exactly one
    bucket, so the buckets always add up to summarize() for the whole period."""
    spans = buckets(date_from, date_to, granularity, week_start)
    index = {start: i for i, (start, _) in enumerate(spans)}
    grouped: list[list[Entry]] = [[] for _ in spans]
    for e in entries:
        if e.currency != currency or not in_period(e, date_from, date_to):
            continue
        b = max(bucket_start(e.transaction_date, granularity, week_start), date_from)
        grouped[index[b]].append(e)
    out = []
    for (d0, d1), es in zip(spans, grouped, strict=True):
        s = summarize(es, d0, d1).get(currency) or Summary(currency=currency)
        out.append(SeriesPoint(d0, d1, s))
    return out


def previous_period(date_from: date, date_to: date) -> tuple[date, date]:
    """R18: the period a report is compared with.
    - Starts on 1 January and ends in the same year (year to date, full year): the same
      dates one year earlier.
    - Starts on the 1st of a month: shifted back by the number of calendar months the period
      touches (this month so far -> the same days of last month; a whole month -> the whole
      previous month).
    - Anything else: the same number of days immediately before."""
    if date_to < date_from:
        raise ValueError("date_to is before date_from")
    if date_from.day == 1:
        if date_from.month == 1 and date_to.year == date_from.year:
            months = 12
        else:
            months = (date_to.year - date_from.year) * 12 + date_to.month - date_from.month + 1
        p0 = _add_months(date_from, -months)
        p1 = _add_months(date_to, -months)
        if _is_month_end(date_to):
            p1 = p1.replace(day=_month_len(p1.year, p1.month))
        return p0, p1
    length = (date_to - date_from).days + 1
    p1 = date_from - timedelta(days=1)
    return p1 - timedelta(days=length - 1), p1


def percent_change(current: int, previous: int) -> int | None:
    """R18: whole-number % change against |previous|, rounded half away from zero; None when
    there is nothing to compare with (previous is 0)."""
    if previous == 0:
        return None
    num = (current - previous) * 100
    q, r = divmod(abs(num), abs(previous))
    if 2 * r >= abs(previous):
        q += 1
    return q if num >= 0 else -q


@dataclass(slots=True)
class MerchantTotal:
    currency: str
    merchant: str | None  # None = no merchant recognised
    gross_spending: int = 0
    refunds: int = 0
    transaction_count: int = 0

    @property
    def net_spending(self) -> int:
        return self.gross_spending - self.refunds


def by_merchant(
    entries: Iterable[Entry], date_from: date | None = None, date_to: date | None = None
) -> dict[tuple[str, str | None], MerchantTotal]:
    """R17: posted spending (expense + fee) and refunds per merchant, with the same inclusion
    rules as summarize(). Income is not grouped by merchant. Entries without a merchant form
    their own group, so the merchants always add up to net spending."""
    out: dict[tuple[str, str | None], MerchantTotal] = {}
    for e in entries:
        if not is_live(e) or not in_period(e, date_from, date_to) or e.status != "posted":
            continue
        if e.kind in NON_PNL_KINDS or e.kind in INCOME_KINDS:
            continue
        key = (e.currency, e.merchant)
        t = out.setdefault(key, MerchantTotal(currency=e.currency, merchant=e.merchant))
        if e.kind in SPEND_KINDS:
            t.gross_spending += e.amount_minor
        elif e.kind in REFUND_KINDS:
            t.refunds += e.amount_minor
        else:
            raise ValueError(f"unknown transaction kind {e.kind!r}")
        t.transaction_count += 1
    return out
