"""Portfolio Service 的 FastAPI 進入點。"""

import os
import logging
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from .schemas import RebuildPositionsRequest, RebuildPositionsResponse, PositionsResponse

from app.db import get_db, engine
from app.sync_service import SyncService
from app.position_rebuilder import PositionRebuilder, preview_rebuild
from app.schemas import RebuildPositionsRequest, RebuildPositionsResponse
from app.repositories.positions_repository import list_positions_for_user

SERVICE_NAME = os.getenv("SERVICE_NAME", "portfolio-service")
app = FastAPI(title="Portfolio Service", version="0.1.0")

# 設定 logger
logger = logging.getLogger(__name__)


@app.on_event("startup")
def verify_db_schema() -> None:
    """啟動時檢查 DB schema 與關鍵欄位是否存在。"""
    try:
        inspector = inspect(engine)
        if not inspector.has_table("positions"):
            logger.error("DB schema mismatch: positions table missing")
            return

        columns = {col["name"] for col in inspector.get_columns("positions")}
        required = {
            "user_id",
            "symbol",
            "asset_ccy",
            "quantity",
            "avg_cost",
            "realized_pnl",
            "u_pnl",
            "last_updated_at",
        }

        missing = sorted(required - columns)
        if missing:
            logger.error("DB schema mismatch: positions missing columns: %s", ", ".join(missing))
    except Exception as exc:
        logger.error("DB schema check failed: %s", exc)


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


@app.post("/portfolio/rebuild_positions/preview", tags=["portfolio"])
def preview_rebuild_positions(
    request: RebuildPositionsRequest,
    db: Session = Depends(get_db)
) -> dict:
    """預覽持倉重算結果（不寫入 DB）。
    
    功能：
    - 從 trades 表查詢用戶的所有交易記錄
    - 按 (symbol, asset_ccy) 分組並計算均價法
    - 回傳計算結果的預覽資料（不寫入 positions 表）
    
    與 POST /portfolio/rebuild_positions 的差異：
    - preview: 只計算不寫入，回傳詳細資料供檢視
    - rebuild: 計算後寫入 positions 表（Sprint 1-4.3 實作）
    
    使用場景：
    - 用戶想查看重算結果但不實際執行
    - 開發/測試時驗證計算邏輯
    - 前端顯示預覽畫面
    
    Args:
        request: 包含 user_id 的請求 body
        db: SQLAlchemy Session（依賴注入）
    
    Returns:
        dict: 預覽結果
            - status: "succeeded" 或 "failed"
            - user_id: 使用者 ID
            - symbols: 持倉列表
              [{
                "symbol": 股票代碼,
                "asset_ccy": 幣別,
                "qty": 持倉數量,
                "avg_cost": 平均成本,
                "realized_pnl": 已實現損益,
                "total_fee": 累計手續費,
                "trades_count": 交易筆數
              }]
            - warnings: 警告訊息列表（計算失敗的標的）
    
    Raises:
        HTTPException:
            - 422: user_id 缺失或格式錯誤（Pydantic 自動驗證）
            - 500: 預覽過程發生錯誤
    
    Notes:
        - TODO: 加入身份驗證（JWT/API Key）
        - 當前階段（Sprint 1-4.2）實作預覽功能
        - 下階段（Sprint 1-4.3）實作實際寫入
    """
    try:
        result = preview_rebuild(user_id=request.user_id, db=db)
        return result
        
    except ValueError as e:
        # 驗證錯誤（例如：user_id 為空）
        logger.warning("預覽重算驗證失敗，user_id=%s, error=%s", request.user_id, e)
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
        
    except Exception as e:
        # 其他錯誤（DB 連線失敗、計算錯誤等）
        logger.exception("預覽重算失敗，user_id=%s", request.user_id)
        raise HTTPException(
            status_code=500,
            detail=f"預覽重算失敗：{str(e)}"
        )


@app.get("/portfolio/positions", tags=["portfolio"], response_model=PositionsResponse)
def get_positions(
    user_id: str = Query(..., min_length=1, description="使用者 ID"),
    asof: Optional[str] = Query(None, description="查詢時點（ISO format，未來實作）"),
    limit: int = Query(500, ge=1, le=2000, description="返回筆數上限"),
    cursor: Optional[str] = Query(None, description="分頁游標（未來實作）"),
    db: Session = Depends(get_db)
) -> PositionsResponse:
    """查詢使用者持倉快照（帳務層只讀 API）。
    
    架構鐵律：
    - 只回傳帳務欄位（symbol, asset_ccy, quantity, avg_cost, realized_pnl, cost_basis）
    - 不做匯率折算（不呼叫 app/fx 模組）
    
    回應欄位：
    - symbol: 股票代碼
    - asset_ccy: 資產幣別（原始交易幣別）
    - quantity: 持倉數量
    - avg_cost: 均價（會計成本）
    - realized_pnl: 已實現損益
    - cost_basis: 成本基礎（quantity * avg_cost）
    
    Args:
        user_id: 使用者 ID（必填）
        asof: 查詢時點（未來實作時間旅行查詢）
        limit: 返回筆數上限（預設 500，最大 2000）
        cursor: 分頁游標（未來實作）
        db: 資料庫 session
        
    Returns:
        PositionsResponse: 持倉快照列表（帳務數據，不含估值）
        
    Example:
        GET /portfolio/positions?user_id=tony&limit=10
        
                {
                    "user_id": "tony",
                    "asof": null,
                    "items": [
                        {
                            "symbol": "AAPL",
                            "asset_ccy": "USD",
                            "quantity": "100.00",
                            "avg_cost": "150.50",
                            "realized_pnl": "0.00",
                            "cost_basis": "15050.00"
                        }
                    ],
                    "next_cursor": null
                }
    """
    items, next_cursor = list_positions_for_user(
        db=db,
        user_id=user_id,
        asof=asof,
        limit=limit,
        cursor=cursor
    )

    return PositionsResponse(
        user_id=user_id,
        asof=asof,
        items=items,
        next_cursor=next_cursor
    )
