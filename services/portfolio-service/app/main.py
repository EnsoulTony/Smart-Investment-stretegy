"""Portfolio Service 的 FastAPI 進入點。"""

import os
import logging
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.sync_service import SyncService
from app.position_rebuilder import PositionRebuilder
from app.schemas import RebuildPositionsRequest, RebuildPositionsResponse

SERVICE_NAME = os.getenv("SERVICE_NAME", "portfolio-service")
app = FastAPI(title="Portfolio Service", version="0.1.0")

# 設定 logger
logger = logging.getLogger(__name__)


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
        # 輸出完整 traceback 到 logs
        logger.exception("Unhandled error in /portfolio/sync: %s", e)
        
        # 同步失敗：回傳 500 錯誤
        raise HTTPException(
            status_code=500,
            detail=f"同步失敗：{str(e)}"
        )


@app.post("/portfolio/rebuild_positions", tags=["portfolio"], response_model=RebuildPositionsResponse)
def rebuild_positions(
    request: RebuildPositionsRequest,
    db: Session = Depends(get_db)
) -> dict:
    """重算指定用戶的持倉狀態。
    
    從 trades 表重新計算當前持倉數量、平均成本與已實現損益。
    
    流程（當前階段僅骨架）：
    1. 讀取該用戶的所有交易記錄
    2. 按 symbol 分組並依序計算（下階段實作均價法）
    3. 寫入 positions_snapshot 表（下階段實作）
    
    Args:
        request: 包含 user_id 的請求 body
        db: SQLAlchemy Session（依賴注入）
    
    Returns:
        dict: 重算結果
            - status: 執行狀態（"succeeded" 或 "failed"）
            - rebuilt_symbols_count: 重算的標的數量
            - warnings: 警告訊息列表
    
    Raises:
        HTTPException:
            - 422: user_id 缺失或格式錯誤（Pydantic 自動驗證）
            - 500: 重算過程發生錯誤
    
    Notes:
        - TODO: 加入身份驗證（JWT/API Key）
        - 當前階段（Sprint 1-4.0）僅回傳固定結構
        - 下階段（Sprint 1-4.1）將實作均價法計算邏輯
    """
    try:
        rebuilder = PositionRebuilder(session=db)
        result = rebuilder.rebuild_positions(user_id=request.user_id)
        return result
        
    except ValueError as e:
        # 驗證錯誤（例如：user_id 為空）
        logger.warning("重算持倉驗證失敗，user_id=%s, error=%s", request.user_id, e)
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
        
    except Exception as e:
        # 其他錯誤（DB 連線失敗、計算錯誤等）
        logger.exception("重算持倉失敗，user_id=%s", request.user_id)
        raise HTTPException(
            status_code=500,
            detail=f"重算持倉失敗：{str(e)}"
        )
