"""測試 source_hash 版本控制與可觀測性欄位。"""

import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.trade_normalizer import TradeNormalizer, CANONICAL_VERSION
from app.schemas import TradeRecord


class TestSourceHashVersioning:
    """測試 source_hash 版本控制。"""
    
    def test_hash_includes_version_prefix(self):
        """測試 hash 包含版本前綴。"""
        trade = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("150.50"),
            fee=Decimal("1.5"),
            trade_date=datetime(2026, 1, 23, 10, 30, 0),
            broker="IB"
        )
        
        hash1 = TradeNormalizer.compute_source_hash(trade)
        hash2 = TradeNormalizer.compute_source_hash(trade)
        
        # 同一筆交易的 hash 應該一致
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 產生 64 字元十六進位
    
    def test_hash_changes_with_version(self, monkeypatch):
        """測試版本變更時 hash 會不同。"""
        trade = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("150.50"),
            fee=Decimal("1.5"),
            trade_date=datetime(2026, 1, 23, 10, 30, 0),
            broker="IB"
        )
        
        # 使用 v1 計算 hash
        hash_v1 = TradeNormalizer.compute_source_hash(trade)
        
        # 暫時修改版本為 v2
        import app.trade_normalizer as normalizer_module
        monkeypatch.setattr(normalizer_module, "CANONICAL_VERSION", "v2")
        
        # 使用 v2 計算 hash
        hash_v2 = TradeNormalizer.compute_source_hash(trade)
        
        # 兩個版本的 hash 應該不同
        assert hash_v1 != hash_v2
    
    def test_hash_identical_for_same_trade_data(self):
        """測試相同交易資料產生相同 hash。"""
        trade1 = TradeRecord(
            user_id="tony",
            symbol="QQQ",
            asset_ccy="USD",
            side="SELL",
            quantity=Decimal("50.5"),
            price=Decimal("388.75"),
            fee=Decimal("2.0"),
            trade_date=datetime(2026, 1, 20, 14, 0, 0),
            broker="Firstrade"
        )
        
        trade2 = TradeRecord(
            user_id="tony",
            symbol="QQQ",
            asset_ccy="USD",
            side="SELL",
            quantity=Decimal("50.5"),
            price=Decimal("388.75"),
            fee=Decimal("2.0"),
            trade_date=datetime(2026, 1, 20, 14, 0, 0),
            broker="Firstrade"
        )
        
        hash1 = TradeNormalizer.compute_source_hash(trade1)
        hash2 = TradeNormalizer.compute_source_hash(trade2)
        
        assert hash1 == hash2
    
    def test_hash_different_for_different_trade_data(self):
        """測試不同交易資料產生不同 hash。"""
        trade1 = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("150.50"),
            fee=Decimal("1.5"),
            trade_date=datetime(2026, 1, 23, 10, 30, 0),
            broker="IB"
        )
        
        # 只改變 quantity
        trade2 = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("200"),  # 不同
            price=Decimal("150.50"),
            fee=Decimal("1.5"),
            trade_date=datetime(2026, 1, 23, 10, 30, 0),
            broker="IB"
        )
        
        hash1 = TradeNormalizer.compute_source_hash(trade1)
        hash2 = TradeNormalizer.compute_source_hash(trade2)
        
        assert hash1 != hash2
    
    def test_canonical_version_constant_exists(self):
        """測試 CANONICAL_VERSION 常數存在且為 v1。"""
        assert CANONICAL_VERSION == "v1"
