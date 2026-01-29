"""Portfolio Service 的 FastAPI 進入點。"""

import os
import logging
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from .schemas import (
    RebuildPositionsRequest,
    RebuildPositionsResponse,
    PositionsResponse,
    TradesSummaryResponse,
    SymbolMappingsResponse,
    SymbolMappingUpsertRequest,
    SymbolMappingResolveRequest,
    OutcomeUpsertRequest,
    OutcomeListResponse,
)

from app.db import get_db, engine
from app.sync_service import SyncService
from app.position_rebuilder import PositionRebuilder, compute_positions_hash
from app.schemas import RebuildPositionsRequest, RebuildPositionsResponse
from app.repositories.positions_repository import list_positions_for_user
from app.trades_repository import count_trades_for_user, count_distinct_symbols_for_user, list_trades_for_user
from app.models import Trade
from app.schemas import TradeRecord
from app.avg_cost_calculator import compute_avg_cost
from app.core_holdings_service import CoreHoldingsService
from app.repositories.symbol_name_mappings_repo import SymbolNameMappingsRepository
from app.symbol_name_resolver import SymbolNameResolver
from app.models_core import DecisionOutcome
from collections import defaultdict
from decimal import Decimal
from datetime import date, datetime, timezone
from .position_rebuilder import preview_rebuild

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


def get_core_holdings_service(db: Session = Depends(get_db)) -> CoreHoldingsService:
    return CoreHoldingsService(db)


def get_symbol_name_repo(db: Session = Depends(get_db)) -> SymbolNameMappingsRepository:
    return SymbolNameMappingsRepository(db)


def get_symbol_name_resolver(
    repo: SymbolNameMappingsRepository = Depends(get_symbol_name_repo),
) -> SymbolNameResolver:
    return SymbolNameResolver(repo)


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


@app.get("/portfolio/rebuild_positions/preview", tags=["portfolio"])
def preview_rebuild_positions(
    user_id: str = Query(..., description="使用者 ID"),
    require_trades: bool = Query(False, description="是否強制要求 trades 表有資料（預設 false 保持相容）"),
    db: Session = Depends(get_db)
) -> dict:
    """預覽持倉重算結果（不寫入 DB）。
    
    功能：
    - 從 trades 表查詢用戶的所有交易記錄
    - 按 (symbol, asset_ccy) 分組並計算均價法
    - 回傳計算結果的預覽資料（不寫入 positions 表）
    
    與 POST /portfolio/rebuild_positions 的差異：
    - preview: 只計算不寫入，回傳詳細資料供檢視
    - rebuild: 計算後寫入 positions 表
    
    使用場景：
    - 用戶想查看重算結果但不實際執行
    - 開發/測試時驗證計算邏輯
    - 前端顯示預覽畫面
    
    Args:
        user_id: 使用者 ID（Query 參數）
        require_trades: 是否強制要求 trades 表有資料（預設 false）
        db: SQLAlchemy Session（依賴注入）
    
    Returns:
        dict: 預覽結果
            - status: "preview" 或 "precondition_failed"
            - user_id: 使用者 ID
            - require_trades: 是否強制要求 trades
            - trades_count: 交易筆數
            - distinct_symbols_count: 不重複標的數量
            - computed_positions_count: 計算後的 positions 數量
            - computed_positions_hash: positions 的 SHA256 hash
            - positions: 持倉列表
              [{
                "symbol": 股票代碼,
                "asset_ccy": 幣別,
                "qty": 持倉數量,
                "avg_cost": 平均成本,
                "realized_pnl": 已實現損益,
                "total_fee": 累計手續費,
                "trades_count": 交易筆數
              }]
            - evidence: 可證偽證據
    
    Raises:
        HTTPException:
            - 409: require_trades=true 且 trades_count=0
            - 422: user_id 缺失或格式錯誤
            - 500: 預覽過程發生錯誤
    
    Notes:
        - Sprint 1-4.B: 實作 preview + rebuild idempotent
    """
    try:
        if not user_id or not user_id.strip():
            raise HTTPException(status_code=422, detail="user_id must not be empty")
        
        # 前置條件檢查：若 require_trades=true 且 trades_count=0，回傳 409
        trades_count = count_trades_for_user(db, user_id)
        distinct_symbols_count = count_distinct_symbols_for_user(db, user_id)
        
        if require_trades and trades_count == 0:
            evidence = {
                "require_trades": True,
                "decision": "blocked",
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
                    "require_trades": require_trades,
                    "trades_count": 0,
                    "computed_positions_count": 0,
                    "computed_positions_hash": "",
                    "evidence": evidence,
                    "message": "前置條件不滿足：該用戶在 trades 表無交易記錄，無法執行 rebuild_positions（require_trades=true）"
                }
            )
        
        result_data = preview_rebuild(user_id=user_id, db=db)

        # Create a new dictionary from the result to avoid modifying the original
        result = dict(result_data)

        # 補充 require_trades 和 trades 計數
        result["require_trades"] = require_trades
        result["trades_count"] = trades_count
        result["distinct_symbols_count"] = distinct_symbols_count

        # 補充 verification_sql
        if "evidence" not in result:
            result["evidence"] = {}
        result["evidence"]["require_trades"] = require_trades
        result["evidence"]["decision"] = "proceed"
        result["evidence"]["precondition_snapshot"] = {
            "trades_count": trades_count,
            "distinct_symbols_count": distinct_symbols_count
        }
        result["evidence"]["verification_sql"] = {
            "trades_count": f"select count(*) from trades where user_id='{user_id}';",
            "distinct_symbols": f"select count(distinct symbol) from trades where user_id='{user_id}';",
            "positions_count": "N/A (preview mode, no DB write)"
        }

        # symbols 欄位改為 positions，確保一致
        if "symbols" in result:
            result["positions"] = result.pop("symbols")

        # status 欄位強制為 preview
        result["status"] = "preview"

        # 移除舊欄位 computed_positions_hash，確保只回傳 positions_hash
        if "computed_positions_hash" in result:
            del result["computed_positions_hash"]
        if "computed_positions_count" in result:
            del result["computed_positions_count"]

        return result
        
    except HTTPException:
        raise
    except ValueError as e:
        # 驗證錯誤（例如：user_id 為空）
        logger.warning("預覽重算驗證失敗，user_id=%s, error=%s", user_id, e)
        raise HTTPException(
            status_code=422,
            detail=str(e)
        )
        
    except Exception as e:
        # 其他錯誤（DB 連線失敗、計算錯誤等）
        logger.exception("預覽重算失敗，user_id=%s", user_id)
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
    - 不做匯率折算（不呼叫匯率模組）
    
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


