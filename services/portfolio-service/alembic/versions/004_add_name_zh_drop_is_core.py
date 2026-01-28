"""Add name_zh to trades/positions and drop trades.is_core.

Revision ID: 004_add_name_zh_drop_is_core
Revises: 003_core_holdings
Create Date: 2026-01-28 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "004_add_name_zh_drop_is_core"
down_revision = "003_core_holdings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("name_zh", sa.Text(), nullable=True))
    op.add_column("positions", sa.Column("name_zh", sa.Text(), nullable=True))
    op.drop_column("trades", "is_core")


def downgrade() -> None:
    op.add_column("trades", sa.Column("is_core", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.drop_column("positions", "name_zh")
    op.drop_column("trades", "name_zh")
