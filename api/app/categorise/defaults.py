"""Default categories every user starts with. Names and colours are editable by the user;
`slug` lets built-in recognition and fixed rules find the right category."""

# (slug, name, kind, colour)
DEFAULT_CATEGORIES: list[tuple[str, str, str, str]] = [
    ("groceries", "Food & groceries", "expense", "#2f8f68"),
    ("eating_out", "Eating out", "expense", "#e07a3f"),
    ("transport", "Transport", "expense", "#3b82c4"),
    ("housing", "Rent & housing", "expense", "#7c5cc4"),
    ("utilities", "Electricity & utilities", "expense", "#c49a1b"),
    ("airtime_data", "Airtime & data", "expense", "#1aa3a3"),
    ("shopping", "Shopping", "expense", "#d0527a"),
    ("entertainment", "Entertainment & subscriptions", "expense", "#9b4dca"),
    ("health", "Health", "expense", "#d94848"),
    ("education", "Education", "expense", "#4a6fd8"),
    ("family", "Family support", "expense", "#b5651d"),
    ("personal_care", "Personal care", "expense", "#c25bb0"),
    ("debt", "Debt repayment", "expense", "#8a5a44"),
    ("giving", "Gifts, tithes & donations", "expense", "#5aa04a"),
    ("savings_investments", "Savings & investments", "expense", "#227a8a"),
    ("bank_fees", "Bank fees", "expense", "#6b7280"),
    ("other_spending", "Other spending", "expense", "#94a3b8"),
    ("salary", "Salary", "income", "#15803d"),
    ("business_income", "Business income", "income", "#0e7490"),
    ("interest", "Interest & dividends", "income", "#65a30d"),
    ("other_income", "Other income", "income", "#4d7c0f"),
    ("transfers", "Transfers between my accounts", "transfer", "#64748b"),
]

# Categories the engine assigns by itself; they can be renamed but not archived or deleted.
LOCKED_SLUGS = frozenset({"bank_fees", "transfers"})
