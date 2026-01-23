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
        """測試混入無效資料：驗證可觀測性欄位的語意正確性（Contract Test）。
        
        測試場景：
        - fixture 包含 3 筆資料：2 筆有效 + 1 筆無效（quantity=0）
        
        Contract 驗證：
        1. status = "partial_succeeded"（有資料被拒絕，但有部分成功）
        2. inserted_count = 2（有效資料成功插入）
        3. errors_count = 1（無效資料算在 errors，不是 skipped）
        4. skipped_count = errors_count（當前實作：無效資料也算在 skipped）
        5. normalized_invalid_count = 1（可觀測性：格式錯誤筆數）
        
        關鍵語意：
        - errors_count：驗證失敗的筆數（格式錯誤、欄位不合法等）
        - skipped_count：未寫入 DB 的總筆數（= errors + duplicates）
        - duplicates_count：重複資料（source_hash 衝突）
        
        確保 invalid 資料不會被誤判為 duplicate。
        """
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
        
        # Contract 1: HTTP 層成功，但業務層部分失敗
        assert response.status_code == 200, "API 呼叫應成功"
        data = response.json()
        
        # Contract 2: status 明確表示部分成功（不是 succeeded，也不是 failed）
        assert data["status"] == "partial_succeeded", \
            f"有 errors 時應回傳 partial_succeeded，實際：{data['status']}"
        
        # Contract 3: 有效資料成功插入（符合 fixture 的 2 筆有效資料）
        assert data["inserted_count"] == 2, \
            f"fixture 有 2 筆有效資料，應全部插入，實際：{data['inserted_count']}"
        
        # Contract 4: 無效資料被正確識別（errors_count > 0）
        assert data["errors_count"] == 1, \
            f"fixture 有 1 筆無效資料（quantity=0），實際：{data['errors_count']}"
        assert data["errors_count"] > 0, "應有驗證錯誤"
        
        # Contract 5: skipped_count 語意正確（= errors + duplicates）
        # 當前場景：1 筆 error，0 筆 duplicate
        assert data["skipped_count"] == data["errors_count"], \
            "skipped_count 應等於 errors_count（無 duplicate 情境）"
        
        # Contract 6: 可觀測性欄位提供除錯資訊
        # normalized_invalid_count 應與 errors_count 一致（格式錯誤筆數）
        if "normalized_invalid_count" in data:
            assert data["normalized_invalid_count"] == 1, \
                f"應有 1 筆格式錯誤，實際：{data['normalized_invalid_count']}"
        
        # Contract 7: 總量平衡（sheet_rows = valid + invalid）
        if "sheet_rows_count" in data and "normalized_valid_count" in data:
            assert data["sheet_rows_count"] == 3, "fixture 總共 3 筆資料"
            assert data["normalized_valid_count"] == 2, "2 筆有效"
            assert data["normalized_invalid_count"] == 1, "1 筆無效"
            assert data["sheet_rows_count"] == \
                   data["normalized_valid_count"] + data["normalized_invalid_count"], \
                   "總量應平衡：sheet_rows = valid + invalid"
    
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