@app.post("/portfolio/core_holdings/rebuild", tags=["portfolio"])
def rebuild_core_holdings(
    user_id: str = Query(..., min_length=1, description="使用者 ID"),
):
    """已停用：trade is_core 欄位移除，請改用 /portfolio/core_holdings 設定。"""
    return {
        "status": "deprecated",
        "user_id": user_id,
        "rows_marked": 0,
        "rows_upserted": 0,
        "message": "trade is_core 欄位已移除，請使用 /portfolio/core_holdings 編輯核心持股",
    }


@app.get("/portfolio/core_holdings", tags=["portfolio"])
def list_core_holdings(
    user_id: str = Query(..., min_length=1, description="使用者 ID"),
    service: CoreHoldingsService = Depends(get_core_holdings_service),
):
    rows = service.list_core_holdings(user_id)
    items = [
        {
            "symbol": row.symbol,
            "name_zh": row.name_zh or "",
        }
        for row in rows
    ]
    symbols = [row.symbol for row in rows]
    return {
        "user_id": user_id,
        "items": items,
        "symbols": symbols,
        "count": len(symbols),
    }


class CoreHoldingItemRequest(BaseModel):
    symbol: str
    name_zh: Optional[str] = None


class CoreHoldingsSaveRequest(BaseModel):
    symbols: list[str] = []
    items: list[CoreHoldingItemRequest] = []


@app.post("/portfolio/core_holdings", tags=["portfolio"])
def save_core_holdings(
    payload: CoreHoldingsSaveRequest,
    user_id: str = Query(..., min_length=1, description="使用者 ID"),
    service: CoreHoldingsService = Depends(get_core_holdings_service),
):
    if payload.items:
        items = [(item.symbol, item.name_zh) for item in payload.items]
    else:
        items = [(symbol, None) for symbol in payload.symbols]
    saved = service.save_core_holdings(user_id, items)
    return {
        "status": "ok",
        "user_id": user_id,
        "count": saved,
    }


