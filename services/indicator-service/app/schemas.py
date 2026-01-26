"""Indicator Service Schemas: API request/response models.

Fixed contract for sector rotation indicators.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class SymbolIndicatorResponse(BaseModel):
    """Indicator data for a single symbol (XLU or XLK)."""
    close: float = Field(..., description="Latest closing price")
    ma20: float = Field(..., description="20-day moving average")
    ma50: float = Field(..., description="50-day moving average")

    model_config = ConfigDict(extra="allow")


class RatioIndicatorResponse(BaseModel):
    """Ratio indicator (XLK/XLU)."""
    pair: str = Field(..., description="Ratio pair identifier")
    value: float = Field(..., description="Current ratio value (XLK.close / XLU.close)")
    ma20: float = Field(..., description="20-day MA of ratio")
    ma50: float = Field(..., description="50-day MA of ratio")
    slope5: float = Field(..., description="5-day slope: (value - value_5d_ago) / 5")
    value_5d_ago: float = Field(..., description="Ratio value 5 days ago")

    model_config = ConfigDict(extra="allow")


class SectorRotationResponse(BaseModel):
    """GET /indicators/sector-rotation response.

    Contains XLU, XLK indicators and their ratio.
    """
    as_of: str = Field(..., description="Indicator date (YYYY-MM-DD)")
    version: str = Field(..., description="API version")
    source: str = Field(..., description="Data source (stub|yfinance|...)")
    XLU: SymbolIndicatorResponse = Field(..., description="XLU (Utilities) indicators")
    XLK: SymbolIndicatorResponse = Field(..., description="XLK (Technology) indicators")
    ratio: RatioIndicatorResponse = Field(..., description="XLK/XLU ratio indicators")

    model_config = ConfigDict(extra="allow")


class ErrorResponse(BaseModel):
    """Error response for 4xx/5xx."""
    status: str = Field(..., description="Error status")
    message: str = Field(..., description="Human-readable error message")
    missing_fields: Optional[list[str]] = Field(
        default=None, description="Missing fields (for 422)"
    )

    model_config = ConfigDict(extra="allow")
