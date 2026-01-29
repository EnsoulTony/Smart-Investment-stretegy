"""Radar Service: Strategy decision API.

Provides investment strategy recommendations using pluggable strategy engine.
"""

import os
from datetime import date
from typing import Optional

import httpx
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse

from .db import (
    fetch_news_signals,
    upsert_decision_snapshot,
    fetch_decision_history,
    build_news_inputs,
    insert_trigger_evaluations,
    fetch_trigger_history,
    fetch_trigger_analytics,
    fetch_decision_analytics,
)
from .news_fusion import (
    compute_news_score,
    apply_news_mode_override,
    build_triggers,
    attach_news_triggers,
)
from .strategy_engine import InputSchema, OutputSchema, get_default_engine
from .strategy_engine.engine import MissingDataException
from .strategy_engine.schemas import (
    PositionInput,
    IndicatorsInput,
    SectorRotationIndicators,
    SymbolIndicator,
    RatioIndicator,
    SignalsInput,
    FalsifiableTrigger,
)
from .utils.triggers import stable_trigger_key

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
async def health() -> dict[str, str | list[str]]:
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
        signals=SignalsInput(
            news=[],
            research=[],
        ),
    )

    # Fetch news_signals from DB (normal path)
    try:
        news_signals = fetch_news_signals(user_id=user_id, as_of=as_of_date)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "upstream_error",
                "service": "postgres",
                "message": f"DB read failed: {str(e)}",
            },
        )

    news_inputs = build_news_inputs(news_signals)
    input_schema.signals.news = news_inputs

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

    # News fusion: scoring + mode override + triggers
    n1_count = sum(1 for signal in news_signals if signal.get("tier") == "N1")
    n3_count = sum(1 for signal in news_signals if signal.get("tier") == "N3")
    score_impact = {
        "risk_off_score_added": compute_news_score(n1_count, n3_count),
        "n1_score": n1_count * 2.0,
        "n3_score": min(2.0, n3_count * 0.5),
    }

    n1_raw_triggers = []
    n3_raw_triggers = []
    items_used = []
    for signal in news_signals:
        payload = signal.get("payload") or {}
        tier = signal.get("tier") or payload.get("tier") or "N3"
        triggers = payload.get("falsifiable_triggers") or []
        items_used.append(
            {
                "item_id": signal.get("signal_id"),
                "tier": tier,
                "headline": payload.get("title") or payload.get("headline"),
                "published_at": payload.get("published_at"),
                "source": payload.get("source"),
                "falsifiable_triggers": triggers,
            }
        )
        if tier == "N1":
            n1_raw_triggers.extend(triggers)
        else:
            n3_raw_triggers.extend(triggers)

    news_trigger_evaluations, news_trigger_observed = _build_news_trigger_evaluations(items_used)

    n1_triggers = _enrich_news_triggers(build_triggers(n1_raw_triggers), "N1", news_trigger_observed)
    n3_triggers = _enrich_news_triggers(build_triggers(n3_raw_triggers), "N3", news_trigger_observed)

    output.actions, watchlist_triggers = attach_news_triggers(
        output.actions, n1_triggers, n3_triggers
    )

    original_mode = output.mode
    output.mode = apply_news_mode_override(output.mode, n1_count)
    if output.mode != original_mode:
        output.evidence.notes.append(
            f"news_fusion: mode override {original_mode.value} -> {output.mode.value}"
        )

    output.actions = _enrich_action_triggers(output.actions)

    output.evidence.news_context = {
        "tiers_count": {"N1": n1_count, "N3": n3_count},
        "items_used": items_used,
        "score_impact": score_impact,
        "watchlist_triggers": [t.model_dump() for t in watchlist_triggers],
        "primary_triggers": [t.model_dump() for t in n1_triggers],
    }

    # Persist decision snapshot (idempotent)
    try:
        upsert_decision_snapshot(
            user_id=user_id,
            as_of=as_of_date,
            plugin=plugin,
            mode=output.mode.value,
            decision=output.decision.value,
            inputs_hash=output.evidence.inputs_hash,
            payload=output.model_dump(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "upstream_error",
                "service": "postgres",
                "message": f"DB write failed: {str(e)}",
            },
        )

    try:
        insert_trigger_evaluations(
            user_id=user_id,
            as_of=as_of_date,
            plugin=plugin,
            decision_inputs_hash=output.evidence.inputs_hash,
            evaluations=news_trigger_evaluations,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "upstream_error",
                "service": "postgres",
                "message": f"DB write failed: {str(e)}",
            },
        )

    # Return OutputSchema
    return JSONResponse(content=output.model_dump())


