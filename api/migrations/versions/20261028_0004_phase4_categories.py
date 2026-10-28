"""Phase 4: categories, category rules, categorisation fields on transactions and import rows.

Hand-reviewed. Seeds the default categories for every existing user (a frozen copy of
app/categorise/defaults.py so this migration never changes), files existing transfers and
bank fees, and grants the app role access. Remaining categorisation of existing
transactions is done by `python -m app.cli categorise-pending` (run by the migrate service).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28 18:06:10.500551
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url

from app.core.config import get_settings

DEFAULTS = [
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

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.String(length=40), nullable=True),
        sa.Column("name", postgresql.CITEXT(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("color", sa.String(length=7), server_default="#94a3b8", nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="100", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name="ck_category_color"),
        sa.CheckConstraint("kind IN ('expense', 'income', 'transfer')", name="ck_category_kind"),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 60", name="ck_category_name_len"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("user_id", "id", name="uq_categories_user_id_id"),
        sa.UniqueConstraint("user_id", "name", name="uq_categories_user_name"),
    )
    op.create_index(op.f("ix_categories_user_id"), "categories", ["user_id"], unique=False)
    op.create_index(
        "uq_categories_user_slug",
        "categories",
        ["user_id", "slug"],
        unique=True,
        postgresql_where=sa.text("slug IS NOT NULL"),
    )
    op.create_table(
        "category_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("match_type", sa.String(length=12), nullable=False),
        sa.Column("pattern", sa.String(length=100), nullable=False),
        sa.Column("direction", sa.String(length=6), nullable=True),
        sa.Column("account_id", sa.BigInteger(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("created_from", sa.String(length=16), server_default="manual", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("hit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "created_from IN ('manual', 'user_correction')", name="ck_rule_created_from"
        ),
        sa.CheckConstraint(
            "direction IS NULL OR direction IN ('debit', 'credit')", name="ck_rule_dir"
        ),
        sa.CheckConstraint(
            "match_type IN ('contains', 'starts_with', 'equals')", name="ck_rule_match_type"
        ),
        sa.CheckConstraint("length(pattern) BETWEEN 2 AND 100", name="ck_rule_pattern_len"),
        sa.ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_rules_account_same_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "category_id"],
            ["categories.user_id", "categories.id"],
            name="fk_rules_category_same_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_category_rules_user_id"), "category_rules", ["user_id"], unique=False)
    op.add_column(
        "import_rows", sa.Column("merchant_normalised", sa.String(length=120), nullable=True)
    )
    op.add_column("import_rows", sa.Column("category_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "import_rows",
        sa.Column("category_source", sa.String(length=8), server_default="none", nullable=False),
    )
    op.add_column(
        "import_rows",
        sa.Column("category_confidence", sa.SmallInteger(), server_default="0", nullable=False),
    )
    op.add_column("import_rows", sa.Column("category_reason", sa.String(length=200), nullable=True))
    op.add_column("import_rows", sa.Column("category_rule_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_import_rows_category",
        "import_rows",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_import_rows_rule",
        "import_rows",
        "category_rules",
        ["category_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "transactions", sa.Column("merchant_normalised", sa.String(length=120), nullable=True)
    )
    op.add_column("transactions", sa.Column("category_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "transactions",
        sa.Column("category_source", sa.String(length=8), server_default="none", nullable=False),
    )
    op.add_column(
        "transactions",
        sa.Column("category_confidence", sa.SmallInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "transactions", sa.Column("category_reason", sa.String(length=200), nullable=True)
    )
    op.add_column("transactions", sa.Column("category_rule_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "transactions",
        sa.Column("needs_review", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index("ix_txn_category", "transactions", ["category_id"], unique=False)
    op.create_index("ix_txn_user_review", "transactions", ["user_id", "needs_review"], unique=False)
    op.create_foreign_key(
        "fk_transactions_category_same_user",
        "transactions",
        "categories",
        ["user_id", "category_id"],
        ["user_id", "id"],
    )
    op.create_foreign_key(
        "fk_txn_category_rule",
        "transactions",
        "category_rules",
        ["category_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_txn_category_source",
        "transactions",
        "category_source IN ('none', 'user', 'rule', 'system', 'linked', 'ai')",
    )
    op.create_check_constraint(
        "ck_txn_category_confidence", "transactions", "category_confidence BETWEEN 0 AND 100"
    )

    # Default categories for every existing user.
    for i, (slug, name, kind, color) in enumerate(DEFAULTS):
        op.execute(
            sa.text(
                "INSERT INTO categories (public_id, user_id, slug, name, kind, color, sort_order) "
                "SELECT gen_random_uuid(), id, :slug, :name, :kind, :color, :sort FROM users"
            ).bindparams(slug=slug, name=name, kind=kind, color=color, sort=i * 10)
        )
    # Transfers and bank fees can be filed straight away; the rest is done by the CLI.
    for kind, slug, reason in (
        ("transfer", "transfers", "Transfer between your own accounts"),
        ("fee", "bank_fees", "Bank fee"),
    ):
        op.execute(
            sa.text(
                "UPDATE transactions t SET category_id = c.id, category_source = 'system', "
                "category_confidence = 100, category_reason = :reason "
                "FROM categories c WHERE c.user_id = t.user_id AND c.slug = :slug "
                "AND t.kind = :kind"
            ).bindparams(kind=kind, slug=slug, reason=reason)
        )

    role = make_url(get_settings().database_url).username
    if not role or not role.replace("_", "").isalnum():
        raise RuntimeError("DATABASE_URL must contain a simple role name")
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON categories, category_rules TO "{role}"')
    op.execute(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"')


def downgrade() -> None:
    op.drop_constraint("ck_txn_category_confidence", "transactions", type_="check")
    op.drop_constraint("ck_txn_category_source", "transactions", type_="check")
    op.drop_constraint("fk_txn_category_rule", "transactions", type_="foreignkey")
    op.drop_constraint("fk_transactions_category_same_user", "transactions", type_="foreignkey")
    op.drop_index("ix_txn_user_review", table_name="transactions")
    op.drop_index("ix_txn_category", table_name="transactions")
    op.drop_column("transactions", "needs_review")
    op.drop_column("transactions", "category_rule_id")
    op.drop_column("transactions", "category_reason")
    op.drop_column("transactions", "category_confidence")
    op.drop_column("transactions", "category_source")
    op.drop_column("transactions", "category_id")
    op.drop_column("transactions", "merchant_normalised")
    # WARNING: constraint name is None; this directive will fail as
    # rendered.  Add a name, or use a naming convention; see
    # https://alembic.sqlalchemy.org/en/latest/naming.html
    op.drop_constraint("fk_import_rows_rule", "import_rows", type_="foreignkey")
    # WARNING: constraint name is None; this directive will fail as
    # rendered.  Add a name, or use a naming convention; see
    # https://alembic.sqlalchemy.org/en/latest/naming.html
    op.drop_constraint("fk_import_rows_category", "import_rows", type_="foreignkey")
    op.drop_column("import_rows", "category_rule_id")
    op.drop_column("import_rows", "category_reason")
    op.drop_column("import_rows", "category_confidence")
    op.drop_column("import_rows", "category_source")
    op.drop_column("import_rows", "category_id")
    op.drop_column("import_rows", "merchant_normalised")
    op.drop_index(op.f("ix_category_rules_user_id"), table_name="category_rules")
    op.drop_table("category_rules")
    op.drop_index(
        "uq_categories_user_slug",
        table_name="categories",
        postgresql_where=sa.text("slug IS NOT NULL"),
    )
    op.drop_index(op.f("ix_categories_user_id"), table_name="categories")
    op.drop_table("categories")
