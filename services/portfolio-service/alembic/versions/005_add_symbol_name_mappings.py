"""Add symbol_name_mappings table for symbol/name_zh cache.

Revision ID: 005_add_symbol_name_mappings
Revises: 004_add_name_zh_drop_is_core
Create Date: 2026-01-28
"""

from alembic import op
import sqlalchemy as sa


revision = "005_add_symbol_name_mappings"
down_revision = "004_add_name_zh_drop_is_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "symbol_name_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("market", sa.Text(), nullable=False),
        sa.Column("name_zh", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("symbol", "market", name="uq_symbol_name_mappings_symbol_market"),
    )
    op.create_index("ix_symbol_name_mappings_symbol", "symbol_name_mappings", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_symbol_name_mappings_symbol", table_name="symbol_name_mappings")
    op.drop_table("symbol_name_mappings")
