"""Phase 6: monthly budgets and budget lines.

Hand-reviewed. Figures (spent, carry-over, projections) are never stored: they are computed
live by app.ledger.engine (RULES R19-R24). A line with no category is the overall limit;
NULLS NOT DISTINCT keeps one overall line per budget. Grants the app role access.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28 19:43:13.531837
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import make_url

from app.core.config import get_settings

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="NGN", nullable=False),
        sa.Column("rollover_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("alert_thresholds", sa.ARRAY(sa.Integer()), nullable=True),
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
            "alert_thresholds IS NULL OR (cardinality(alert_thresholds) BETWEEN 1 AND 5 AND 1 <= ALL(alert_thresholds) AND 200 >= ALL(alert_thresholds))",
            name="ck_budget_thresholds",
        ),
        sa.CheckConstraint("extract(day from month) = 1", name="ck_budget_month_first"),
        sa.ForeignKeyConstraint(
            ["currency"],
            ["currencies.code"],
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("user_id", "id", name="uq_budgets_user_id_id"),
        sa.UniqueConstraint("user_id", "month", "currency", name="uq_budgets_user_month"),
    )
    op.create_index(op.f("ix_budgets_user_id"), "budgets", ["user_id"], unique=False)
    op.create_table(
        "budget_lines",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("budget_id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=True),
        sa.Column("planned_minor", sa.BigInteger(), nullable=False),
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
            "planned_minor > 0 AND planned_minor <= 1000000000000000", name="ck_budget_line_amount"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "budget_id"],
            ["budgets.user_id", "budgets.id"],
            name="fk_budget_lines_budget_same_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "category_id"],
            ["categories.user_id", "categories.id"],
            name="fk_budget_lines_category_same_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_budget_lines_budget_id"), "budget_lines", ["budget_id"], unique=False)
    op.create_index(
        op.f("ix_budget_lines_category_id"), "budget_lines", ["category_id"], unique=False
    )
    op.create_index(
        "uq_budget_lines_budget_category",
        "budget_lines",
        ["budget_id", "category_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )

    role = make_url(get_settings().database_url).username
    if not role or not role.replace("_", "").isalnum():
        raise RuntimeError("DATABASE_URL must contain a simple role name")
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON budgets, budget_lines TO "{role}"')
    op.execute(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"')


def downgrade() -> None:
    op.drop_index(
        "uq_budget_lines_budget_category",
        table_name="budget_lines",
        postgresql_nulls_not_distinct=True,
    )
    op.drop_index(op.f("ix_budget_lines_category_id"), table_name="budget_lines")
    op.drop_index(op.f("ix_budget_lines_budget_id"), table_name="budget_lines")
    op.drop_table("budget_lines")
    op.drop_index(op.f("ix_budgets_user_id"), table_name="budgets")
    op.drop_table("budgets")
