"""Add u_pnl column to positions (schema drift fix)

Revision ID: 002_add_u_pnl_schema_drift_fix
Revises: 001_initial_schema
Create Date: 2026-01-25 00:00:00.000000

This migration fixes schema drift where ORM expects positions.u_pnl but DB schema is missing it,
which can cause production 500s on /portfolio/positions.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_add_u_pnl_schema_drift_fix'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 修正 schema drift：補上 positions.u_pnl（避免 production 500）
    # 使用 batch_alter_table 檢查欄位是否已存在
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('positions')]
    
    if 'u_pnl' not in columns:
        op.add_column(
            'positions',
            sa.Column('u_pnl', sa.Numeric(18, 6), nullable=True)
        )
    else:
        # 欄位已存在，跳過（冪等性）
        pass


def downgrade() -> None:
    op.drop_column('positions', 'u_pnl')
