"""Valuation Service - FastAPI Application

Sprint 1-4.B：估值層 API，透過 HTTP 從 portfolio-service 取數。

鐵律：
- 禁止 DB 直連（透過 guardrails 強制）
- 只能透過 PORTFOLIO_BASE_URL (HTTP) 取數
- 前置條件檢查：trades_count=0 時回 409
"""

import os
import json
import hashlib
from typing import Optional, Any, List
from decimal import Decimal
from datetime import date
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .portfolio_client import PortfolioClient
from .guardrails import validate_runtime_env, GUARDRAIL_ID, GUARDRAIL_VERSION
from .providers import (
    PriceProvider, FxProvider,
    get_price_provider, get_fx_provider,
    PROVIDER_VERSION,
)


app = FastAPI(
    title="Valuation Service",
    description="估值層服務（Sprint 1-4.B），API-only 取數邊界",
    version="1.4.B"
)

# 啟動時強制檢查：估值層不得持有 DB 連線設定
RUNTIME_GUARD_STATUS = validate_runtime_env()


# ============================================================================
# Utility Functions
# ============================================================================

def _get_masked_env_keys() -> List[str]:
    """取得當前環境變數的 key 列表（只顯示 key，value 一律遮罩）"""
    return [f"{key}=***" for key in sorted(os.environ.keys())]


def _canonical_json_hash(payload: Any) -> str:
    """計算 payload 的 canonical JSON hash"""
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_decimal(value: Any) -> Decimal:
    """安全轉換為 Decimal"""
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


# ============================================================================
# Pydantic Schemas
# ============================================================================

class PositionItem(BaseModel):
    """單一持倉的估值結果"""
    symbol: str
    asset_ccy: str
    quantity: float
    avg_cost: float
    cost_value: float        # quantity * avg_cost (in base_ccy)
    price: float
    price_ccy: str
    market_value: float      # quantity * price * fx_rate (in base_ccy)
    unrealized_pnl: float    # market_value - cost_value


class Totals(BaseModel):
    """估值總計"""
    market_value: float      # 總市值
    cost_value: float        # 總成本
    unrealized_pnl: float    # 總未實現損益


class PreconditionSnapshot(BaseModel):
    """前置條件快照"""
    trades_count: int
    distinct_symbols_count: int


class Verification(BaseModel):
    """驗證資訊（可證偽）"""
    portfolio_service_endpoints_called: List[str]
    trades_summary_sql: dict
    as_of: str


class Providers(BaseModel):
    """Provider 資訊"""
    price_provider: str
    price_provider_version: str
    fx_provider: str
    fx_provider_version: str


class Evidence(BaseModel):
    """可證偽 evidence"""
    decision: str            # proceed / blocked_precondition
    precondition_snapshot: PreconditionSnapshot
    verification: Verification
    providers: Providers
    positions_count: int
    positions_hash: str
    masked_env_keys: List[str]


class ValuationResponse(BaseModel):
    """估值 API 回應"""
    status: str
    user_id: str
    base_ccy: str
    as_of: str
    totals: Totals
    positions: List[PositionItem]
    evidence: Evidence


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    portfolio_base_url = os.getenv("PORTFOLIO_BASE_URL", "http://portfolio-service:8001")

    price_provider = get_price_provider()
    fx_provider = get_fx_provider()

    return JSONResponse(content={
        "status": "healthy",
        "service_name": "valuation-service",
        "version": "1.4.B",
        "portfolio_base_url": portfolio_base_url,
        "providers": {
            "price_provider": price_provider.provider_name(),
            "price_provider_version": price_provider.provider_version(),
            "fx_provider": fx_provider.provider_name(),
            "fx_provider_version": fx_provider.provider_version(),
        },
        "guardrail": {
            "id": GUARDRAIL_ID,
            "version": GUARDRAIL_VERSION,
            "status": RUNTIME_GUARD_STATUS.get("status", "unknown"),
        },
    })


