"""Valuation Service - FastAPI Application

Sprint 1-4.B 骨架：提供估值層 API，透過 HTTP 從 portfolio-service 取數。
Sprint Next：添加 trades/summary 前置條件檢查
"""

import os
import re
import json
import hashlib
from typing import Optional, Any
from decimal import Decimal
from datetime import date
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .portfolio_client import PortfolioClient
from .guardrails import validate_runtime_env
from .providers import PriceProvider, FxProvider


app = FastAPI(
    title="Valuation Service",
    description="估值層服務（Sprint 1-4.B），API-only 取數邊界",
    version="1.4.B-skeleton"
)

# 啟動時強制檢查：估值層不得持有 DB 連線設定
RUNTIME_GUARD_STATUS = validate_runtime_env()


# ============================================================================
# Utility Functions
# ============================================================================

def _mask_env_keys_in_evidence(evidence: dict) -> dict:
    """遮罩 evidence 中的環境變數值（安全考慮）
    
    策略：
    - user_id 可以明文顯示（業務識別符）
    - 任何 env key（資料庫連線字串、API_KEY 等）必須遮罩
    - verification_sql 中的 user_id 保留（供手動驗證）
    
    Args:
        evidence: 原始 evidence dict
        
    Returns:
        遮罩後的 evidence dict
    """
    # 深度複製（避免修改原始 dict）
    masked = json.loads(json.dumps(evidence))
    
    # 需要遮罩的 key pattern（大小寫不敏感）
    env_key_patterns = [
        r'.*_URL$',
        r'.*_KEY$',
        r'.*_SECRET$',
        r'.*_PASSWORD$',
        r'.*_TOKEN$',
        r'DATABASE.*',
    ]
    
    def mask_value(key: str, value: any) -> any:
        """判斷是否需要遮罩"""
        if not isinstance(value, str):
            return value
        
        for pattern in env_key_patterns:
            if re.match(pattern, key, re.IGNORECASE):
                # 遮罩格式：顯示前 3 字元 + ***
                if len(value) > 3:
                    return value[:3] + "***"
                else:
                    return "***"
        
        return value
    
    def mask_dict(d: dict) -> dict:
        """遞迴遮罩 dict"""
        result = {}
        for k, v in d.items():
            if isinstance(v, dict):
                result[k] = mask_dict(v)
            elif isinstance(v, list):
                result[k] = [mask_dict(item) if isinstance(item, dict) else item for item in v]
            else:
                result[k] = mask_value(k, v)
        return result
    
    return mask_dict(masked)


def _canonical_json_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


# ============================================================================
# Schemas
# ============================================================================

class ValuationItem(BaseModel):
    """估值結果項目"""
    symbol: str
    asset_ccy: str
    quantity: float
    avg_cost: float
    price: float
    price_ccy: str
    base_ccy: str
    fx_rate_to_base: float
    market_value: float
    unrealized_pnl: float


class ValuationResponse(BaseModel):
    """估值回應"""
    status: str
    user_id: str
    base_ccy: str
    as_of: date
    items: list[ValuationItem]
    evidence: dict


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    portfolio_base_url = os.getenv("PORTFOLIO_BASE_URL", "http://portfolio-service:8001")

    return {
        "status": "healthy",
        "service_name": "valuation-service",
        "portfolio_base_url": portfolio_base_url,
        "providers": {
            "price_provider": PriceProvider.provider_name(),
            "fx_provider": FxProvider.provider_name(),
        },
        "runtime_guard_status": RUNTIME_GUARD_STATUS,
    }


@app.get("/valuation/portfolio", response_model=ValuationResponse)
async def valuation_portfolio(user_id: str, base_ccy: str = "USD", as_of: Optional[date] = None):
    """估值 API（Sprint 1-4.B）"""
    as_of = as_of or date.today()

    client = PortfolioClient()
    try:
        trades_summary = await client.get_trades_summary(user_id)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "upstream_error",
                "service": "portfolio-service",
                "operation": "trades_summary",
                "message": str(e),
            },
        )

    trades_count = int(trades_summary.get("trades_count", 0))
    symbols_count = int(trades_summary.get("symbols_count", 0))
    verification_sql = trades_summary.get("evidence", {}).get("verification_sql", {})

    if trades_count == 0:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "precondition_failed",
                "user_id": user_id,
                "message": "trades_count=0;請先執行 sync",
                "evidence": {
                    "trades_count": trades_count,
                    "distinct_symbols_count": symbols_count,
                    "verification_sql": verification_sql,
                },
            },
        )

    positions_payload = await client.get_positions(user_id)
    positions_items = positions_payload
    positions_items = sorted(
        positions_items,
        key=lambda item: (item.get("symbol", ""), item.get("asset_ccy", "")),
    )

    price_provider = PriceProvider()
    fx_provider = FxProvider()

    items: list[ValuationItem] = []
    for pos in positions_items:
        symbol = pos.get("symbol", "")
        asset_ccy = pos.get("asset_ccy", "")
        qty = _to_decimal(pos.get("quantity", 0))
        avg_cost = _to_decimal(pos.get("avg_cost", 0))

        price, price_ccy, source = price_provider.get_price(symbol, as_of)
        rate = fx_provider.get_rate(price_ccy, base_ccy, as_of)

        market_value = (qty * price * rate)
        unrealized = (price - avg_cost) * qty * rate

        items.append(
            ValuationItem(
                symbol=symbol,
                asset_ccy=asset_ccy,
                quantity=float(qty),
                avg_cost=float(avg_cost),
                price=float(price),
                price_ccy=price_ccy,
                base_ccy=base_ccy,
                fx_rate_to_base=float(rate),
                market_value=float(market_value),
                unrealized_pnl=float(unrealized),
            )
        )

    evidence = {
        "positions_count": len(positions_items),
        "positions_hash": _canonical_json_hash(positions_items),
        "trades_count": trades_count,
        "distinct_symbols_count": symbols_count,
        "verification_sql": verification_sql,
        "providers": {
            "price_provider": price_provider.provider_name(),
            "fx_provider": fx_provider.provider_name(),
            "price_source": price_provider.source(),
            "as_of": as_of.isoformat(),
        },
    }

    return ValuationResponse(
        status="succeeded",
        user_id=user_id,
        base_ccy=base_ccy,
        as_of=as_of,
        items=items,
        evidence=_mask_env_keys_in_evidence(evidence),
    )
