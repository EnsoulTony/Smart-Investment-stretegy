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
            
            try:
                response = await client.get(
                    url,
                    params={"user_id": user_id}
                )
                response.raise_for_status()
                
                data = response.json()
                
                # 回傳格式：[{symbol, asset_ccy, quantity, avg_cost, ...}]
                return data.get("positions", [])
            
            except httpx.HTTPError as e:
                # 骨架版：如果端點不存在，回傳空列表
                # 未來應該拋出異常
                print(f"Warning: Failed to fetch positions: {e}")
                return []
    
    async def health_check(self) -> Dict[str, Any]:
        """檢查 portfolio-service 健康狀態"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