def _extract_trigger_condition(trigger: dict) -> dict:
    return {
        "type": trigger.get("type"),
        "name": trigger.get("name"),
        "condition": trigger.get("condition"),
        "value": trigger.get("value"),
    }


def _build_news_trigger_evaluations(items_used: list[dict]) -> tuple[list[dict], dict]:
    evaluations = []
    observed_by_key: dict[str, dict] = {}

    for item in items_used:
        tier = item.get("tier") or "N3"
        observed_value = {
            "headline": item.get("headline"),
            "published_at": item.get("published_at"),
            "source": item.get("source"),
            "tier": tier,
        }
        if item.get("item_id"):
            observed_value["item_id"] = item.get("item_id")

        for trigger in item.get("falsifiable_triggers") or []:
            condition = _extract_trigger_condition(trigger)
            trigger_key = stable_trigger_key("news", tier, condition)
            evaluations.append(
                {
                    "trigger_key": trigger_key,
                    "trigger_type": "news",
                    "condition": condition,
                    "observed_value": observed_value,
                    "is_triggered": True,
                }
            )
            if trigger_key not in observed_by_key:
                observed_by_key[trigger_key] = observed_value

    return evaluations, observed_by_key


def _enrich_news_triggers(
    triggers: list[FalsifiableTrigger],
    tier: str,
    observed_by_key: dict,
) -> list[FalsifiableTrigger]:
    enriched = []
    for trigger in triggers:
        data = trigger.model_dump()
        trigger_key = stable_trigger_key("news", tier, data)
        observed_value = observed_by_key.get(trigger_key, {"tier": tier})
        enriched.append(
            FalsifiableTrigger.model_validate(
                {
                    **data,
                    "trigger_key": trigger_key,
                    "observed_value": observed_value,
                    "is_triggered": True,
                }
            )
        )
    return enriched


def _enrich_action_triggers(actions: list) -> list:
    enriched_actions = []
    for action in actions:
        enriched_triggers = []
        for trigger in action.falsifiable_triggers:
            data = trigger.model_dump()
            if (
                "trigger_key" in data
                and "observed_value" in data
                and "is_triggered" in data
            ):
                enriched_triggers.append(trigger)
                continue
            trigger_type = data.get("type") or "unknown"
            trigger_key = stable_trigger_key(trigger_type, "core", data)
            enriched_triggers.append(
                FalsifiableTrigger.model_validate(
                    {
                        **data,
                        "trigger_key": trigger_key,
                        "observed_value": data.get("observed_value") or {},
                        "is_triggered": False,
                    }
                )
            )
        action.falsifiable_triggers = enriched_triggers
        enriched_actions.append(action)
    return enriched_actions


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


@app.get("/radar/decisions/history", tags=["radar"])
async def get_decision_history(
    user_id: str = Query(..., description="User ID for decision history lookup"),
    limit: int = Query(default=30, ge=1, le=100, description="Max history rows"),
) -> list[dict]:
    """Return recent decision snapshots for a user."""
    try:
        return fetch_decision_history(user_id=user_id, limit=limit)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "upstream_error",
                "service": "postgres",
                "message": f"DB read failed: {str(e)}",
            },
        )


