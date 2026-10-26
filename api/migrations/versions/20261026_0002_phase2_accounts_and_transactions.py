"""Phase 2: accounts, transactions, transaction revisions.

Hand-reviewed. Adds app-role grants; transaction_revisions is insert-only for the app
(DELETE is kept so that account deletion can cascade).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26 22:22:28.012413
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url

from app.core.config import get_settings

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("institution_name", sa.String(length=80), nullable=True),
        sa.Column("mask", sa.String(length=4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("opening_balance_minor", sa.BigInteger(), nullable=False),
        sa.Column("opening_balance_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=16), server_default="manual", nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("mask IS NULL OR mask ~ '^[0-9]{4}$'", name="ck_accounts_mask"),
        sa.CheckConstraint(
            "source IN ('manual', 'imported', 'simulated', 'connected')", name="ck_accounts_source"
        ),
        sa.CheckConstraint(
            "type IN ('bank', 'wallet', 'cash', 'savings', 'card', 'loan')", name="ck_accounts_type"
        ),
        sa.CheckConstraint(
            "abs(opening_balance_minor) <= 1000000000000000", name="ck_accounts_opening_range"
        ),
        sa.ForeignKeyConstraint(
            ["currency"],
            ["currencies.code"],
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("user_id", "id", name="uq_accounts_user_id_id"),
    )
    op.create_index(op.f("ix_accounts_user_id"), "accounts", ["user_id"], unique=False)
    op.create_table(
        "transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=6), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=True),
        sa.Column("merchant", sa.String(length=120), nullable=True),
        sa.Column("narration", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("source", sa.String(length=16), server_default="manual", nullable=False),
        sa.Column("external_ref", sa.String(length=128), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("transfer_group_id", sa.UUID(), nullable=True),
        sa.Column("reverses_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("refund_of_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            "(kind = 'reversal') = (reverses_transaction_id IS NOT NULL)",
            name="ck_txn_reversal_link",
        ),
        sa.CheckConstraint(
            "(kind = 'transfer') = (transfer_group_id IS NOT NULL)", name="ck_txn_transfer_group"
        ),
        sa.CheckConstraint(
            "(kind IN ('income', 'refund') AND direction = 'credit') OR (kind IN ('expense', 'fee') AND direction = 'debit') OR kind IN ('transfer', 'reversal', 'adjustment')",
            name="ck_txn_kind_direction",
        ),
        sa.CheckConstraint("direction IN ('debit', 'credit')", name="ck_txn_direction"),
        sa.CheckConstraint(
            "kind IN ('income', 'expense', 'fee', 'refund', 'transfer', 'reversal', 'adjustment')",
            name="ck_txn_kind",
        ),
        sa.CheckConstraint(
            "refund_of_transaction_id IS NULL OR kind = 'refund'", name="ck_txn_refund_link"
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'csv', 'xlsx', 'pdf', 'simulated', 'email', 'open_banking')",
            name="ck_txn_source",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'posted', 'failed', 'reversed')", name="ck_txn_status"
        ),
        sa.CheckConstraint(
            "amount_minor > 0 AND amount_minor <= 1000000000000000", name="ck_txn_amount_range"
        ),
        sa.ForeignKeyConstraint(
            ["currency"],
            ["currencies.code"],
        ),
        sa.ForeignKeyConstraint(
            ["refund_of_transaction_id"], ["transactions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reverses_transaction_id"], ["transactions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_transactions_account_same_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_txn_account", "transactions", ["account_id"], unique=False)
    op.create_index("ix_txn_transfer_group", "transactions", ["transfer_group_id"], unique=False)
    op.create_index(
        "ix_txn_user_date", "transactions", ["user_id", "transaction_date", "id"], unique=False
    )
    op.create_index(
        "uq_txn_account_external_ref",
        "transactions",
        ["account_id", "external_ref"],
        unique=True,
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )
    op.create_index(
        "uq_txn_account_fingerprint",
        "transactions",
        ["account_id", "fingerprint"],
        unique=True,
        postgresql_where=sa.text("fingerprint IS NOT NULL"),
    )
    op.create_table(
        "transaction_revisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("transaction_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column(
            "changes", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'delete', 'reverse')", name="ck_rev_action"
        ),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_transaction_revisions_transaction_id"),
        "transaction_revisions",
        ["transaction_id"],
        unique=False,
    )

    role = make_url(get_settings().database_url).username
    if not role or not role.replace("_", "").isalnum():
        raise RuntimeError("DATABASE_URL must contain a simple role name")
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON accounts, transactions TO "{role}"')
    op.execute(f'GRANT SELECT, INSERT, DELETE ON transaction_revisions TO "{role}"')
    op.execute(f'REVOKE UPDATE, TRUNCATE ON transaction_revisions FROM "{role}"')
    op.execute(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"')


def downgrade() -> None:
    op.drop_index(
        op.f("ix_transaction_revisions_transaction_id"), table_name="transaction_revisions"
    )
    op.drop_table("transaction_revisions")
    op.drop_index(
        "uq_txn_account_fingerprint",
        table_name="transactions",
        postgresql_where=sa.text("fingerprint IS NOT NULL"),
    )
    op.drop_index(
        "uq_txn_account_external_ref",
        table_name="transactions",
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )
    op.drop_index("ix_txn_user_date", table_name="transactions")
    op.drop_index("ix_txn_transfer_group", table_name="transactions")
    op.drop_index("ix_txn_account", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index(op.f("ix_accounts_user_id"), table_name="accounts")
    op.drop_table("accounts")
