"""Initial schema: trades, positions, sync_runs

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-01-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 建立 trades 表
    op.create_table(
        'trades',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('symbol', sa.Text(), nullable=False),
        sa.Column('asset_ccy', sa.Text(), nullable=False),
        sa.Column('side', sa.Text(), nullable=False),
        sa.Column('quantity', sa.Numeric(), nullable=False),
        sa.Column('price', sa.Numeric(), nullable=False),
        sa.Column('fee', sa.Numeric(), nullable=False, server_default='0'),
        sa.Column('trade_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('broker', sa.Text(), nullable=False),
        sa.Column('source_row_id', sa.Text(), nullable=True),
        sa.Column('source_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_hash', name='uq_trades_source_hash')
    )
    op.create_index('ix_trades_user_symbol_date', 'trades', ['user_id', 'symbol', 'trade_date'])
    
    # 建立 positions 表
    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('symbol', sa.Text(), nullable=False),
        sa.Column('asset_ccy', sa.Text(), nullable=False),
        sa.Column('quantity', sa.Numeric(), nullable=False),
        sa.Column('avg_cost', sa.Numeric(), nullable=False),
        sa.Column('realized_pnl', sa.Numeric(), nullable=False, server_default='0'),
        sa.Column('unrealized_pnl', sa.Numeric(), nullable=False, server_default='0'),
        sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'symbol', name='uq_positions_user_symbol')
    )
    
    # 建立 sync_runs 表
    op.create_table(
        'sync_runs',
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('inserted_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skipped_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('run_id')
    )


def downgrade() -> None:
    op.drop_table('sync_runs')
    op.drop_table('positions')
    op.drop_index('ix_trades_user_symbol_date', table_name='trades')
    op.drop_table('trades')
