"""Portfolio Service 資料模型定義。

定義三張表：
1. trades - 交易流水帳
2. positions - 最新持倉快照
3. sync_runs - 同步紀錄
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, UniqueConstraint, Index, Boolean
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import synonym
import uuid

from app.db import Base
from app.models_core import CoreHolding  # noqa: F401 - exported for Alembic autoload


class Trade(Base):
    """交易流水帳表。
    
    記錄每一筆買賣交易，透過 source_hash 避免重複匯入。
    """
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    asset_ccy = Column(Text, nullable=False)
    side = Column(Text, nullable=False)  # BUY/SELL
    quantity = Column(Numeric, nullable=False)
    price = Column(Numeric, nullable=False)
    fee = Column(Numeric, nullable=False, default=0)
    trade_date = Column(DateTime(timezone=True), nullable=False)
    broker = Column(Text, nullable=False)
    is_core = Column(Boolean, nullable=False, server_default=sa.text('false'))
    source_row_id = Column(Text, nullable=True)
    source_hash = Column(Text, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index('ix_trades_user_symbol_date', 'user_id', 'symbol', 'trade_date'),
        UniqueConstraint('source_hash', name='uq_trades_source_hash'),
    )


class Position(Base):
    """最新持倉快照表。
    
    每個 user_id + symbol 只保留一筆最新狀態。
    """
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    asset_ccy = Column(Text, nullable=False)
    quantity = Column(Numeric, nullable=False)
    avg_cost = Column(Numeric, nullable=False)
    realized_pnl = Column(Numeric, nullable=False, default=0)
    u_pnl = Column(Numeric, nullable=False, default=0)
    last_updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        UniqueConstraint('user_id', 'symbol', name='uq_positions_user_symbol'),
    )


class SyncRun(Base):
    """同步紀錄表。
    
    記錄每次從 Google Sheets 同步的執行結果。
    """
    __tablename__ = "sync_runs"
    
    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Text, nullable=False)  # started/succeeded/failed
    inserted_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    
    # Synonym: 讓 created_at 指向 started_at（相容性，測試中使用）
    created_at = synonym("started_at")
