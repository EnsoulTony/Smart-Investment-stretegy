"""Strategy Engine Schemas: Fixed Input/Output contract.

These schemas are the FIXED contract for all strategy plugins.
Fields can be ADDED but never REMOVED (backward compatibility).
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from decimal import Decimal
from enum import Enum


# =============================================================================
# Enums for type safety
# =============================================================================

class Mode(str, Enum):
    """Market regime mode."""
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    TRANSITION = "TRANSITION"


class Decision(str, Enum):
    """Portfolio decision."""
    NO_ACTION = "NO_ACTION"
    REDUCE_RISK = "REDUCE_RISK"
    REBALANCE = "REBALANCE"
    WATCHLIST = "WATCHLIST"


class Action(str, Enum):
    """Per-position action."""
    HOLD = "HOLD"
    TRIM = "TRIM"
    ADD = "ADD"
    AVOID = "AVOID"


# =============================================================================
# Input Schema Components
# =============================================================================

class PositionInput(BaseModel):
    """Position data from portfolio-service (accounting layer)."""
    symbol: str = Field(..., description="Stock symbol")
    asset_ccy: str = Field(..., description="Asset currency")
    quantity: float = Field(..., description="Position quantity")
    avg_cost: float = Field(..., description="Average cost")
    u_pnl: float = Field(default=0.0, description="Unrealized P&L")
    realized_pnl: float = Field(default=0.0, description="Realized P&L")

    model_config = ConfigDict(extra="allow")


class SymbolIndicator(BaseModel):
    """Indicator data for a single symbol (e.g., XLU, XLK)."""
    close: float = Field(..., description="Latest closing price")
    ma20: float = Field(..., description="20-day moving average")
    ma50: float = Field(..., description="50-day moving average")

    model_config = ConfigDict(extra="allow")


class RatioIndicator(BaseModel):
    """Ratio indicator (e.g., XLK/XLU)."""
    pair: str = Field(..., description="Ratio pair (e.g., 'XLK/XLU')")
    value: float = Field(..., description="Current ratio value")
    ma20: float = Field(..., description="20-day MA of ratio")
    ma50: float = Field(..., description="50-day MA of ratio")
    slope5: float = Field(..., description="5-day slope: (value - value_5d_ago) / 5")

    model_config = ConfigDict(extra="allow")


class SectorRotationIndicators(BaseModel):
    """Sector rotation indicators (XLU/XLK based)."""
    as_of: str = Field(..., description="Indicator date (YYYY-MM-DD)")
    version: str = Field(..., description="Indicator version")
    source: str = Field(..., description="Data source (stub|yfinance|...)")
    XLU: SymbolIndicator = Field(..., description="XLU (Utilities) indicators")
    XLK: SymbolIndicator = Field(..., description="XLK (Technology) indicators")
    ratio: RatioIndicator = Field(..., description="XLK/XLU ratio indicators")

    model_config = ConfigDict(extra="allow")


class IndicatorsInput(BaseModel):
    """All indicators grouped by category."""
    sector_rotation: SectorRotationIndicators = Field(
        ..., description="Sector rotation indicators (XLU/XLK)"
    )

    model_config = ConfigDict(extra="allow")


class SignalsInput(BaseModel):
    """Optional signals (news, research) - reserved for future sprints."""
    news: List[dict] = Field(default_factory=list, description="News signals (reserved)")
    research: List[dict] = Field(default_factory=list, description="Research signals (reserved)")

    model_config = ConfigDict(extra="allow")


class InputSchema(BaseModel):
    """Strategy Engine Input Schema (FIXED CONTRACT).

    Fields can be ADDED but never REMOVED.
    All plugins must accept this schema.
    """
    schema_version: str = Field(default="1.0", description="Schema version")
    as_of: str = Field(..., description="Decision date (YYYY-MM-DD)")
    user_id: str = Field(..., description="User ID")
    base_ccy: str = Field(..., description="Base currency for reporting")
    positions: List[PositionInput] = Field(
        default_factory=list, description="Current positions from portfolio-service"
    )
    indicators: IndicatorsInput = Field(..., description="Market indicators")
    signals: SignalsInput = Field(
        default_factory=SignalsInput, description="Optional signals (news, research)"
    )

    model_config = ConfigDict(extra="allow")


# =============================================================================
# Output Schema Components
# =============================================================================

class FalsifiableTrigger(BaseModel):
    """A falsifiable trigger condition that would invalidate the recommendation.

    Example: XLK/XLU ratio crosses below MA50 → invalidates RISK_ON mode.
    """
    type: str = Field(..., description="Trigger type: 'indicator' | 'price' | 'time'")
    name: str = Field(..., description="Indicator/metric name (e.g., 'XLK/XLU')")
    condition: str = Field(..., description="Condition (e.g., 'cross_below_ma50')")
    value: float = Field(..., description="Current value for reference")

    model_config = ConfigDict(extra="allow")


class ActionConstraints(BaseModel):
    """Constraints for an action (cooldown, position limits)."""
    cooldown_days: int = Field(default=5, description="Trading cooldown (5 days)")
    max_position_pct: float = Field(
        default=0.0, description="Max position % (0 = no limit specified)"
    )

    model_config = ConfigDict(extra="allow")


class ActionItem(BaseModel):
    """Action recommendation for a specific position."""
    symbol: str = Field(..., description="Stock symbol")
    action: Action = Field(..., description="Recommended action: HOLD|TRIM|ADD|AVOID")
    reason: str = Field(..., description="Concise reason (no vague language)")
    constraints: ActionConstraints = Field(
        default_factory=ActionConstraints, description="Action constraints"
    )
    falsifiable_triggers: List[FalsifiableTrigger] = Field(
        default_factory=list, description="Conditions that would invalidate this action"
    )

    model_config = ConfigDict(extra="allow")


class Evidence(BaseModel):
    """Evidence block for audit/reproducibility."""
    engine: str = Field(default="strategy_engine", description="Engine name")
    plugin: str = Field(..., description="Plugin version (e.g., 'v1.4')")
    inputs_hash: str = Field(..., description="SHA256 of canonical InputSchema JSON")
    notes: List[str] = Field(default_factory=list, description="Additional notes")
    scoring_detail: Optional[dict] = Field(
        default=None, description="Detailed scoring breakdown"
    )

    model_config = ConfigDict(extra="allow")


class OutputSchema(BaseModel):
    """Strategy Engine Output Schema (FIXED CONTRACT).

    Must contain:
    - mode: Market regime (RISK_ON | RISK_OFF | TRANSITION)
    - decision: Portfolio decision (NO_ACTION | REDUCE_RISK | REBALANCE | WATCHLIST)
    - actions: Per-position recommendations with falsifiable triggers
    - evidence: Audit trail with inputs_hash
    """
    schema_version: str = Field(default="1.0", description="Schema version")
    as_of: str = Field(..., description="Decision date (YYYY-MM-DD)")
    user_id: str = Field(..., description="User ID")
    mode: Mode = Field(..., description="Market regime: RISK_ON | RISK_OFF | TRANSITION")
    decision: Decision = Field(
        ..., description="Decision: NO_ACTION | REDUCE_RISK | REBALANCE | WATCHLIST"
    )
    actions: List[ActionItem] = Field(
        default_factory=list, description="Per-position action recommendations"
    )
    evidence: Evidence = Field(..., description="Audit trail and evidence")

    model_config = ConfigDict(extra="allow")


# =============================================================================
# Error Response Schema
# =============================================================================

class MissingDataError(BaseModel):
    """Error response when required data is missing (503)."""
    status: str = Field(default="missing_data", description="Error status")
    missing_fields: List[str] = Field(..., description="List of missing fields")
    message: str = Field(..., description="Human-readable error message")

    model_config = ConfigDict(extra="allow")
