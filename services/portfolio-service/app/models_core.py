"""Additional models separated to avoid circular imports."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Text, Boolean, DateTime, UniqueConstraint

from app.db import Base


class CoreHolding(Base):
    __tablename__ = "core_holdings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    is_core = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('user_id', 'symbol', name='uq_core_holdings_user_symbol'),
    )


class SymbolNameMapping(Base):
    __tablename__ = "symbol_name_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    market = Column(Text, nullable=False)
    name_zh = Column(Text, nullable=False)
    source = Column(Text, nullable=False, default="manual")
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('symbol', 'market', name='uq_symbol_name_mappings_symbol_market'),
    )
