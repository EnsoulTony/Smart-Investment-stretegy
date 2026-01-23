"""Portfolio Service 的 FastAPI 進入點。"""

import os
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.sync_service import SyncService

SERVICE_NAME = os.getenv("SERVICE_NAME", "portfolio-service")
app = FastAPI(title="Portfolio Service", version="0.1.0")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """健康檢查端點，確認投資組合服務是否存活。"""
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/portfolio/sync", tags=["portfolio"])
def sync_trades(db: Session = Depends(get_db)) -> dict:
    """同步 Google Sheets 交易流水帳到資料庫。
    
    流程：
    1. 從 Google Sheets 讀取交易資料
    2. 標準化與驗證
    3. 寫入 trades 表（使用 source_hash 去重）
    4. 記錄同步結果到 sync_runs 表
    
    Returns:
        dict: 同步結果
            - run_id: 同步執行 ID
            - inserted_count: 實際插入筆數
            - updated_count: 更新筆數（目前固定為 0）
            - skipped_count: 跳過筆數（重複 + 驗證失敗）
            - errors_count: 驗證失敗筆數
            - status: 同步狀態（"succeeded" 或 "failed"）
    
    Raises:
        HTTPException: 
            - 500: 同步過程發生錯誤（Google Sheets 連線失敗、DB 寫入失敗等）
    
    Notes:
        - TODO: 未來需加入身份驗證（JWT/API Key）
        - 使用 ON CONFLICT DO NOTHING 避免重複插入
        - 驗證失敗的資料會被跳過，但不影響整體同步狀態
    """
    try:
        # TODO: 加入身份驗證
        # if not check_auth(request):
        #     raise HTTPException(status_code=401, detail="Unauthorized")
        
        sync_service = SyncService(session=db)
        result = sync_service.run_sync()
        
        return result.to_dict()
        
    except Exception as e:
        # 同步失敗：回傳 500 錯誤
        raise HTTPException(
            status_code=500,
            detail=f"同步失敗：{str(e)}"
        )