@app.get("/portfolio/symbol_mappings", tags=["portfolio"], response_model=SymbolMappingsResponse)
def list_symbol_mappings(
    q: Optional[str] = Query(None, description="symbol 查詢（模糊搜尋）"),
    limit: int = Query(200, ge=1, le=1000, description="回傳筆數上限"),
    repo: SymbolNameMappingsRepository = Depends(get_symbol_name_repo),
):
    rows = repo.list_mappings(query=q, limit=limit)
    items = [
        {
            "symbol": row.symbol,
            "market": row.market,
            "name_zh": row.name_zh,
            "source": row.source,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]
    return {"items": items}


@app.post("/portfolio/symbol_mappings", tags=["portfolio"])
def upsert_symbol_mapping(
    payload: SymbolMappingUpsertRequest,
    repo: SymbolNameMappingsRepository = Depends(get_symbol_name_repo),
):
    mapping = repo.upsert_mapping(
        symbol=payload.symbol.upper(),
        market=payload.market.upper(),
        name_zh=payload.name_zh,
        source=payload.source or "manual",
    )
    return {
        "symbol": mapping.symbol,
        "market": mapping.market,
        "name_zh": mapping.name_zh,
        "source": mapping.source,
        "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
    }


@app.post("/portfolio/symbol_mappings/resolve", tags=["portfolio"])
def resolve_symbol_mapping(
    payload: SymbolMappingResolveRequest,
    resolver: SymbolNameResolver = Depends(get_symbol_name_resolver),
    repo: SymbolNameMappingsRepository = Depends(get_symbol_name_repo),
):
    symbol = payload.symbol.upper()
    market = payload.market.upper() if payload.market else resolver.infer_market(symbol, payload.asset_ccy)
    name = resolver.resolve(symbol, payload.asset_ccy)
    if not name:
        return {
            "symbol": symbol,
            "market": market or "UNKNOWN",
            "name_zh": "",
            "source": "unresolved",
        }
    mapping = repo.get_mapping(symbol, market)
    return {
        "symbol": mapping.symbol if mapping else symbol,
        "market": mapping.market if mapping else (market or "UNKNOWN"),
        "name_zh": mapping.name_zh if mapping else name,
        "source": mapping.source if mapping else "resolved",
        "updated_at": mapping.updated_at.isoformat() if mapping and mapping.updated_at else None,
    }


@app.post("/portfolio/outcomes", tags=["portfolio"])
def upsert_decision_outcome(
    payload: OutcomeUpsertRequest,
    db: Session = Depends(get_db),
):
    outcome = (
        db.query(DecisionOutcome)
        .filter(
            DecisionOutcome.user_id == payload.user_id,
            DecisionOutcome.as_of == payload.as_of,
            DecisionOutcome.plugin == payload.plugin,
            DecisionOutcome.decision_inputs_hash == payload.decision_inputs_hash,
        )
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if outcome:
        outcome.outcome_label = payload.outcome_label
        outcome.outcome_note = payload.outcome_note
        outcome.updated_at = now
    else:
        outcome = DecisionOutcome(
            user_id=payload.user_id,
            as_of=payload.as_of,
            plugin=payload.plugin,
            decision_inputs_hash=payload.decision_inputs_hash,
            outcome_label=payload.outcome_label,
            outcome_note=payload.outcome_note,
            created_at=now,
            updated_at=now,
        )
        db.add(outcome)
    db.commit()
    db.refresh(outcome)
    return {
        "user_id": outcome.user_id,
        "as_of": outcome.as_of.isoformat(),
        "plugin": outcome.plugin,
        "decision_inputs_hash": outcome.decision_inputs_hash,
        "outcome_label": outcome.outcome_label,
        "outcome_note": outcome.outcome_note,
        "created_at": outcome.created_at.isoformat() if outcome.created_at else None,
        "updated_at": outcome.updated_at.isoformat() if outcome.updated_at else None,
    }


@app.get("/portfolio/outcomes", tags=["portfolio"], response_model=OutcomeListResponse)
def list_decision_outcomes(
    user_id: str = Query(..., min_length=1, description="使用者 ID"),
    from_date: str = Query(..., alias="from", description="起始日期 (YYYY-MM-DD)"),
    to_date: str = Query(..., alias="to", description="結束日期 (YYYY-MM-DD)"),
    plugin: Optional[str] = Query(None, description="策略版本"),
    limit: int = Query(200, ge=1, le=1000, description="回傳筆數上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: Session = Depends(get_db),
):
    try:
        from_dt = date.fromisoformat(from_date)
        to_dt = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid date format. Expected YYYY-MM-DD",
        )

    query = db.query(DecisionOutcome).filter(
        DecisionOutcome.user_id == user_id,
        DecisionOutcome.as_of >= from_dt,
        DecisionOutcome.as_of <= to_dt,
    )
    if plugin:
        query = query.filter(DecisionOutcome.plugin == plugin)

    rows = (
        query.order_by(DecisionOutcome.as_of.desc(), DecisionOutcome.updated_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    items = [
        {
            "user_id": row.user_id,
            "as_of": row.as_of.isoformat(),
            "plugin": row.plugin,
            "decision_inputs_hash": row.decision_inputs_hash,
            "outcome_label": row.outcome_label,
            "outcome_note": row.outcome_note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]
    return {"items": items}
