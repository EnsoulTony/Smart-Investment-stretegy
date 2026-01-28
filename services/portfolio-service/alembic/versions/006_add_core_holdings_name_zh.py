"""Add name_zh to core_holdings.

Revision ID: 006_add_core_holdings_name_zh
Revises: 005_add_symbol_name_mappings
Create Date: 2026-01-28
"""

from alembic import op
import sqlalchemy as sa

revision = "006_add_core_holdings_name_zh"
down_revision = "005_add_symbol_name_mappings"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("core_holdings")}
    if "name_zh" not in columns:
        op.add_column("core_holdings", sa.Column("name_zh", sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("core_holdings")}
    if "name_zh" in columns:
        op.drop_column("core_holdings", "name_zh")