@app.get("/radar/triggers/history", tags=["radar"])
async def get_trigger_history(
    user_id: str = Query(..., description="User ID for trigger history lookup"),
    from_date: str = Query(..., alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: str = Query(..., alias="to", description="End date (YYYY-MM-DD)"),
    plugin: str = Query(default="v1.4", description="Strategy plugin"),
    trigger_type: Optional[str] = Query(default=None, description="Trigger type"),
    is_triggered: Optional[bool] = Query(default=None, description="Filter by triggered"),
    limit: int = Query(default=200, ge=1, le=500, description="Max rows"),
    offset: int = Query(default=0, ge=0, description="Offset"),
) -> dict:
    """Return trigger evaluation history for a user."""
    try:
        from_dt = date.fromisoformat(from_date)
        to_dt = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "invalid_request",
                "message": "Invalid date format. Expected YYYY-MM-DD",
            },
        )

    try:
        items = fetch_trigger_history(
            user_id=user_id,
            plugin=plugin,
            from_date=from_dt,
            to_date=to_dt,
            trigger_type=trigger_type,
            is_triggered=is_triggered,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "upstream_error",
                "service": "postgres",
                "message": f"DB read failed: {str(e)}",
            },
        )

    return {
        "schema_version": "1.0",
        "user_id": user_id,
        "plugin": plugin,
        "from": from_dt.isoformat(),
        "to": to_dt.isoformat(),
        "items": items,
    }


@app.get("/radar/analytics/triggers", tags=["radar"])
async def get_trigger_analytics(
    user_id: str = Query(..., description="User ID for analytics lookup"),
    from_date: str = Query(..., alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: str = Query(..., alias="to", description="End date (YYYY-MM-DD)"),
    plugin: str = Query(default="v1.4", description="Strategy plugin"),
    only_triggered: bool = Query(default=False, description="Only count triggered rows"),
) -> dict:
    """Return aggregated trigger outcome analytics for a user."""
    try:
        from_dt = date.fromisoformat(from_date)
        to_dt = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "invalid_request",
                "message": "Invalid date format. Expected YYYY-MM-DD",
            },
        )

    try:
        items = fetch_trigger_analytics(
            user_id=user_id,
            plugin=plugin,
            from_date=from_dt,
            to_date=to_dt,
            only_triggered=only_triggered,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "upstream_error",
                "service": "postgres",
                "message": f"DB read failed: {str(e)}",
            },
        )

    return {
        "schema_version": "1.0",
        "user_id": user_id,
        "plugin": plugin,
        "from": from_dt.isoformat(),
        "to": to_dt.isoformat(),
        "only_triggered": only_triggered,
        "items": items,
    }


@app.get("/radar/analytics/decisions", tags=["radar"])
async def get_decision_analytics(
    user_id: str = Query(..., description="User ID for analytics lookup"),
    from_date: str = Query(..., alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: str = Query(..., alias="to", description="End date (YYYY-MM-DD)"),
    plugin: str = Query(default="v1.4", description="Strategy plugin"),
    group_by: str = Query(default="tier", description="Group by tier or decision"),
) -> dict:
    """Return aggregated decision outcome analytics for a user."""
    try:
        from_dt = date.fromisoformat(from_date)
        to_dt = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "invalid_request",
                "message": "Invalid date format. Expected YYYY-MM-DD",
            },
        )

    if group_by not in {"tier", "decision"}:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "invalid_request",
                "message": "Invalid group_by. Expected 'tier' or 'decision'",
            },
        )

    try:
        items = fetch_decision_analytics(
            user_id=user_id,
            plugin=plugin,
            from_date=from_dt,
            to_date=to_dt,
            group_by=group_by,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "upstream_error",
                "service": "postgres",
                "message": f"DB read failed: {str(e)}",
            },
        )

    return {
        "schema_version": "1.0",
        "user_id": user_id,
        "plugin": plugin,
        "from": from_dt.isoformat(),
        "to": to_dt.isoformat(),
        "group_by": group_by,
        "items": items,
    }
