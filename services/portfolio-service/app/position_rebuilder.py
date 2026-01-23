"""持倉重算模組（Position Rebuilder）。

本模組負責從 trades 表重新計算每個用戶的當前持倉狀態。

架構分層：
- Router (main.py) ➜ 接收 HTTP 請求，處理身份驗證
- Service (本模組) ➜ 協調業務流程，處理錯誤
- Calculator (未來 Sprint 1-4.1) ➜ 純函數，實作均價法計算邏輯
- Repository (repositories/) ➜ 資料庫 CRUD 操作

當前階段（Sprint 1-4.0）：
- ✅ 建立骨架結構
- ⏸ 均價法計算邏輯（下階段）
- ⏸ 外幣折算（下階段）
- ⏸ positions_snapshot 表寫入（下階段）
"""

import logging
from sqlalchemy.orm import Session
from typing import Dict, List

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
        """重算指定用戶的持倉狀態。
        
        流程（完整版，當前階段僅實作骨架）：
        1. 驗證 user_id（目前略過）
        2. 從 trades 表讀取該用戶所有交易，按 trade_date 排序
        3. 按 symbol 分組，依序計算每筆交易後的持倉狀態
        4. 呼叫均價法計算器（下階段實作）：
           - 計算持倉數量（quantity）
           - 計算平均成本（avg_cost）
           - 計算已實現損益（realized_pnl）
        5. 呼叫外幣折算邏輯（下階段實作）：
           - 將不同幣別（USD、TWD、HKD）的持倉折算為基準幣別
           - 使用即時或快取的匯率
        6. 寫入 positions_snapshot 表（下階段實作）
        7. 回傳結果摘要
        
        Args:
            user_id: 使用者 ID（例如："tony"）
            
        Returns:
            dict: 重算結果
                - status: 執行狀態（"succeeded" 或 "failed"）
                - rebuilt_symbols_count: 重算的標的數量（當前固定為 0）
                - warnings: 警告訊息列表（當前為空陣列）
                
        Raises:
            ValueError: 當 user_id 為空時
            Exception: 資料庫操作失敗時（下階段實作）
        
        Notes:
            - 當前階段（Sprint 1-4.0）僅回傳固定結構，不做實際計算
            - 下階段（Sprint 1-4.1）將引入均價法純函數
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不可為空")
        
        logger.info("開始重算持倉，user_id=%s", user_id)
        
        # TODO (Sprint 1-4.1): 實作以下邏輯
        # 1. 讀取交易記錄：
        #    trades = self.session.query(Trade).filter_by(user_id=user_id).order_by(Trade.trade_date).all()
        #
        # 2. 按 symbol 分組並計算：
        #    positions = {}
        #    for trade in trades:
        #        if trade.symbol not in positions:
        #            positions[trade.symbol] = Position(symbol=trade.symbol, quantity=0, avg_cost=0)
        #        # 呼叫均價法計算器
        #        positions[trade.symbol] = calculate_avg_cost(positions[trade.symbol], trade)
        #
        # 3. 寫入 positions_snapshot 表：
        #    for symbol, position in positions.items():
        #        self.session.merge(PositionSnapshot(...))
        #    self.session.commit()
        
        # 當前階段：回傳固定結構
        result = {
            "status": "succeeded",
            "rebuilt_symbols_count": 0,  # 下階段改為實際計算的標的數量
            "warnings": []  # 下階段可能包含：「標的 XYZ 匯率缺失，使用預設匯率」
        }
        
        logger.info("持倉重算完成，user_id=%s, result=%s", user_id, result)
        return result


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
