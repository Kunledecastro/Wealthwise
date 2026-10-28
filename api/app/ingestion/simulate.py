"""Simulated bank events for development and demos (DEMO_MODE only).

Produces a statement-shaped grid that goes through exactly the same import path as a real
file, so it exercises parsing, duplicate detection, matching and reconciliation. Everything
it creates is marked as demo data and the account is labelled "simulated".
"""

import random
from datetime import date, timedelta

HEADER = ["Trans. Date", "Value Date", "Reference", "Narration", "Debit", "Credit", "Balance"]

SPEND = [
    ("POS PURCHASE SHOPRITE LEKKI", 800_000, 4_500_000),
    ("POS PURCHASE CHICKEN REPUBLIC", 250_000, 900_000),
    ("WEB PURCHASE BOLT RIDE", 150_000, 600_000),
    ("AIRTIME MTN 08030000000", 100_000, 500_000),
    ("WEB PURCHASE NETFLIX", 440_000, 440_000),
    ("BILL PAYMENT IKEJA ELECTRIC", 1_000_000, 2_500_000),
    ("POS PURCHASE MEDPLUS PHARMACY", 300_000, 1_500_000),
    ("NIP TRF TO MAMA/FAMILY SUPPORT", 2_000_000, 5_000_000),
]


def _money(minor: int) -> str:
    return f"{minor // 100:,}.{minor % 100:02d}"


def simulate_grid(start: date, end: date, opening_minor: int, seed: int) -> list[list[str]]:
    """Newest-first statement with a consistent running balance from `opening_minor`."""
    rng = random.Random(seed)  # noqa: S311 - demo data, not security
    events: list[tuple[date, str, int, bool]] = []  # (date, narration, amount, is_credit)
    d = start
    while d <= end:
        if d.day == 25:
            events.append((d, "SALARY PAYMENT DEMO EMPLOYER LTD", 45_000_000, True))
        for _ in range(rng.choice([0, 1, 1, 2, 3])):
            narr, lo, hi = rng.choice(SPEND)
            amt = rng.randrange(lo, hi + 1, 50)
            events.append((d, narr, amt, False))
            if narr.startswith("NIP TRF"):
                events.append((d, "NIP TRANSFER CHARGE", 5_375, False))
                events.append((d, "VAT ON NIP CHARGE", 403, False))
        if d.day == 1:
            events.append((d, "SMS ALERT CHARGES", 5_250, False))
        d += timedelta(days=1)
    # One bank reversal of a card purchase, a day later.
    purchases = [e for e in events if not e[3] and "PURCHASE" in e[1]]
    if purchases:
        p = rng.choice(purchases)
        rev_day = min(p[0] + timedelta(days=1), end)
        events.append((rev_day, f"REVERSAL {p[1]}", p[2], True))
    events.sort(key=lambda e: e[0])

    bal = opening_minor
    rows = []
    for i, (day, narr, amt, credit) in enumerate(events):
        bal += amt if credit else -amt
        rows.append(
            [
                day.strftime("%d-%b-%Y"),
                day.strftime("%d-%b-%Y"),
                f"SIM{seed:04d}{i:05d}",
                narr,
                "" if credit else _money(amt),
                _money(amt) if credit else "",
                ("-" if bal < 0 else "") + _money(abs(bal)),
            ]
        )
    return [["DEMO BANK - SIMULATED STATEMENT (NOT REAL DATA)"], [], HEADER, *reversed(rows)]
