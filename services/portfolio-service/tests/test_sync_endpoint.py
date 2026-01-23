"""測試 POST /portfolio/sync 端點。

測試內容：
1. 第一次同步：正常插入資料
2. 第二次同步（相同資料）：全部被跳過（source_hash 去重）
3. 混入非法資料：errors_count > 0 但整體 succeeded
4. Google Sheets 連線失敗：回傳 500

測試策略：
- 使用 monkeypatch 模擬 SheetsClient（不連真實 Google Sheets）
- 使用 docker-compose 的 postgres（真實 DB 測試）
- 每個測試使用 transaction rollback 確保隔離
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock

from app.main import app
from app.sync_service import SyncService
from app.sheets_client import SheetsClient
from app.db import get_db


@pytest.fixture
def client(db_session):
    """建立 FastAPI 測試客戶端（使用測試 db_session）。
    
    覆蓋 get_db 依賴，讓 API 端點使用測試的 db_session。
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # 不關閉 session，由 db_session fixture 管理
    
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_sheets_data_valid():
    """假資料：3 筆有效的交易記錄。"""
    return [
        {
            "user_id": "test_user",
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
            "user_id": "test_user",
            "symbol": "QQQ",
            "asset_ccy": "USD",
            "side": "買",  # 中文測試
            "quantity": "50",
            "price": "395.00",
            "fee": "0",
            "trade_date": "2026-01-21 09:30:00",
            "broker": "Firstrade"
        },
        {
            "user_id": "test_user",
            "symbol": "TSLA",
            "asset_ccy": "USD",
            "side": "SELL",
            "quantity": "25",
            "price": "250.00",
            "fee": "0.5",
            "trade_date": "2026-01-22",
            "broker": "IB"
        }
    ]


@pytest.fixture
def mock_sheets_data_with_invalid():
    """假資料：2 筆有效 + 1 筆無效（quantity=0）。"""
    return [
        {
            "user_id": "test_user",
            "symbol": "AAPL",
            "asset_ccy": "USD",
            "side": "BUY",
            "quantity": "100",
            "price": "180.50",
            "fee": "1.50",
            "trade_date": "2026-01-23",
            "broker": "IB"
        },
        {
            "user_id": "test_user",
            "symbol": "INVALID",
            "asset_ccy": "USD",
            "side": "BUY",
            "quantity": "0",  # 無效：quantity 必須 > 0
            "price": "100.00",
            "fee": "0",
            "trade_date": "2026-01-23",
            "broker": "IB"
        },
        {
            "user_id": "test_user",
            "symbol": "MSFT",
            "asset_ccy": "USD",
            "side": "SELL",
            "quantity": "50",
            "price": "420.00",
            "fee": "1.0",
            "trade_date": "2026-01-23",
            "broker": "Firstrade"
        }
    ]


