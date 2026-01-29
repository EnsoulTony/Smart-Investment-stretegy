"""Additional models separated to avoid circular imports."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Text, Boolean, DateTime, UniqueConstraint, Date, Index

from app.db import Base


class CoreHolding(Base):
    __tablename__ = "core_holdings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    name_zh = Column(Text, nullable=True)
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


class DecisionOutcome(Base):
    __tablename__ = "decision_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Text, nullable=False)
    as_of = Column(Date, nullable=False)
    plugin = Column(Text, nullable=False)
    decision_inputs_hash = Column(Text, nullable=False)
    outcome_label = Column(Text, nullable=False, default="unknown")
    outcome_note = Column(Text, nullable=True)
    labeled_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    horizon = Column(Text, nullable=False, default="D1")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "as_of",
            "plugin",
            "decision_inputs_hash",
            name="uq_decision_outcomes_identity",
        ),
        Index("ix_decision_outcomes_user_plugin_asof", "user_id", "plugin", "as_of"),
    )
