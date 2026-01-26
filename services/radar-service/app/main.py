"""Radar Service: Strategy decision API.

Provides investment strategy recommendations using pluggable strategy engine.
"""

import os
from datetime import date
from typing import Optional

import httpx
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse

from .strategy_engine import InputSchema, OutputSchema, get_default_engine
from .strategy_engine.engine import MissingDataException
from .strategy_engine.schemas import (
    PositionInput,
    IndicatorsInput,
    SectorRotationIndicators,
    SymbolIndicator,
    RatioIndicator,
    SignalsInput,
)

SERVICE_NAME = os.getenv("SERVICE_NAME", "radar-service")
PORTFOLIO_BASE_URL = os.getenv("PORTFOLIO_BASE_URL", "http://portfolio-service:8001")
INDICATOR_BASE_URL = os.getenv("INDICATOR_BASE_URL", "http://indicator-service:8006")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10.0"))

app = FastAPI(
    title="Radar Service",
    description="Investment strategy recommendations with pluggable strategy engine",
    version="0.2.0",
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Health check endpoint."""
    engine = get_default_engine()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "plugins": engine.list_plugins(),
    }


@app.get(
    "/radar/decision",
    tags=["radar"],
    responses={
        200: {"description": "Strategy decision output"},
        422: {"description": "Invalid parameters"},
        502: {"description": "Upstream service error"},
        503: {"description": "Missing required data"},
    },
)
async def get_decision(
    user_id: str = Query(..., description="User ID for position lookup"),
    base_ccy: str = Query(default="TWD", description="Base currency for reporting"),
    plugin: str = Query(default="v1.4", description="Strategy plugin to use"),
    as_of: Optional[str] = Query(default=None, description="Decision date (YYYY-MM-DD)"),
):
    """Get strategy decision for a user.

    Flow:
    1. Fetch positions from portfolio-service
    2. Fetch indicators from indicator-service
    3. Execute strategy plugin
    4. Return OutputSchema with decision and evidence

    Error handling:
    - 422: Invalid parameters
    - 502: Upstream service unavailable
    - 503: Missing required data for strategy execution
    """
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
                },
            )
    else:
        as_of_date = date.today()

    as_of_str = as_of_date.isoformat()

    # Get strategy engine
    engine = get_default_engine()
    if plugin not in engine.list_plugins():
        raise HTTPException(
            status_code=422,
            detail={
                "status": "invalid_plugin",
                "message": f"Plugin '{plugin}' not found. Available: {engine.list_plugins()}",
            },
        )

    # Fetch data from upstream services
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        # Fetch positions from portfolio-service
        try:
            positions_response = await client.get(
                f"{PORTFOLIO_BASE_URL}/portfolio/positions",
                params={"user_id": user_id},
            )
            positions_response.raise_for_status()
            positions_data = positions_response.json()
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "status": "upstream_error",
                    "service": "portfolio-service",
                    "message": f"Connection error: {str(e)}",
                },
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "status": "upstream_error",
                    "service": "portfolio-service",
                    "message": f"HTTP {e.response.status_code}: {e.response.text}",
                },
            )

        # Fetch indicators from indicator-service
        try:
            indicators_response = await client.get(
                f"{INDICATOR_BASE_URL}/indicators/sector-rotation",
                params={"symbols": "XLU,XLK", "as_of": as_of_str},
            )
            indicators_response.raise_for_status()
            indicators_data = indicators_response.json()
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "status": "upstream_error",
                    "service": "indicator-service",
                    "message": f"Connection error: {str(e)}",
                },
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "status": "upstream_error",
                    "service": "indicator-service",
                    "message": f"HTTP {e.response.status_code}: {e.response.text}",
                },
            )

    # Transform positions to InputSchema format
    positions = _transform_positions(positions_data)

    # Transform indicators to InputSchema format
    try:
        indicators = _transform_indicators(indicators_data)
    except KeyError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "missing_data",
                "message": f"Indicator data missing field: {str(e)}",
                "missing_fields": [str(e)],
            },
        )

    # Build InputSchema
    input_schema = InputSchema(
        schema_version="1.0",
        as_of=as_of_str,
        user_id=user_id,
        base_ccy=base_ccy,
        positions=positions,
        indicators=indicators,
        signals=SignalsInput(news=[], research=[]),
    )

    # Execute strategy plugin
    try:
        output = engine.execute(plugin, input_schema)
    except MissingDataException as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "missing_data",
                "message": e.message,
                "missing_fields": e.missing_fields,
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "plugin_error",
                "message": str(e),
            },
        )

    # Return OutputSchema
    return JSONResponse(content=output.model_dump())


def _transform_positions(positions_data: dict) -> list[PositionInput]:
    """Transform portfolio-service response to PositionInput list.

    Args:
        positions_data: Response from GET /portfolio/positions

    Returns:
        List of PositionInput
    """
    items = positions_data.get("items", [])
    positions = []

    for item in items:
        # Skip zero-quantity positions
        qty = float(item.get("quantity", 0))
        if qty == 0:
            continue

        positions.append(PositionInput(
            symbol=item.get("symbol", ""),
            asset_ccy=item.get("asset_ccy", "USD"),
            quantity=qty,
            avg_cost=float(item.get("avg_cost", 0)),
            u_pnl=float(item.get("u_pnl", 0)),
            realized_pnl=float(item.get("realized_pnl", 0)),
        ))

    return positions


def _transform_indicators(indicators_data: dict) -> IndicatorsInput:
    """Transform indicator-service response to IndicatorsInput.

    Args:
        indicators_data: Response from GET /indicators/sector-rotation

    Returns:
        IndicatorsInput with sector_rotation data

    Raises:
        KeyError: If required field is missing
    """
    return IndicatorsInput(
        sector_rotation=SectorRotationIndicators(
            as_of=indicators_data["as_of"],
            version=indicators_data["version"],
            source=indicators_data["source"],
            XLU=SymbolIndicator(
                close=indicators_data["XLU"]["close"],
                ma20=indicators_data["XLU"]["ma20"],
                ma50=indicators_data["XLU"]["ma50"],
            ),
            XLK=SymbolIndicator(
                close=indicators_data["XLK"]["close"],
                ma20=indicators_data["XLK"]["ma20"],
                ma50=indicators_data["XLK"]["ma50"],
            ),
            ratio=RatioIndicator(
                pair=indicators_data["ratio"]["pair"],
                value=indicators_data["ratio"]["value"],
                ma20=indicators_data["ratio"]["ma20"],
                ma50=indicators_data["ratio"]["ma50"],
                slope5=indicators_data["ratio"]["slope5"],
            ),
        ),
    )


@app.get("/radar/plugins", tags=["radar"])
async def list_plugins() -> dict:
    """List available strategy plugins."""
    engine = get_default_engine()
    plugins_info = []

    for name in engine.list_plugins():
        plugin = engine.get_plugin(name)
        if plugin:
            plugins_info.append({
                "name": name,
                "version": plugin.plugin_version,
            })

    return {
        "plugins": plugins_info,
        "default": "v1.4",
    }
