"""Valuation Service - FastAPI Application

Sprint 1-4.B 骨架：提供估值層 API，透過 HTTP 從 portfolio-service 取數。
"""

import os
from typing import Optional
from datetime import date
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .portfolio_client import PortfolioClient
from .guardrails import enforce_no_db_env


app = FastAPI(
    title="Valuation Service",
    description="估值層服務（Sprint 1-4.B），API-only 取數邊界",
    version="1.4.B-skeleton"
)

# 啟動時強制檢查：估值層不得持有 DB 連線設定
enforce_no_db_env()


# ============================================================================
# Schemas
# ============================================================================

class RevalueRequest(BaseModel):
    """重新估值請求"""
    user_id: str
    asof_date: Optional[date] = None  # None = 使用今日


class RevalueResponse(BaseModel):
    """重新估值回應"""
    status: str
    user_id: str
    asof_date: date
    positions_count: int
    message: str


class ValuationSnapshot(BaseModel):
    """估值快照（骨架版）"""
    user_id: str
    symbol: str
    asset_ccy: str
    quantity: float
    avg_cost: float
    # 未來擴充：market_price, market_value, unrealized_pnl


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    portfolio_base_url = os.getenv("PORTFOLIO_BASE_URL", "http://portfolio-service:8001")
    
    return {
        "status": "healthy",
        "service": "valuation-service",
        "version": "1.4.B-skeleton",
        "portfolio_base_url": portfolio_base_url,
        "capabilities": [
            "API-only data fetching (no DB connection)",
            "Skeleton endpoints for revalue & snapshots",
            "Guardrails: no direct DB libraries"
        ]
    }


@app.post("/valuation/revalue", response_model=RevalueResponse)
async def revalue_positions(request: RevalueRequest):
    """重新估值（骨架版）
    
    流程：
    1. 透過 HTTP 從 portfolio-service 取得 positions（帳務層數據）
    2. （未來）透過 FX provider 取得匯率
    3. （未來）透過 market data provider 取得市價
    4. （未來）計算 market_value 與 unrealized_pnl
    5. （未來）寫入 valuation_snapshots 表（估值層專屬表）
    
    Sprint 1-4.B：只實作骨架，確認 API-only 取數正常
    """
    from datetime import date as date_module
    
    asof = request.asof_date or date_module.today()
    
    # 透過 HTTP client 取得帳務層數據
    client = PortfolioClient()
    
    try:
        positions = await client.get_positions(request.user_id)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch positions from portfolio-service: {str(e)}"
        )
    
    # 骨架版：只回傳取數成功的訊息
    return RevalueResponse(
        status="succeeded",
        user_id=request.user_id,
        asof_date=asof,
        positions_count=len(positions),
        message=f"Skeleton: fetched {len(positions)} positions via HTTP (no valuation yet)"
    )


@app.get("/valuation/snapshots")
async def get_valuation_snapshots(
    user_id: str,
    asof: Optional[str] = None
):
    """取得估值快照（骨架版）
    
    Sprint 1-4.B：透過 HTTP 從 portfolio-service 取得帳務數據，
    未來才會加上市價與未實現損益計算。
    """
    # 透過 HTTP client 取得帳務層數據
    client = PortfolioClient()
    
    try:
        positions = await client.get_positions(user_id)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch positions from portfolio-service: {str(e)}"
        )
    
    # 骨架版：只回傳帳務數據（未加市價與估值）
    snapshots = [
        ValuationSnapshot(
            user_id=user_id,
            symbol=pos["symbol"],
            asset_ccy=pos["asset_ccy"],
            quantity=pos["quantity"],
            avg_cost=pos["avg_cost"]
        )
        for pos in positions
    ]
    
    return {
        "user_id": user_id,
        "asof": asof,
        "snapshots": snapshots,
        "note": "Skeleton: accounting data only (no market price or unrealized PnL yet)"
    }
