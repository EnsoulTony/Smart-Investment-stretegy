"""Add is_core flag to trades and core_holdings table.

Revision ID: 003_core_holdings
Revises: 002_add_u_pnl_schema_drift_fix
Create Date: 2026-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_core_holdings'
down_revision = '002_add_u_pnl_schema_drift_fix'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('trades', sa.Column('is_core', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    op.create_table(
        'core_holdings',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('symbol', sa.Text(), nullable=False),
        sa.Column('is_core', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('user_id', 'symbol', name='uq_core_holdings_user_symbol'),
    )


def downgrade() -> None:
    op.drop_table('core_holdings')
    op.drop_column('trades', 'is_core')
