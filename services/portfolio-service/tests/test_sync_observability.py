"""測試同步回應的可觀測性欄位。"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime
from decimal import Decimal

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.sync_service import SyncService, SyncResult
from app.schemas import TradeRecord


class TestSyncObservability:
    """測試同步服務的可觀測性欄位。"""
    
    def test_sync_result_includes_observability_fields(self):
        """測試 SyncResult 包含所有可觀測性欄位。"""
        import uuid
        
        result = SyncResult(
            run_id=uuid.uuid4(),
            inserted_count=10,
            updated_count=0,
            skipped_count=5,
            errors_count=2,
            status="partial_succeeded",
            sheet_rows_count=20,
            normalized_valid_count=15,
            normalized_invalid_count=2,
            duplicates_count=3
        )
        
        result_dict = result.to_dict()
        
        # 驗證基本欄位
        assert result_dict["inserted_count"] == 10
        assert result_dict["skipped_count"] == 5
        assert result_dict["errors_count"] == 2
        assert result_dict["status"] == "partial_succeeded"
        
        # 驗證可觀測性欄位
        assert result_dict["sheet_rows_count"] == 20
        assert result_dict["normalized_valid_count"] == 15
        assert result_dict["normalized_invalid_count"] == 2
        assert result_dict["duplicates_count"] == 3
    
    @pytest.fixture
    def mock_session(self):
        """建立 mock SQLAlchemy session。"""
        session = MagicMock()
        session.commit = MagicMock()
        session.rollback = MagicMock()
        return session
    
    @pytest.fixture
    def mock_sheets_client(self):
        """建立 mock SheetsClient。"""
        client = MagicMock()
        
        # 模擬從 Google Sheets 讀取 15 列資料
        client.fetch_trades_dicts.return_value = [
            {
                "user_id": "tony",
                "symbol": "AAPL",
                "asset_ccy": "USD",
                "side": "BUY",
                "quantity": "100",
                "price": "150.50",
                "fee": "1.5",
                "trade_date": "2026-01-23 10:30:00",
                "broker": "IB"
            }
            for i in range(10)  # 10 筆有效資料
        ] + [
            {
                "user_id": "tony",
                "symbol": "QQQ",
                "asset_ccy": "USD",
                "side": "BUY",
                "quantity": "-100",  # 無效：數量為負
                "price": "388.50",
                "fee": "2.0",
                "trade_date": "2026-01-20",
                "broker": "Firstrade"
            }
            for i in range(3)  # 3 筆無效資料
        ] + [
            {
                "user_id": "tony",
                "symbol": "TSLA",
                "asset_ccy": "USD",
                "side": "SELL",
                "quantity": "50",
                "price": "250.00",
                "fee": "1.0",
                "trade_date": "2026-01-22",
                "broker": "IB"
            }
            for i in range(2)  # 2 筆有效資料
        ]
        
        return client
    
    def test_run_sync_returns_correct_observability_metrics(self, mock_session, mock_sheets_client):
        """測試 run_sync 回傳正確的可觀測性指標。"""
        # 建立 SyncService（注入 mock）
        service = SyncService(session=mock_session, sheets_client=mock_sheets_client)
        
        # Mock repositories
        with patch.object(service.sync_runs_repo, 'create_run') as mock_create, \
             patch.object(service.sync_runs_repo, 'finish_run') as mock_finish, \
             patch.object(service.trades_repo, 'bulk_insert_trades') as mock_bulk_insert:
            
            # 設定 mock 回傳值
            mock_run = MagicMock()
            mock_run.run_id = "test-run-id"
            mock_create.return_value = mock_run
            
            # 模擬插入 10 筆，2 筆重複
            mock_bulk_insert.return_value = (10, 2)
            
            # 執行同步
            result = service.run_sync()
            
            # 驗證可觀測性欄位
            assert result.sheet_rows_count == 15  # 從 Sheets 讀取 15 列
            assert result.normalized_valid_count == 12  # 10 + 2 筆有效
            assert result.normalized_invalid_count == 3  # 3 筆無效（quantity 為負）
            assert result.duplicates_count == 2  # 2 筆重複
            assert result.inserted_count == 10  # 實際插入 10 筆
            assert result.errors_count == 3  # 與 normalized_invalid_count 一致
    
    def test_sync_result_to_dict_format(self):
        """測試 SyncResult.to_dict() 的輸出格式。"""
        import uuid
        
        run_id = uuid.uuid4()
        result = SyncResult(
            run_id=run_id,
            inserted_count=8,
            updated_count=0,
            skipped_count=4,
            errors_count=1,
            status="partial_succeeded",
            sheet_rows_count=13,
            normalized_valid_count=12,
            normalized_invalid_count=1,
            duplicates_count=3
        )
        
        result_dict = result.to_dict()
        
        # 驗證所有必要欄位存在
        required_fields = [
            "run_id", "inserted_count", "updated_count", "skipped_count",
            "errors_count", "status", "sheet_rows_count", "normalized_valid_count",
            "normalized_invalid_count", "duplicates_count"
        ]
        
        for field in required_fields:
            assert field in result_dict, f"Missing field: {field}"
        
        # 驗證數學關係正確
        # skipped_count = duplicates_count + errors_count
        assert result_dict["skipped_count"] == result_dict["duplicates_count"] + result_dict["errors_count"]