class TestSyncEndpoint:
    """測試 POST /portfolio/sync 端點。"""
    
    def test_first_sync_inserts_all_records(
        self, 
        client, 
        mock_sheets_data_valid, 
        monkeypatch, 
        db_session
    ):
        """測試第一次同步：所有記錄都被插入。"""
        # 創建 Mock 類別（替代 SheetsClient）
        # 重要：不能繼承 SheetsClient，因為 __init__ 會檢查環境變數
        captured_data = mock_sheets_data_valid
        
        class MockSheetsClient:
            def __init__(self):
                # 不呼叫 super().__init__()，避免環境變數檢查
                pass
            
            def fetch_trades_dicts(self):
                return captured_data
        
        # 使用 monkeypatch 替換 SheetsClient 類別
        monkeypatch.setattr("app.sync_service.SheetsClient", MockSheetsClient)
        
        # 呼叫 API
        response = client.post("/portfolio/sync")
        
        # 驗證回應
        assert response.status_code == 200
        data = response.json()
        
        # 調試輸出
        print(f"\n=== 調試信息 ===")
        print(f"Response data: {data}")
        print(f"Status: {data['status']}")
        print(f"Inserted: {data['inserted_count']}")
        print(f"Skipped: {data['skipped_count']}")
        print(f"Errors: {data['errors_count']}")
        
        assert data["status"] == "succeeded"
        assert data["inserted_count"] == 3  # 3 筆全部插入
        assert data["skipped_count"] == 0
        assert data["errors_count"] == 0
        assert "run_id" in data
    
    def test_second_sync_skips_duplicates(
        self, 
        client, 
        mock_sheets_data_valid, 
        monkeypatch,
        db_session
    ):
        """測試第二次同步（相同資料）：全部因 source_hash 重複而跳過。"""
        # 創建 Mock 類別（替代 SheetsClient）
        captured_data = mock_sheets_data_valid
        
        class MockSheetsClient:
            def __init__(self):
                pass
            
            def fetch_trades_dicts(self):
                return captured_data
        
        # 使用 monkeypatch 替換 SheetsClient 類別
        monkeypatch.setattr("app.sync_service.SheetsClient", MockSheetsClient)
        
        # 第一次同步
        response1 = client.post("/portfolio/sync")
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["inserted_count"] == 3
        
        # 第二次同步（相同資料）
        response2 = client.post("/portfolio/sync")
        assert response2.status_code == 200
        data2 = response2.json()
        
        # 驗證：全部被跳過
        assert data2["inserted_count"] == 0
        assert data2["skipped_count"] == 3  # 3 筆全部跳過（source_hash 重複）
        assert data2["errors_count"] == 0
        assert data2["status"] == "succeeded"
    
    def test_sync_with_invalid_data(
        self, 
        client, 
        mock_sheets_data_with_invalid, 
        monkeypatch,
        db_session
    ):
        """測試混入無效資料：errors_count > 0 但整體仍 succeeded。"""
        # 創建 Mock 類別（替代 SheetsClient）
        captured_data = mock_sheets_data_with_invalid
        
        class MockSheetsClient:
            def __init__(self):
                pass
            
            def fetch_trades_dicts(self):
                return captured_data
        
        # 使用 monkeypatch 替換 SheetsClient 類別
        monkeypatch.setattr("app.sync_service.SheetsClient", MockSheetsClient)
        
        # 呼叫 API
        response = client.post("/portfolio/sync")
        
        # 驗證回應
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "succeeded"  # 整體成功（部分資料有效）
        assert data["inserted_count"] == 2   # 2 筆有效資料插入
        assert data["errors_count"] == 1      # 1 筆驗證失敗
        assert data["skipped_count"] == 1     # 1 筆被跳過（errors_count）
    
    def test_sync_google_sheets_connection_failure(
        self, 
        client, 
        monkeypatch,
        db_session
    ):
        """測試 Google Sheets 連線失敗：回傳 500。"""
        # 創建會拋出例外的 Mock 類別
        class MockSheetsClient:
            def __init__(self):
                pass
            def fetch_trades_dicts(self):
                raise Exception("Google Sheets API 連線失敗")
        
        # 使用 monkeypatch 替換 SheetsClient 類別
        monkeypatch.setattr("app.sync_service.SheetsClient", MockSheetsClient)
        
        # 呼叫 API
        response = client.post("/portfolio/sync")
        
        # 驗證回應：應該回傳 500
        assert response.status_code == 500
        data = response.json()
        assert "同步失敗" in data["detail"]
    
    def test_sync_creates_sync_run_record(
        self, 
        client, 
        mock_sheets_data_valid, 
        monkeypatch,
        db_session
    ):
        """測試同步會建立 sync_run 記錄。"""
        from app.models import SyncRun
        
        # 創建 Mock 類別（替代 SheetsClient）
        captured_data = mock_sheets_data_valid
        
        class MockSheetsClient:
            def __init__(self):
                pass
            
            def fetch_trades_dicts(self):
                return captured_data
        
        # 使用 monkeypatch 替換 SheetsClient 類別
        monkeypatch.setattr("app.sync_service.SheetsClient", MockSheetsClient)
        
        # 記錄同步前的 sync_run 數量
        initial_count = db_session.query(SyncRun).count()
        
        # 呼叫 API
        response = client.post("/portfolio/sync")
        assert response.status_code == 200
        
        # 驗證 sync_run 記錄已建立
        final_count = db_session.query(SyncRun).count()
        assert final_count == initial_count + 1
        
        # 取得最新的 sync_run（修正：使用 started_at 而不是 created_at）
        sync_run = db_session.query(SyncRun).order_by(SyncRun.started_at.desc()).first()
        assert sync_run.status == "succeeded"
        assert sync_run.inserted_count == 3
        assert sync_run.finished_at is not None
