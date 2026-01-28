"""Trades Repository - 交易流水帳資料存取層。

負責 trades 表的所有 SQL 操作，包含批次插入與去重邏輯。
"""

from typing import List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timezone

from app.models import Trade
from app.schemas import TradeRecord
from app.trade_normalizer import TradeNormalizer


class TradesRepository:
    """交易流水帳 Repository。
    
    提供 trades 表的資料存取方法，封裝 SQL 操作。
    """
    
    def __init__(self, session: Session):
        """初始化 Repository。
        
        Args:
            session: SQLAlchemy session
        """
        self.session = session
    
    def bulk_insert_trades(
        self, 
        trade_records: List[TradeRecord]
    ) -> Tuple[int, int]:
        """批次插入交易記錄（使用 source_hash 去重）。
        
        使用 PostgreSQL 的 INSERT ... ON CONFLICT DO NOTHING 避免重複插入。
        
        Args:
            trade_records: 已驗證的 TradeRecord 列表
        
        Returns:
            Tuple[int, int]: (inserted_count, skipped_count)
                - inserted_count: 實際插入的筆數
                - skipped_count: 因 source_hash 重複而跳過的筆數
        
        Notes:
            - 使用 ON CONFLICT (source_hash) DO NOTHING 實現去重
            - 不會覆蓋已存在的交易記錄
            - 所有操作在同一個 transaction 中執行
        """
        if not trade_records:
            return 0, 0
        
        # 準備批次插入資料並收集所有 source_hash
        trades_data = []
        all_hashes = []
        for trade_record in trade_records:
            # 計算 source_hash
            source_hash = TradeNormalizer.compute_source_hash(trade_record)
            all_hashes.append(source_hash)
            
            # 確保 trade_date 有時區資訊（符合 DB schema）
            trade_date = trade_record.trade_date
            if trade_date.tzinfo is None:
                # Naive datetime: 假設為 UTC
                trade_date = trade_date.replace(tzinfo=timezone.utc)
            
            trades_data.append({
                "user_id": trade_record.user_id,
                "symbol": trade_record.symbol,
                "asset_ccy": trade_record.asset_ccy,
                "side": trade_record.side,
                "quantity": trade_record.quantity,
                "price": trade_record.price,
                "fee": trade_record.fee,
                "trade_date": trade_date,
                "broker": trade_record.broker,
                "name_zh": trade_record.name_zh,
                "source_hash": source_hash,
            })
        
        # 查詢已存在的 source_hash（插入前）
        existing_hashes = set(
            row[0] for row in self.session.query(Trade.source_hash)
            .filter(Trade.source_hash.in_(all_hashes))
            .all()
        )
        
        # 使用 PostgreSQL 的 INSERT ... ON CONFLICT DO NOTHING
        stmt = insert(Trade).values(trades_data)
        stmt = stmt.on_conflict_do_nothing(index_elements=["source_hash"])
        
        # 執行插入
        self.session.execute(stmt)
        self.session.commit()
        
        # 計算實際插入與跳過的筆數（基於查詢結果，不依賴 rowcount）
        skipped_count = len(existing_hashes)
        inserted_count = len(trade_records) - skipped_count
        
        return inserted_count, skipped_count
    
    def get_trades_by_user(
        self, 
        user_id: str, 
        limit: int = 100
    ) -> List[Trade]:
        """取得指定使用者的交易記錄。
        
        Args:
            user_id: 使用者 ID
            limit: 最多回傳筆數
        
        Returns:
            List[Trade]: 交易記錄列表（依 trade_date 降冪排序）
        """
        return (
            self.session.query(Trade)
            .filter(Trade.user_id == user_id)
            .order_by(Trade.trade_date.desc())
            .limit(limit)
            .all()
        )
    
    def count_trades(self) -> int:
        """計算交易記錄總數。
        
        Returns:
            int: 交易記錄總筆數
        """
        return self.session.query(Trade).count()
