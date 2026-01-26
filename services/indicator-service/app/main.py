"""Indicator Service: FastAPI application entry point.

Provides market indicator APIs for strategy engine consumption.
"""

import os
from datetime import date
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse

from .schemas import SectorRotationResponse, ErrorResponse
from .providers import StubProvider


SERVICE_NAME = os.getenv("SERVICE_NAME", "indicator-service")
INDICATOR_PROVIDER = os.getenv("INDICATOR_PROVIDER", "stub")
INDICATOR_SCENARIO = os.getenv("INDICATOR_SCENARIO", "default")

app = FastAPI(
    title="Indicator Service",
    description="Market indicators API for strategy engine",
    version="0.1.0",
)


def get_provider():
    """Get indicator provider based on environment configuration.

    Returns:
        Provider instance (StubProvider by default)
    """
    if INDICATOR_PROVIDER == "stub":
        return StubProvider(scenario=INDICATOR_SCENARIO)
    # Future: add yfinance provider
    # elif INDICATOR_PROVIDER == "yfinance":
    #     from .providers.yfinance import YFinanceProvider
    #     return YFinanceProvider()
    else:
        raise ValueError(f"Unknown INDICATOR_PROVIDER: {INDICATOR_PROVIDER}")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "provider": INDICATOR_PROVIDER,
    }


@app.get(
    "/indicators/sector-rotation",
    tags=["indicators"],
    response_model=SectorRotationResponse,
    responses={
        200: {"model": SectorRotationResponse},
        422: {"model": ErrorResponse, "description": "Missing or invalid parameters"},
        503: {"model": ErrorResponse, "description": "Provider unavailable"},
    },
)
async def get_sector_rotation(
    symbols: str = Query(
        default="XLU,XLK",
        description="Comma-separated symbols (currently only XLU,XLK supported)",
    ),
    as_of: Optional[str] = Query(
        default=None,
        description="Indicator date (YYYY-MM-DD), default: today",
    ),
) -> SectorRotationResponse:
    """Get sector rotation indicators (XLU/XLK).

    Returns:
        - XLU: Utilities sector ETF indicators (close, ma20, ma50)
        - XLK: Technology sector ETF indicators (close, ma20, ma50)
        - ratio: XLK/XLU ratio with MA20, MA50, and slope5

    The slope5 is calculated as: (value - value_5d_ago) / 5

    Errors:
        - 422: Invalid symbols or date format
        - 503: Provider unavailable (e.g., network error for live provider)
    """
    # Validate symbols
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    required_symbols = {"XLU", "XLK"}

    if not required_symbols.issubset(set(symbol_list)):
        missing = required_symbols - set(symbol_list)
        raise HTTPException(
            status_code=422,
            detail={
                "status": "invalid_request",
                "message": f"Missing required symbols: {', '.join(missing)}",
                "missing_fields": [f"symbols.{s}" for s in missing],
            },
        )

    # Parse as_of date
    as_of_date: date
    if as_of:
        try:
            as_of_date = date.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "invalid_request",
                    "message": f"Invalid date format: {as_of}. Expected YYYY-MM-DD",
                    "missing_fields": ["as_of"],
                },
            )
    else:
        as_of_date = date.today()

    # Get provider
    try:
        provider = get_provider()
    except ValueError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "provider_error",
                "message": str(e),
                "missing_fields": [],
            },
        )

    # Fetch indicators
    try:
        data = provider.get_sector_rotation(as_of=as_of_date)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "provider_error",
                "message": f"Failed to fetch indicators: {str(e)}",
                "missing_fields": [],
            },
        )

    # Validate response completeness
    required_fields = [
        ("XLU", ["close", "ma20", "ma50"]),
        ("XLK", ["close", "ma20", "ma50"]),
        ("ratio", ["value", "ma20", "ma50", "slope5"]),
    ]

    missing_fields = []
    for section, fields in required_fields:
        if section not in data:
            missing_fields.append(section)
        else:
            for field in fields:
                if field not in data[section]:
                    missing_fields.append(f"{section}.{field}")

    if missing_fields:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "incomplete_data",
                "message": f"Provider returned incomplete data",
                "missing_fields": missing_fields,
            },
        )

    return SectorRotationResponse(**data)


@app.get("/indicators/providers", tags=["indicators"])
async def list_providers() -> dict:
    """List available indicator providers and scenarios."""
    return {
        "current_provider": INDICATOR_PROVIDER,
        "current_scenario": INDICATOR_SCENARIO,
        "available_providers": ["stub"],  # Future: add "yfinance"
        "stub_scenarios": StubProvider.available_scenarios(),
    }
