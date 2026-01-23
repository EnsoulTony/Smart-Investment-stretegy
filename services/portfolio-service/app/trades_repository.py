"""交易記錄資料庫存取層（Trades Repository）。

本模組負責從 trades 表查詢交易記錄，提供給持倉重算服務使用。

職責：
- 查詢指定用戶的所有交易記錄
- 確保交易記錄按時間順序排序（均價法計算的前提）
- 提供穩定的排序（同日多筆交易需二級排序）

設計原則：
- 單一職責：只負責 trades 表的查詢
- 純資料層：不包含業務邏輯
- 回傳 ORM 模型（由呼叫方轉換為 Pydantic 模型）
"""

import logging
from sqlalchemy.orm import Session
from typing import List

from app.models import Trade

logger = logging.getLogger(__name__)


def list_trades_for_user(db: Session, user_id: str) -> List[Trade]:
    """查詢指定用戶的所有交易記錄（按時間排序）。
    
    排序規則：
    1. 主要排序：trade_date ASC（交易日期由舊到新）
    2. 次要排序：created_at ASC（同日多筆時，按匯入順序）
    
    為什麼需要二級排序？
    - 同一天可能有多筆交易（例如：當日沖銷、多次買賣）
    - 若只按 trade_date 排序，同日交易順序不穩定（資料庫回傳順序可能變動）
    - 使用 created_at 作為 tie-breaker，確保排序穩定且符合匯入順序
    - 這對均價法計算很重要：先買後賣 vs 先賣後買會影響已實現損益
    
    注意事項：
    - 回傳的是 ORM Trade 物件，呼叫方需轉換為 TradeRecord（Pydantic）
    - 不過濾 symbol 或 asset_ccy（由呼叫方分組）
    - 不做任何業務邏輯處理（例如：驗證 side、計算均價）
    
    Args:
        db: SQLAlchemy Session
        user_id: 使用者 ID
    
    Returns:
        List[Trade]: 交易記錄列表（已排序）
        若用戶無交易記錄，回傳空列表
    
    Example:
        >>> from app.db import get_db_session
        >>> with get_db_session() as session:
        ...     trades = list_trades_for_user(session, "tony")
        ...     print(f"找到 {len(trades)} 筆交易")
        ...     for trade in trades:
        ...         print(f"{trade.trade_date}: {trade.side} {trade.quantity} {trade.symbol}")
    """
    logger.info("查詢用戶交易記錄，user_id=%s", user_id)
    
    trades = db.query(Trade).filter(
        Trade.user_id == user_id
    ).order_by(
        Trade.trade_date.asc(),   # 主要排序：交易日期
        Trade.created_at.asc()     # 次要排序：匯入順序（穩定性）
    ).all()
    
    logger.info("查詢完成，user_id=%s, trades_count=%d", user_id, len(trades))
    
    return trades
