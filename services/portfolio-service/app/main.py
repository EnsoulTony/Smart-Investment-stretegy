"""Portfolio Service 的 FastAPI 進入點。"""

import os
import logging
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from .schemas import RebuildPositionsRequest, RebuildPositionsResponse, PositionsResponse, TradesSummaryResponse

from app.db import get_db, engine
from app.sync_service import SyncService
from app.position_rebuilder import PositionRebuilder, preview_rebuild
from app.schemas import RebuildPositionsRequest, RebuildPositionsResponse
from app.repositories.positions_repository import list_positions_for_user
from app.trades_repository import count_trades_for_user, count_distinct_symbols_for_user
from app.models import Trade

SERVICE_NAME = os.getenv("SERVICE_NAME", "portfolio-service")

# 設定 logger
logger = logging.getLogger(__name__)


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    verify_db_schema()
    yield


app = FastAPI(title="Portfolio Service", version="0.1.0", lifespan=lifespan)


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


@app.get("/portfolio/trades/summary", tags=["portfolio"], response_model=TradesSummaryResponse)
def get_trades_summary(
    user_id: str = Query(..., description="使用者 ID"),
    db: Session = Depends(get_db)
) -> dict:
    """取得指定用戶的交易記錄摘要（輕量級探針端點）。
    
    用途：
    - 提供輕量級探針端點，讓其他服務或腳本先確認前置條件
    - automation 腳本在呼叫 rebuild_positions 前先確認是否有交易記錄
    - 診斷工具（確認 sync 是否成功）
    
    回傳：
    - trades_count: 交易記錄總筆數
    - symbols_count: 不重複標的數量
    - min_trade_date / max_trade_date: 交易日期範圍（可選）
    - evidence: 可證偽證據（包含 verification_sql）
    
    Args:
        user_id: 使用者 ID（Query 參數）
        db: SQLAlchemy Session（依賴注入）
    
    Returns:
        TradesSummaryResponse: 交易摘要
    
    Raises:
        HTTPException:
            - 422: user_id 缺失或格式錯誤
    """
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=422, detail="user_id must not be empty")
    
    trades_count = count_trades_for_user(db, user_id)
    symbols_count = count_distinct_symbols_for_user(db, user_id)
    
    # 查詢日期範圍（可選）
    min_date = None
    max_date = None
    if trades_count > 0:
        from sqlalchemy import func
        date_range = db.query(
            func.min(Trade.trade_date),
            func.max(Trade.trade_date)
        ).filter(Trade.user_id == user_id).first()
        
        if date_range and date_range[0] and date_range[1]:
            min_date = date_range[0].strftime("%Y-%m-%d")
            max_date = date_range[1].strftime("%Y-%m-%d")
    
    evidence = {
        "verification_sql": {
            "trades_count": f"select count(*) from trades where user_id='{user_id}';",
            "distinct_symbols": f"select count(distinct symbol) from trades where user_id='{user_id}';"
        }
    }
    
    return {
        "user_id": user_id,
        "trades_count": trades_count,
        "symbols_count": symbols_count,
        "min_trade_date": min_date,
        "max_trade_date": max_date,
        "evidence": evidence
    }


@app.post("/portfolio/rebuild_positions", tags=["portfolio"], response_model=RebuildPositionsResponse)
def rebuild_positions(
    request: dict | None = Body(None),
    user_id: Optional[str] = Query(None),
    require_trades: bool = Query(False, description="是否強制要求 trades 表有資料（預設 false 保持相容）"),
    db: Session = Depends(get_db)
) -> dict:
    """重算指定用戶的持倉狀態。
    
    從 trades 表重新計算當前持倉數量、平均成本與已實現損益。
    
    前置條件檢查（require_trades=true 時）：
    - 若該用戶在 trades 表的筆數為 0，回傳 409 Conflict
    - 這是「讓錯誤早炸」的設計，避免使用者誤判「rebuild 成功」
    
    流程：
    1. 檢查前置條件（若 require_trades=true）
    2. 讀取該用戶的所有交易記錄
    3. 按 symbol 分組並依序計算均價法
    4. 寫入 positions 表（UPSERT）
    
    Args:
        request: 包含 user_id 的請求 body（可選）
        user_id: 使用者 ID（Query 參數，優先於 body）
        require_trades: 是否強制要求 trades 表有資料（預設 false）
        db: SQLAlchemy Session（依賴注入）
    
    Returns:
        dict: 重算結果
            - status: 執行狀態（"succeeded" / "failed" / "precondition_failed"）
            - symbols_count: 重算的標的數量
            - evidence: 可證偽證據（包含 verification_sql）
    
    Raises:
        HTTPException:
            - 409: require_trades=true 且 trades_count=0（前置條件不滿足）
            - 422: user_id 缺失或格式錯誤
            - 500: 重算過程發生錯誤
    
    Notes:
        - require_trades 預設 false 保持既有行為相容
        - 前置條件失敗會回傳 409 Conflict + 可證偽 evidence
    """
    try:
        if user_id is None:
            if request is None or "user_id" not in request:
                raise HTTPException(status_code=422, detail="user_id is required")
            user_id = request.get("user_id")
        elif request is not None and request.get("user_id") not in (None, user_id):
            raise HTTPException(status_code=422, detail="user_id mismatch")

        if not user_id or not user_id.strip():
            raise HTTPException(status_code=422, detail="user_id must not be empty")

        # 前置條件檢查：若 require_trades=true 且 trades_count=0，回傳 409
        trades_count = count_trades_for_user(db, user_id)
        distinct_symbols_count = count_distinct_symbols_for_user(db, user_id)
        
        if require_trades and trades_count == 0:
            evidence = {
                "require_trades": True,
                "decision": "blocked_precondition",
                "trades_count": trades_count,
                "distinct_symbols_count": distinct_symbols_count,
                "verification_sql": {
                    "trades_count": f"select count(*) from trades where user_id='{user_id}';",
                    "distinct_symbols": f"select count(distinct symbol) from trades where user_id='{user_id}';"
                }
            }
            raise HTTPException(
                status_code=409,
                detail={
                    "status": "precondition_failed",
                    "user_id": user_id,
                    "symbols_count": 0,
                    "upserted_count": 0,
                    "deleted_or_zeroed_count": 0,
                    "run_id": "",
                    "evidence": evidence,
                    "message": "前置條件不滿足：該用戶在 trades 表無交易記錄，無法執行 rebuild_positions（require_trades=true）"
                }
            )

        rebuilder = PositionRebuilder(session=db)
        result = rebuilder.rebuild_positions(user_id=user_id)
        
        # 補充可證偽 evidence
        result["evidence"]["require_trades"] = require_trades
        result["evidence"]["decision"] = "proceed"
        result["evidence"]["trades_count"] = trades_count
        result["evidence"]["distinct_symbols_count"] = distinct_symbols_count
        result["evidence"]["verification_sql"] = {
            "trades_count": f"select count(*) from trades where user_id='{user_id}';",
            "distinct_symbols": f"select count(distinct symbol) from trades where user_id='{user_id}';",
            "positions_count": f"select count(*) from positions where user_id='{user_id}';"
        }
        
        return result
        
    except HTTPException:
        raise
    except ValueError as e:
        # 驗證錯誤（例如：user_id 為空）
        logger.warning("重算持倉驗證失敗，user_id=%s, error=%s", user_id, e)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        # 其他錯誤（DB 連線失敗、計算錯誤等）
        logger.exception("重算持倉失敗，user_id=%s", user_id)
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
