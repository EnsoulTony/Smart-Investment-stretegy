"""持倉重算模組（Position Rebuilder）。

本模組負責從 trades 表重新計算每個用戶的當前持倉狀態。

架構分層：
- Router (main.py) ➜ 接收 HTTP 請求，處理身份驗證
- Service (本模組) ➜ 協調業務流程，處理錯誤
- Calculator (avg_cost_calculator.py) ➜ 純函數，實作均價法計算邏輯
- Repository (trades_repository.py) ➜ 資料庫 CRUD 操作

當前階段（Sprint 1-4.2）：
- ✅ 建立骨架結構（Sprint 1-4.0）
- ✅ 均價法計算邏輯（Sprint 1-4.1）
- ✅ DB 查詢與預覽重算（Sprint 1-4.2）
- ⏸ positions_snapshot 表寫入（Sprint 1-4.3）
- ⏸ 外幣折算（未來）
"""

import logging
from sqlalchemy.orm import Session
from typing import Dict, List
from decimal import Decimal
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas import TradeRecord
from app.avg_cost_calculator import compute_avg_cost
from app.trades_repository import list_trades_for_user

logger = logging.getLogger(__name__)


class PositionRebuilder:
    """持倉重算服務類別。
    
    職責：
    1. 讀取指定用戶的所有交易記錄（按日期排序）
    2. 呼叫均價法計算器（下階段實作）
    3. 寫入 positions_snapshot 表（下階段實作）
    4. 回傳重算結果與警告訊息
    
    Attributes:
        session: SQLAlchemy Session，用於資料庫操作
    """
    
    def __init__(self, session: Session):
        """初始化 PositionRebuilder。
        
        Args:
            session: SQLAlchemy Session 物件
        """
        self.session = session
    
    def rebuild_positions(self, user_id: str) -> Dict:
        """重算指定用戶的持倉狀態並寫入 positions 表。
        
        Sprint 1-4.3 實作：
        1. 從 trades 表讀取該用戶所有交易，按 trade_date 排序
        2. 按 (symbol, asset_ccy) 分組
        3. 每組內使用均價法計算器計算：
           - quantity: 持倉數量
           - avg_cost: 平均成本
           - realized_pnl: 已實現損益
        4. 寫入 positions 表（使用 merge 實現冪等性）
        5. u_pnl 固定填 0（不做估值）
        6. 不做 FX 匯率折算（帳務層硬禁止）
        
        Args:
            user_id: 使用者 ID（例如："tony"）
            
        Returns:
            dict: 重算結果摘要（含可證偽證據）
                
        Raises:
            ValueError: 當 user_id 為空時
            Exception: 資料庫操作失敗時
        
        Notes:
            - 使用 session.merge() 實現冪等性（重複執行結果一致）
            - 不呼叫 FX 模組（帳務層規範）
            - u_pnl 填 0（不做估值）
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不可為空")
        
        logger.info("開始重算持倉並寫入 positions 表，user_id=%s", user_id)
        
        try:
            trades_orm = list_trades_for_user(self.session, user_id)
            grouped_trades = defaultdict(list)

            for trade_orm in trades_orm:
                # 將 ORM 轉為 Pydantic TradeRecord
                # 注意：DB 中賣出交易的 quantity 可能是負數，需轉為正數
                quantity = abs(trade_orm.quantity)  # 確保 quantity 總是正數
                
                trade_record = TradeRecord(
                    user_id=trade_orm.user_id,
                    symbol=trade_orm.symbol,
                    asset_ccy=trade_orm.asset_ccy,
                    side=trade_orm.side,
                    quantity=quantity,  # 使用轉換後的正數
                    price=trade_orm.price,
                    fee=trade_orm.fee,
                    trade_date=trade_orm.trade_date,
                    broker=trade_orm.broker
                )
                grouped_trades[(trade_record.symbol, trade_record.asset_ccy)].append(trade_record)

            from app.models import Position

            upserted_count = 0
            deleted_or_zeroed_count = 0

            for (symbol, asset_ccy), trades in grouped_trades.items():
                state = compute_avg_cost(trades)
                if state.qty == 0:
                    deleted_or_zeroed_count += 1
                    self.session.query(Position).filter(
                        Position.user_id == user_id,
                        Position.symbol == symbol
                    ).delete(synchronize_session=False)
                    continue

                position = Position(
                    user_id=user_id,
                    symbol=symbol,
                    asset_ccy=asset_ccy,
                    quantity=state.qty,
                    avg_cost=state.avg_cost,
                    realized_pnl=state.realized_pnl,
                    u_pnl=Decimal("0"),
                    last_updated_at=datetime.now(timezone.utc)
                )

                self.session.merge(position)
                upserted_count += 1

            self.session.commit()

            run_id = str(uuid4())
            evidence = {
                "positions_columns": list(Position.__table__.columns.keys())
            }

            result = {
                "status": "succeeded",
                "user_id": user_id,
                "symbols_count": len(grouped_trades),
                "upserted_count": upserted_count,
                "deleted_or_zeroed_count": deleted_or_zeroed_count,
                "run_id": run_id,
                "evidence": evidence,
            }

            logger.info("持倉重算完成，user_id=%s, result=%s", user_id, result)
            return result

        except Exception as e:
            logger.exception("持倉重算失敗，user_id=%s, error=%s", user_id, str(e))
            self.session.rollback()
            return {
                "status": "failed",
                "user_id": user_id,
                "symbols_count": 0,
                "upserted_count": 0,
                "deleted_or_zeroed_count": 0,
                "run_id": str(uuid4()),
                "evidence": {
                    "positions_columns": []
                }
            }


def rebuild_positions(user_id: str, db: Session) -> Dict:
    """持倉重算的函式介面（Functional Interface）。
    
    提供簡化的函式呼叫方式，內部委派給 PositionRebuilder 類別。
    適合在測試或腳本中使用。
    
    Args:
        user_id: 使用者 ID
        db: SQLAlchemy Session
        
    Returns:
        dict: 重算結果（與 PositionRebuilder.rebuild_positions 相同）
        
    Example:
        >>> from app.db import get_db_session
        >>> with get_db_session() as session:
        ...     result = rebuild_positions("tony", session)
        ...     print(result["rebuilt_symbols_count"])
    """
    rebuilder = PositionRebuilder(session=db)
    return rebuilder.rebuild_positions(user_id=user_id)


def preview_rebuild(user_id: str, db: Session) -> Dict:
    """預覽持倉重算結果（不寫入 DB）。
    
    功能：
    1. 從 trades 表查詢用戶的所有交易記錄
    2. 按 (symbol, asset_ccy) 分組
    3. 每組內按 trade_date 排序後呼叫均價法計算器
    4. 回傳計算結果的預覽資料（JSON 格式）
    
    與 rebuild_positions 的差異：
    - preview_rebuild: 只計算不寫入，回傳詳細資料供檢視
    - rebuild_positions: 計算後寫入 positions 表（Sprint 1-4.3 實作）
    
    使用場景：
    - 用戶想查看重算結果但不實際執行
    - 開發/測試時驗證計算邏輯
    - 提供 API 端點供前端顯示預覽
    
    Args:
        user_id: 使用者 ID
        db: SQLAlchemy Session
    
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
            - warnings: 警告訊息列表
    
    Raises:
        ValueError: user_id 為空時
        Exception: 資料庫查詢或計算失敗時
    
    Example:
        >>> result = preview_rebuild("tony", db)
        >>> print(f"共 {len(result['symbols'])} 個持倉")
        >>> for pos in result['symbols']:
        ...     print(f"{pos['symbol']}: {pos['qty']} 股 @ {pos['avg_cost']}")
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id 不可為空")
    
    logger.info("開始預覽持倉重算，user_id=%s", user_id)
    
    try:
        # 步驟 1: 從 DB 查詢交易記錄
        trades_orm = list_trades_for_user(db, user_id)
        logger.info("查詢到 %d 筆交易記錄，user_id=%s", len(trades_orm), user_id)
        
        # 步驟 2: 轉換為 TradeRecord（Pydantic 模型）
        # ORM Trade -> Pydantic TradeRecord（欄位映射）
        trades_pydantic: List[TradeRecord] = []
        for trade_orm in trades_orm:
            try:
                trade_record = TradeRecord(
                    user_id=trade_orm.user_id,
                    symbol=trade_orm.symbol,
                    asset_ccy=trade_orm.asset_ccy,
                    side=trade_orm.side,
                    quantity=trade_orm.quantity,
                    price=trade_orm.price,
                    fee=trade_orm.fee,
                    trade_date=trade_orm.trade_date,
                    broker=trade_orm.broker
                )
                trades_pydantic.append(trade_record)
            except Exception as e:
                # 個別交易轉換失敗，記錄警告但繼續處理
                logger.warning(
                    "交易記錄轉換失敗，trade_id=%s, error=%s",
                    trade_orm.id, e
                )
        
        logger.info("成功轉換 %d 筆交易記錄為 TradeRecord", len(trades_pydantic))
        
        # 步驟 3: 按 (symbol, asset_ccy) 分組
        # 使用 defaultdict 自動建立空列表
        grouped_trades = defaultdict(list)
        for trade in trades_pydantic:
            key = (trade.symbol, trade.asset_ccy)
            grouped_trades[key].append(trade)
        
        logger.info("交易記錄分組完成，共 %d 個標的", len(grouped_trades))
        
        # 步驟 4: 每組計算均價法
        symbols_result = []
        warnings = []
        
        for (symbol, asset_ccy), group_trades in grouped_trades.items():
            try:
                # 每組已在 repository 層排序（trade_date, created_at）
                # 直接呼叫均價法計算器
                state = compute_avg_cost(group_trades)
                
                symbols_result.append({
                    "symbol": symbol,
                    "asset_ccy": asset_ccy,
                    "qty": float(state.qty),  # Decimal -> float（JSON 序列化）
                    "avg_cost": float(state.avg_cost),
                    "realized_pnl": float(state.realized_pnl),
                    "total_fee": float(state.total_fee),
                    "trades_count": len(group_trades)
                })
                
                logger.debug(
                    "計算完成：symbol=%s, asset_ccy=%s, qty=%s, avg_cost=%s",
                    symbol, asset_ccy, state.qty, state.avg_cost
                )
                
            except ValueError as e:
                # 均價法計算失敗（例如：賣出超過持倉）
                warning_msg = f"標的 {symbol} ({asset_ccy}) 計算失敗：{str(e)}"
                warnings.append(warning_msg)
                logger.warning(warning_msg)
            
            except Exception as e:
                # 其他未預期的錯誤
                warning_msg = f"標的 {symbol} ({asset_ccy}) 發生未預期錯誤：{str(e)}"
                warnings.append(warning_msg)
                logger.exception(warning_msg)
        
        # 步驟 5: 組裝回傳結果
        result = {
            "status": "succeeded",
            "user_id": user_id,
            "symbols": symbols_result,
            "warnings": warnings
        }
        
        logger.info(
            "預覽重算完成，user_id=%s, symbols_count=%d, warnings_count=%d",
            user_id, len(symbols_result), len(warnings)
        )
        
        return result
        
    except Exception as e:
        logger.exception("預覽重算失敗，user_id=%s", user_id)
        raise