@app.get("/valuation/portfolio")
async def valuation_portfolio(
    user_id: str,
    base_ccy: str = "USD",
    as_of: Optional[date] = None
):
    """估值 API（Sprint 1-4.B）

    流程：
    1. 呼叫 portfolio-service /trades/summary 檢查前置條件
    2. 若 trades_count=0 → 409 Conflict
    3. 呼叫 portfolio-service /positions 取得帳務數據
    4. 使用 PriceProvider/FxProvider 計算估值
    5. 回傳結構化 JSON（含 totals + positions + evidence）

    Args:
        user_id: 用戶 ID
        base_ccy: 基準幣別（預設 USD）
        as_of: 估值日期（預設今天）

    Returns:
        ValuationResponse: 結構化估值結果

    Raises:
        409: trades_count=0（前置條件不足）
        502: portfolio-service 連線失敗
    """
    as_of = as_of or date.today()
    as_of_str = as_of.isoformat()

    client = PortfolioClient()
    endpoints_called: List[str] = []

    # Step 1: 前置條件檢查
    try:
        trades_summary = await client.get_trades_summary(user_id)
        endpoints_called.append(f"GET /portfolio/trades/summary?user_id={user_id}")
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={
                "detail": {
                    "status": "upstream_error",
                    "service": "portfolio-service",
                    "operation": "trades_summary",
                    "message": str(e),
                }
            },
            media_type="application/json",
        )

    trades_count = int(trades_summary.get("trades_count", 0))
    symbols_count = int(trades_summary.get("symbols_count", 0))
    verification_sql = trades_summary.get("evidence", {}).get("verification_sql", {})

    # Step 2: 前置條件失敗
    if trades_count == 0:
        precondition_evidence = {
            "decision": "blocked_precondition",
            "trades_count": trades_count,
            "distinct_symbols_count": symbols_count,
            "verification_sql": verification_sql,
            "portfolio_service_endpoints_called": endpoints_called,
            "masked_env_keys": _get_masked_env_keys(),
        }

        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "status": "precondition_failed",
                    "user_id": user_id,
                    "message": "trades_count=0;請先執行 sync",
                    "evidence": precondition_evidence,
                }
            },
            media_type="application/json",
        )

    # Step 3: 取得持倉
    try:
        positions_payload = await client.get_positions(user_id)
        endpoints_called.append(f"GET /portfolio/positions?user_id={user_id}")
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={
                "detail": {
                    "status": "upstream_error",
                    "service": "portfolio-service",
                    "operation": "get_positions",
                    "message": str(e),
                }
            },
            media_type="application/json",
        )

    positions_items = sorted(
        positions_payload,
        key=lambda item: (item.get("symbol", ""), item.get("asset_ccy", "")),
    )

    # Step 4: 估值計算
    price_provider = get_price_provider()
    fx_provider = get_fx_provider()

    positions: List[dict] = []
    total_market_value = Decimal("0")
    total_cost_value = Decimal("0")
    total_unrealized_pnl = Decimal("0")

    for pos in positions_items:
        symbol = pos.get("symbol", "")
        asset_ccy = pos.get("asset_ccy", "")
        qty = _to_decimal(pos.get("quantity", 0))
        avg_cost = _to_decimal(pos.get("avg_cost", 0))

        # 成本價值（原幣別）
        cost_value_raw = qty * avg_cost

        # 取得市價與匯率
        price, price_ccy, _ = price_provider.get_price(symbol, as_of)
        rate = fx_provider.get_rate(price_ccy, base_ccy, as_of)

        # 市值（目標幣別）
        market_value = qty * price * rate

        # 成本也需要折算到目標幣別
        cost_rate = fx_provider.get_rate(asset_ccy, base_ccy, as_of)
        cost_value = cost_value_raw * cost_rate

        # 未實現損益
        unrealized_pnl = market_value - cost_value

        positions.append({
            "symbol": symbol,
            "asset_ccy": asset_ccy,
            "quantity": float(qty),
            "avg_cost": float(avg_cost),
            "cost_value": float(cost_value),
            "price": float(price),
            "price_ccy": price_ccy,
            "market_value": float(market_value),
            "unrealized_pnl": float(unrealized_pnl),
        })

        total_market_value += market_value
        total_cost_value += cost_value
        total_unrealized_pnl += unrealized_pnl

    # Step 5: 建構回應
    response_data = {
        "status": "succeeded",
        "user_id": user_id,
        "base_ccy": base_ccy,
        "as_of": as_of_str,
        "totals": {
            "market_value": float(total_market_value),
            "cost_value": float(total_cost_value),
            "unrealized_pnl": float(total_unrealized_pnl),
        },
        "positions": positions,
        "evidence": {
            "decision": "proceed",
            "precondition_snapshot": {
                "trades_count": trades_count,
                "distinct_symbols_count": symbols_count,
            },
            "verification": {
                "portfolio_service_endpoints_called": endpoints_called,
                "trades_summary_sql": verification_sql,
                "as_of": as_of_str,
            },
            "providers": {
                "price_provider": price_provider.provider_name(),
                "price_provider_version": price_provider.provider_version(),
                "fx_provider": fx_provider.provider_name(),
                "fx_provider_version": fx_provider.provider_version(),
            },
            "positions_count": len(positions_items),
            "positions_hash": _canonical_json_hash(positions_items),
            "masked_env_keys": _get_masked_env_keys(),
        },
    }

    return JSONResponse(
        content=response_data,
        media_type="application/json",
    )
