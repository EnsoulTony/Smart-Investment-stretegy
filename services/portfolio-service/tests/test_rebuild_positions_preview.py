"""測試 POST /portfolio/rebuild_positions/preview 端點（預覽重算）。

測試範圍（Sprint 1-4.2）：
- ✅ 端點存在並可回應
- ✅ 從 DB 查詢 trades 並計算均價法
- ✅ 回應結構正確（symbols 包含必要欄位）
- ✅ 計算結果與 compute_avg_cost 一致
- ⏸ 實際寫入 positions 表（Sprint 1-4.3）

不依賴：
- ❌ Google Sheets
- ❌ 外部 API
- ✅ 使用 db_session fixture 插入測試資料
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from decimal import Decimal
from datetime import datetime

# 將服務根目錄加入 import 路徑
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app
from app.models import Trade
from app.db import get_db


@pytest.fixture
def client(db_session):
    """建立 FastAPI TestClient，並 override get_db dependency。
    
    關鍵：
    - TestClient 預設會使用 app.get_db() 建立新的 session
    - 測試插入的資料在 db_session fixture 中（使用 SAVEPOINT 機制）
    - 必須 override get_db，讓 API 使用「同一個 db_session」
    - 這樣才能在同一個 transaction 範圍內看到尚未 commit 的測試資料
    
    為什麼需要同一個 session？
    - conftest.py 的 db_session 使用 SAVEPOINT（nested transaction）
    - 測試中的 commit() 只提交到 SAVEPOINT，不是真正寫入 DB
    - 如果 API 用另一個 session，會因為 transaction 隔離看不到資料
    """
    def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestRebuildPositionsPreview:
    """測試預覽重算端點。"""
    
    def test_preview_endpoint_exists(self, client):
        """測試：端點存在且可回應。
        
        驗證：
        - HTTP status code = 200
        - 回應為 JSON 格式
        """
        response = client.post(
            "/portfolio/rebuild_positions/preview",
            json={"user_id": "test_user"}
        )
        
        assert response.status_code == 200, f"預期 200，實際：{response.status_code}"
        assert response.headers["content-type"] == "application/json"
    
    def test_preview_with_no_trades_returns_empty_symbols(self, client, db_session):
        """測試：用戶無交易記錄時，回傳空 symbols 列表。
        
        驗證：
        - status = "succeeded"
        - symbols = []（空列表）
        - warnings = []
        """
        response = client.post(
            "/portfolio/rebuild_positions/preview",
            json={"user_id": "user_with_no_trades"}
        )
        
        data = response.json()
        
        assert data["status"] == "succeeded"
        assert data["user_id"] == "user_with_no_trades"
        assert data["symbols"] == [], "無交易記錄時，symbols 應為空列表"
        assert data["warnings"] == []
    
    def test_preview_with_single_buy_calculates_correctly(self, client, db_session):
        """測試：單筆 BUY 交易的預覽計算。
        
        場景：
        - 買入 100 股 AAPL @ 150 元（手續費 1.5）
        
        驗證：
        - symbols 長度 = 1
        - qty = 100
        - avg_cost = (100*150 + 1.5) / 100 = 150.015
        - realized_pnl = 0（尚未賣出）
        - total_fee = 1.5
        - trades_count = 1
        """
        # 插入測試資料
        trade = Trade(
            user_id="test_user_1",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("150.00"),
            fee=Decimal("1.50"),
            trade_date=datetime(2026, 1, 1, 9, 30, 0),
            broker="IB",
            source_hash="test_hash_1"
        )
        db_session.add(trade)
        db_session.commit()
        
        # 自我驗證：確認資料真的插入成功（避免 rollback 太早）
        count = db_session.query(Trade).filter_by(user_id="test_user_1").count()
        assert count == 1, f"插入失敗或 rollback 太早，預期 1 筆 trade，實際：{count}"
        
        # 呼叫 API
        response = client.post(
            "/portfolio/rebuild_positions/preview",
            json={"user_id": "test_user_1"}
        )
        
        data = response.json()
        
        # 驗證基本結構
        assert data["status"] == "succeeded"
        assert data["user_id"] == "test_user_1"
        assert len(data["symbols"]) == 1, "應有 1 個標的"
        
        # 驗證計算結果
        pos = data["symbols"][0]
        assert pos["symbol"] == "AAPL"
        assert pos["asset_ccy"] == "USD"
        assert pos["qty"] == 100.0
        assert pos["avg_cost"] == 150.015, f"均價應為 150.015，實際：{pos['avg_cost']}"
        assert pos["realized_pnl"] == 0.0, "尚未賣出，realized_pnl 應為 0"
        assert pos["total_fee"] == 1.5
        assert pos["trades_count"] == 1
    
    def test_preview_with_buy_and_sell_calculates_pnl(self, client, db_session):
        """測試：BUY + SELL 交易的已實現損益計算。
        
        場景：
        - 買入 100 股 @ 150 元（手續費 1.5）
        - 賣出 40 股 @ 160 元（手續費 0.8）
        
        驗證：
        - qty = 60（剩餘持倉）
        - avg_cost = 150.015（不變）
        - realized_pnl = 40 * (160 - 150.015) - 0.8 = 398.6
        - total_fee = 2.3
        - trades_count = 2
        """
        # 插入測試資料
        trades = [
            Trade(
                user_id="test_user_2",
                symbol="AAPL",
                asset_ccy="USD",
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                fee=Decimal("1.50"),
                trade_date=datetime(2026, 1, 1, 9, 30, 0),
                broker="IB",
                source_hash="test_hash_2a"
            ),
            Trade(
                user_id="test_user_2",
                symbol="AAPL",
                asset_ccy="USD",
                side="SELL",
                quantity=Decimal("40"),
                price=Decimal("160.00"),
                fee=Decimal("0.80"),
                trade_date=datetime(2026, 1, 2, 10, 0, 0),
                broker="IB",
                source_hash="test_hash_2b"
            )
        ]
        db_session.add_all(trades)
        db_session.commit()
        
        # 自我驗證：確認資料真的插入成功
        count = db_session.query(Trade).filter_by(user_id="test_user_2").count()
        assert count == 2, f"插入失敗或 rollback 太早，預期 2 筆 trade，實際：{count}"
        
        # 呼叫 API
        response = client.post(
            "/portfolio/rebuild_positions/preview",
            json={"user_id": "test_user_2"}
        )
        
        data = response.json()
        
        assert len(data["symbols"]) == 1
        
        pos = data["symbols"][0]
        assert pos["symbol"] == "AAPL"
        assert pos["qty"] == 60.0, "剩餘持倉應為 60 股"
        assert pos["avg_cost"] == 150.015, "平均成本不應改變"
        assert pos["realized_pnl"] == 398.6, f"已實現損益應為 398.6，實際：{pos['realized_pnl']}"
        assert pos["total_fee"] == 2.3, "累計手續費應為 2.3"
        assert pos["trades_count"] == 2
    
    def test_preview_with_multiple_symbols_groups_correctly(self, client, db_session):
        """測試：多個標的的分組計算。
        
        場景：
        - AAPL: 買入 100 股 @ 150
        - MSFT: 買入 50 股 @ 300
        - QQQ: 買入 200 股 @ 380
        
        驗證：
        - symbols 長度 = 3
        - 每個標的獨立計算
        """
        trades = [
            Trade(
                user_id="test_user_3",
                symbol="AAPL",
                asset_ccy="USD",
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                fee=Decimal("1.50"),
                trade_date=datetime(2026, 1, 1),
                broker="IB",
                source_hash="test_hash_3a"
            ),
            Trade(
                user_id="test_user_3",
                symbol="MSFT",
                asset_ccy="USD",
                side="BUY",
                quantity=Decimal("50"),
                price=Decimal("300.00"),
                fee=Decimal("1.50"),
                broker="IB",
                trade_date=datetime(2026, 1, 2),
                source_hash="test_hash_3b"
            ),
            Trade(
                user_id="test_user_3",
                symbol="QQQ",
                asset_ccy="USD",
                side="BUY",
                quantity=Decimal("200"),
                price=Decimal("380.00"),
                fee=Decimal("3.00"),
                trade_date=datetime(2026, 1, 3),
                broker="IB",
                source_hash="test_hash_3c"
            )
        ]
        db_session.add_all(trades)
        db_session.commit()
        
        # 自我驗證：確認資料真的插入成功
        count = db_session.query(Trade).filter_by(user_id="test_user_3").count()
        assert count == 3, f"插入失敗或 rollback 太早，預期 3 筆 trade，實際：{count}"
        
        # 呼叫 API
        response = client.post(
            "/portfolio/rebuild_positions/preview",
            json={"user_id": "test_user_3"}
        )
        
        data = response.json()
        
        assert len(data["symbols"]) == 3, "應有 3 個標的"
        
        # 驗證所有標的都出現
        symbols = {pos["symbol"] for pos in data["symbols"]}
        assert symbols == {"AAPL", "MSFT", "QQQ"}
        
        # 驗證每個標的的計算
        for pos in data["symbols"]:
            assert pos["qty"] > 0, f"{pos['symbol']} 的持倉數量應 > 0"
            assert pos["avg_cost"] > 0, f"{pos['symbol']} 的均價應 > 0"
            assert pos["trades_count"] == 1, f"{pos['symbol']} 應有 1 筆交易"
    
    def test_preview_response_structure_complete(self, client, db_session):
        """測試：回應結構完整性（合約測試）。
        
        驗證所有必要欄位存在且型別正確。
        """
        # 插入測試資料
        trade = Trade(
            user_id="test_user_4",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("150.00"),
            fee=Decimal("1.50"),
            trade_date=datetime(2026, 1, 1),
            broker="IB",
            source_hash="test_hash_4"
        )
        db_session.add(trade)
        db_session.commit()
        
        # 呼叫 API
        response = client.post(
            "/portfolio/rebuild_positions/preview",
            json={"user_id": "test_user_4"}
        )
        
        data = response.json()
        
        # 驗證頂層欄位
        assert "status" in data
        assert "user_id" in data
        assert "symbols" in data
        assert "warnings" in data
        
        assert isinstance(data["status"], str)
        assert isinstance(data["user_id"], str)
        assert isinstance(data["symbols"], list)
        assert isinstance(data["warnings"], list)
        
        # 驗證 symbols 內的欄位
        if len(data["symbols"]) > 0:
            pos = data["symbols"][0]
            required_fields = [
                "symbol", "asset_ccy", "qty", "avg_cost",
                "realized_pnl", "total_fee", "trades_count"
            ]
            for field in required_fields:
                assert field in pos, f"symbols 應包含 {field} 欄位"
            
            assert isinstance(pos["symbol"], str)
            assert isinstance(pos["asset_ccy"], str)
            assert isinstance(pos["qty"], (int, float))
            assert isinstance(pos["avg_cost"], (int, float))
            assert isinstance(pos["realized_pnl"], (int, float))
            assert isinstance(pos["total_fee"], (int, float))
            assert isinstance(pos["trades_count"], int)
    
    def test_preview_missing_user_id_returns_422(self, client):
        """測試：缺少 user_id 時回傳 422。
        
        驗證 Pydantic validation contract。
        """
        response = client.post(
            "/portfolio/rebuild_positions/preview",
            json={}  # 缺少 user_id
        )
        
        assert response.status_code == 422
        error_detail = response.json()
        assert "detail" in error_detail
