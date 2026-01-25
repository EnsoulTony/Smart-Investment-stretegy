"""Valuation Service - FastAPI Application

Sprint 1-4.B 骨架：提供估值層 API，透過 HTTP 從 portfolio-service 取數。
Sprint Next：添加 trades/summary 前置條件檢查
"""

import os
import re
import json
from typing import Optional
from datetime import date
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .portfolio_client import PortfolioClient
from .guardrails import validate_no_db_env


app = FastAPI(
    title="Valuation Service",
    description="估值層服務（Sprint 1-4.B），API-only 取數邊界",
    version="1.4.B-skeleton"
)

# 啟動時強制檢查：估值層不得持有 DB 連線設定
validate_no_db_env()


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
            "Guardrails: no direct DB libraries",
            "Precondition check: trades/summary before revalue"
        ]
    }


@app.post("/valuation/revalue", response_model=RevalueResponse)
async def revalue_positions(request: RevalueRequest):
    """重新估值（骨架版）
    
    流程：
    0. 檢查 trades 是否有資料（前置條件）
    1. 透過 HTTP 從 portfolio-service 取得 positions（帳務層數據）
    2. （未來）透過 FX provider 取得匯率
    3. （未來）透過 market data provider 取得市價
    4. （未來）計算 market_value 與 unrealized_pnl
    5. （未來）寫入 valuation_snapshots 表（估值層專屬表）
    
    Sprint 1-4.B：只實作骨架，確認 API-only 取數正常
    Sprint Next：增加 trades/summary 前置條件檢查
    """
    from datetime import date as date_module
    
    asof = request.asof_date or date_module.today()
    
    # 透過 HTTP client 取得帳務層數據
    client = PortfolioClient()
    
    # 前置條件檢查：trades 是否有資料
    try:
        trades_summary = await client.get_trades_summary(request.user_id)
        trades_count = trades_summary.get("trades_count", 0)
        
        if trades_count == 0:
            # 遮罩 evidence 中的環境變數（若有）
            evidence = trades_summary.get("evidence", {})
            masked_evidence = _mask_env_keys_in_evidence(evidence)
            
            return RevalueResponse(
                status="no_data",
                user_id=request.user_id,
                asof_date=asof,
                positions_count=0,
                message=f"前置條件不滿足：trades_count=0，需要先執行 sync。使用 tools/portfolio_refresh.sh {request.user_id} 自動執行完整流程。Evidence: {json.dumps(masked_evidence)}"
            )
    except Exception as e:
        # trades/summary 失敗，但不阻斷整個流程（前向相容）
        print(f"Warning: Failed to check trades summary: {e}")
    
    try:
        positions = await client.get_positions(request.user_id)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch positions from portfolio-service: {str(e)}"
        )
    
    # 骨架版：只回傳取數結果，不做實際估值
    return RevalueResponse(
        status="skeleton",
        user_id=request.user_id,
        asof_date=asof,
        positions_count=len(positions),
        message=f"骨架版：成功取得 {len(positions)} 筆 positions（未來將實作估值邏輯）"
    )


@app.get("/valuation/snapshots")
async def get_snapshots(user_id: str, asof_date: Optional[date] = None):
    """取得估值快照（骨架版）
    
    未來：從 valuation_snapshots 表查詢估值結果
    目前：從 portfolio-service 取得帳務數據（示範 API-only 取數）
    """
    client = PortfolioClient()
    
    try:
        positions = await client.get_positions(user_id)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch positions: {str(e)}"
        )
    
    # 骨架版：直接回傳帳務數據
    snapshots = [
        ValuationSnapshot(
            user_id=user_id,
            symbol=pos.get("symbol", ""),
            asset_ccy=pos.get("asset_ccy", ""),
            quantity=pos.get("quantity", 0.0),
            avg_cost=pos.get("avg_cost", 0.0)
        )
        for pos in positions
    ]
    
    return {
        "user_id": user_id,
        "asof_date": asof_date,
        "snapshots": snapshots,
        "message": "骨架版：回傳帳務數據（未來將實作估值邏輯）"
    }
