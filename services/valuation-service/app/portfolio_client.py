"""Portfolio Service HTTP Client

估值層與帳務層的唯一連接方式：HTTP API（禁止直接 DB 連線）

鐵律：
- 只能透過 HTTP 取數
- 禁止任何直接 DB library
- BASE_URL 由環境變數控制（可測試、可切換環境）
"""

import os
import httpx
from typing import List, Dict, Any


class PortfolioClient:
    """Portfolio Service HTTP Client
    
    取數來源：portfolio-service HTTP API
    禁止：直接查詢資料庫
    """
    
    def __init__(self):
        self.base_url = os.getenv(
            "PORTFOLIO_BASE_URL",
            "http://portfolio-service:8001"
        )
        self.timeout = float(os.getenv("PORTFOLIO_CLIENT_TIMEOUT", "10.0"))
    
    async def get_positions(self, user_id: str) -> List[Dict[str, Any]]:
        """取得用戶持倉（帳務層數據）
        
        Args:
            user_id: 用戶 ID
            
        Returns:
            持倉列表（帳務數據：quantity, avg_cost, asset_ccy）
            
        Raises:
            httpx.HTTPError: HTTP 請求失敗
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # 骨架版：假設 portfolio-service 提供此端點
            # 實際端點需要與 portfolio-service 協調
            url = f"{self.base_url}/portfolio/positions"
            
            response = await client.get(
                url,
                params={"user_id": user_id}
            )
            response.raise_for_status()

            data = response.json()

            # 回傳格式：{items: [...]}
            return data.get("items", data.get("positions", []))
    
    async def get_trades_summary(self, user_id: str) -> Dict[str, Any]:
        """取得交易記錄摘要（前置條件檢查）
        
        用途：
        - 在執行估值前先確認 trades 有資料
        - 若 trades_count=0，提示需要先 sync
        
        Args:
            user_id: 用戶 ID
            
        Returns:
            {
                "user_id": str,
                "trades_count": int,
                "symbols_count": int,
                "min_trade_date": str | None,
                "max_trade_date": str | None,
                "evidence": {...}
            }
            
        Raises:
            httpx.HTTPError: HTTP 請求失敗
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.base_url}/portfolio/trades/summary"
            
            response = await client.get(
                url,
                params={"user_id": user_id}
            )
            response.raise_for_status()
            
            return response.json()
    
    async def health_check(self) -> Dict[str, Any]:
        """檢查 portfolio-service 健康狀態"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
