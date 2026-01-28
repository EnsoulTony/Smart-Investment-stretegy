"""測試交易資料標準化器（trade_normalizer）。

測試內容：
1. 欄位 mapping 正確轉換
2. 交易方向（side）轉換（買/賣 → BUY/SELL）
3. 日期解析（支援多種格式）
4. source_hash 計算穩定性（相同資料必產生相同 hash）
5. 錯誤處理（缺少欄位、資料格式錯誤）
"""

import pytest
import os
from datetime import datetime, timezone
from decimal import Decimal

from app.trade_normalizer import TradeNormalizer
from app.schemas import TradeRecord

os.environ.setdefault("SYMBOL_NAME_PROVIDER", "disabled")


class TestTradeNormalizer:
    """測試 TradeNormalizer 類別。"""
    
    def test_normalize_row_success(self):
        """測試標準化單列資料成功。"""
        normalizer = TradeNormalizer()
        
        row_dict = {
            "user_id": "tony",
            "symbol": "AAPL",
            "asset_ccy": "USD",
            "side": "BUY",
            "quantity": "100",
            "price": "180.50",
            "fee": "1.50",
            "trade_date": "2026-01-20",
            "broker": "IB"
        }
        
        trade, error = normalizer.normalize_row(row_dict)
        
        assert error is None
        assert trade is not None
        assert trade.user_id == "tony"
        assert trade.symbol == "AAPL"
        assert trade.side == "BUY"
        assert float(trade.quantity) == 100.0
        assert float(trade.price) == 180.50
        assert float(trade.fee) == 1.50
    
    def test_normalize_row_chinese_side(self):
        """測試交易方向轉換：買/賣 → BUY/SELL。"""
        normalizer = TradeNormalizer()
        
        # 測試「買」
        row_buy = {
            "user_id": "tony",
            "symbol": "QQQ",
            "asset_ccy": "USD",
            "side": "買",
            "quantity": "50",
            "price": "395.00",
            "fee": "0",
            "trade_date": "2026-01-21",
            "broker": "Firstrade"
        }
        
        trade_buy, error_buy = normalizer.normalize_row(row_buy)
        assert error_buy is None
        assert trade_buy.side == "BUY"
        
        # 測試「賣」
        row_sell = row_buy.copy()
        row_sell["side"] = "賣"
        
        trade_sell, error_sell = normalizer.normalize_row(row_sell)
        assert error_sell is None
        assert trade_sell.side == "SELL"
    
    def test_normalize_row_date_formats(self):
        """測試多種日期格式解析。"""
        normalizer = TradeNormalizer()
        
        base_row = {
            "user_id": "tony",
            "symbol": "TSLA",
            "asset_ccy": "USD",
            "side": "BUY",
            "quantity": "10",
            "price": "250.00",
            "fee": "0.5",
            "broker": "IB"
        }
        
        # 測試不同日期格式
        date_formats = [
            ("2026-01-20", datetime(2026, 1, 20)),
            ("2026-01-20 09:30:00", datetime(2026, 1, 20, 9, 30, 0)),
            ("2026-01-20 09:30", datetime(2026, 1, 20, 9, 30, 0)),
            ("2026/01/20", datetime(2026, 1, 20)),
        ]
        
        for date_str, expected_dt in date_formats:
            row = base_row.copy()
            row["trade_date"] = date_str
            
            trade, error = normalizer.normalize_row(row)
            assert error is None, f"日期格式 {date_str} 解析失敗：{error}"
            assert trade.trade_date == expected_dt
    
    def test_normalize_row_missing_field(self):
        """測試缺少必要欄位時回傳錯誤。"""
        normalizer = TradeNormalizer()
        
        # 缺少 symbol 欄位
        row_dict = {
            "user_id": "tony",
            "asset_ccy": "USD",
            "side": "BUY",
            "quantity": "100",
            "price": "180.50",
            "fee": "1.50",
            "trade_date": "2026-01-20",
            "broker": "IB"
        }
        
        trade, error = normalizer.normalize_row(row_dict)
        
        assert trade is None
        assert error is not None
        assert "symbol" in error.lower()
    
    def test_normalize_row_invalid_quantity(self):
        """測試數量必須 > 0。"""
        normalizer = TradeNormalizer()
        
        row_dict = {
            "user_id": "tony",
            "symbol": "AAPL",
            "asset_ccy": "USD",
            "side": "BUY",
            "quantity": "0",  # 不合法
            "price": "180.50",
            "fee": "1.50",
            "trade_date": "2026-01-20",
            "broker": "IB"
        }
        
        trade, error = normalizer.normalize_row(row_dict)
        
        assert trade is None
        assert error is not None
    
    def test_normalize_rows_batch(self):
        """測試批次標準化。"""
        normalizer = TradeNormalizer()
        
        rows_dicts = [
            {
                "user_id": "tony",
                "symbol": "AAPL",
                "asset_ccy": "USD",
                "side": "BUY",
                "quantity": "100",
                "price": "180.50",
                "fee": "1.50",
                "trade_date": "2026-01-20",
                "broker": "IB"
            },
            {
                "user_id": "tony",
                "symbol": "QQQ",
                "asset_ccy": "USD",
                "side": "賣",  # 中文
                "quantity": "50",
                "price": "395.00",
                "fee": "0",
                "trade_date": "2026-01-21",
                "broker": "Firstrade"
            },
            {
                "user_id": "tony",
                "symbol": "TSLA",
                "asset_ccy": "USD",
                "side": "BUY",
                "quantity": "0",  # 不合法
                "price": "250.00",
                "fee": "0.5",
                "trade_date": "2026-01-22",
                "broker": "IB"
            }
        ]
        
        success, failed = normalizer.normalize_rows(rows_dicts)
        
        assert len(success) == 2  # 前兩列成功
        assert len(failed) == 1   # 第三列失敗
        
        assert success[0].symbol == "AAPL"
        assert success[1].symbol == "QQQ"
        assert success[1].side == "SELL"  # 中文已轉換
        
        assert failed[0]["row_index"] == 3
        assert "quantity" in failed[0]["error"].lower()
    
    def test_compute_source_hash_stability(self):
        """測試 source_hash 計算穩定性：相同資料必產生相同 hash。"""
        trade1 = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("180.50"),
            fee=Decimal("1.50"),
            trade_date=datetime(2026, 1, 20, 9, 30, 0),
            broker="IB"
        )
        
        trade2 = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100.0"),  # 不同表示法，但值相同
            price=Decimal("180.50"),
            fee=Decimal("1.50"),
            trade_date=datetime(2026, 1, 20, 9, 30, 0),
            broker="IB"
        )
        
        hash1 = TradeNormalizer.compute_source_hash(trade1)
        hash2 = TradeNormalizer.compute_source_hash(trade2)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 產生 64 字元的十六進位字串
    
    def test_compute_source_hash_different_data(self):
        """測試不同資料產生不同 hash。"""
        trade1 = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("180.50"),
            fee=Decimal("1.50"),
            trade_date=datetime(2026, 1, 20, 9, 30, 0),
            broker="IB"
        )
        
        trade2 = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("180.51"),  # 價格不同
            fee=Decimal("1.50"),
            trade_date=datetime(2026, 1, 20, 9, 30, 0),
            broker="IB"
        )
        
        hash1 = TradeNormalizer.compute_source_hash(trade1)
        hash2 = TradeNormalizer.compute_source_hash(trade2)
        
        assert hash1 != hash2
    
    def test_custom_column_mapping(self, monkeypatch):
        """測試自訂欄位 mapping。"""
        # 模擬環境變數：Google Sheets 的欄位名稱不同
        monkeypatch.setenv("SHEET_COL_SYMBOL", "股票代碼")
        monkeypatch.setenv("SHEET_COL_SIDE", "買賣")
        monkeypatch.setenv("SHEET_COL_QUANTITY", "數量")
        
        normalizer = TradeNormalizer()
        
        # 使用中文欄位名稱
        row_dict = {
            "user_id": "tony",
            "股票代碼": "AAPL",  # 對應 symbol
            "asset_ccy": "USD",
            "買賣": "買",         # 對應 side
            "數量": "100",        # 對應 quantity
            "price": "180.50",
            "fee": "1.50",
            "trade_date": "2026-01-20",
            "broker": "IB"
        }
        
        trade, error = normalizer.normalize_row(row_dict)
        
        assert error is None
        assert trade.symbol == "AAPL"
        assert trade.side == "BUY"
        assert float(trade.quantity) == 100.0
    
    def test_get_canonical_string(self):
        """測試取得 canonical 字串（用於除錯）。"""
        trade = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("180.50"),
            fee=Decimal("1.50"),
            trade_date=datetime(2026, 1, 20, 9, 30, 0),
            broker="IB"
        )
        
        canonical = TradeNormalizer.get_canonical_string(trade)
        
        # 驗證格式
        assert canonical.startswith("tony|AAPL|USD|BUY|100|180.5|1.5|2026-01-20 09:30:00|IB")
        
        # 驗證欄位數量（9 個欄位，8 個分隔符）
        assert canonical.count("|") == 8
    
    def test_compute_source_hash_timezone_consistency(self):
        """測試 hash 計算對 timezone-aware 和 naive datetime 的一致性。
        
        地雷 2 驗證：確保不同時區的相同時刻產生相同 hash。
        """
        from datetime import timezone, timedelta
        
        # 建立三個不同表示但代表相同時刻的 datetime：
        # 1. Naive datetime（無時區）
        trade_naive = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("180.50"),
            fee=Decimal("1.50"),
            trade_date=datetime(2026, 1, 20, 9, 30, 0),  # Naive
            broker="IB"
        )
        
        # 2. UTC timezone-aware datetime（相同時刻）
        trade_utc = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("180.50"),
            fee=Decimal("1.50"),
            trade_date=datetime(2026, 1, 20, 9, 30, 0, tzinfo=timezone.utc),
            broker="IB"
        )
        
        # 3. 其他時區但轉換後是相同時刻（例如：UTC+8 的 17:30 = UTC 09:30）
        tz_plus8 = timezone(timedelta(hours=8))
        trade_tz8 = TradeRecord(
            user_id="tony",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("180.50"),
            fee=Decimal("1.50"),
            trade_date=datetime(2026, 1, 20, 17, 30, 0, tzinfo=tz_plus8),  # UTC+8 17:30
            broker="IB"
        )
        
        hash_naive = TradeNormalizer.compute_source_hash(trade_naive)
        hash_utc = TradeNormalizer.compute_source_hash(trade_utc)
        hash_tz8 = TradeNormalizer.compute_source_hash(trade_tz8)
        
        # 關鍵驗證：
        # - naive 與 UTC 的 hash 應該相同（都當作 naive 處理）
        # - UTC+8 17:30 轉為 UTC 後是 09:30，應該與其他兩個相同
        assert hash_naive == hash_utc, "Naive 和 UTC datetime 應產生相同 hash"
        assert hash_utc == hash_tz8, "不同時區但相同 UTC 時刻應產生相同 hash"
