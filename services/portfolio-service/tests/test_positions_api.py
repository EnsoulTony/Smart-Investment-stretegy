"""測試 GET /portfolio/positions 端點（只讀帳務 API）。

驗證：
A) 正常回傳帳務資料（含 cost_basis）
B) 參數驗證（user_id 空字串 → 422）
C) 架構邊界（不呼叫 FX、不做估值）
"""

import pytest
from fastapi.testclient import TestClient
from decimal import Decimal
from app.main import app
from app.db import get_db, engine
from app.models import Base, Position

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """每個測試前重置 DB。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_get_positions_success():
    """A) 正常回傳：插入測試資料 → 檢查 items 長度與欄位。"""
    db = next(get_db())
    
    # 插入 2 筆測試持倉
    pos1 = Position(
        user_id="tony",
        symbol="TSLA",
        asset_ccy="USD",
        quantity=Decimal("100"),
        avg_cost=Decimal("250.00"),
        realized_pnl=Decimal("1500.00"),
        u_pnl=Decimal("0")
    )
    pos2 = Position(
        user_id="tony",
        symbol="NVDA",
        asset_ccy="USD",
        quantity=Decimal("50"),
        avg_cost=Decimal("500.00"),
        realized_pnl=Decimal("3000.00"),
        u_pnl=Decimal("0")
    )
    db.add_all([pos1, pos2])
    db.commit()
    db.close()
    
    # 呼叫 API
    response = client.get("/portfolio/positions?user_id=tony")
    
    # 驗證
    assert response.status_code == 200
    data = response.json()
    
    assert data["user_id"] == "tony"
    assert len(data["items"]) == 2
    assert data["next_cursor"] is None
    
    # 驗證持倉內容（不依賴順序）
    items_by_symbol = {item["symbol"]: item for item in data["items"]}
    assert set(items_by_symbol.keys()) == {"TSLA", "NVDA"}
    item1 = items_by_symbol["TSLA"]
    assert item1["asset_ccy"] == "USD"
    assert item1["quantity"] == "100"
    assert item1["avg_cost"] == "250.00"
    assert item1["realized_pnl"] == "1500.00"
    assert item1["cost_basis"] == "25000.00"  # 100 * 250
    
    # 確保沒有估值欄位
    assert "market_value" not in item1
    assert "unrealized_pnl" not in item1
    assert "fx_rate" not in item1
    assert "valuation_ccy" not in item1


def test_get_positions_empty_user_id():
    """B) 參數驗證：user_id 空字串 → 422。"""
    response = client.get("/portfolio/positions?user_id=")
    
    assert response.status_code == 422
    error = response.json()
    assert "detail" in error


def test_get_positions_no_data():
    """C) 空資料：查詢不存在的 user_id → 回傳空陣列。"""
    response = client.get("/portfolio/positions?user_id=nonexistent")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["user_id"] == "nonexistent"
    assert data["items"] == []
    assert data["next_cursor"] is None


def test_get_positions_limit():
    """D) limit 參數：插入 5 筆 → 限制只回傳 2 筆。"""
    db = next(get_db())
    
    # 插入 5 筆
    for i in range(5):
        pos = Position(
            user_id="tony",
            symbol=f"SYM{i}",
            asset_ccy="USD",
            quantity=Decimal("10"),
            avg_cost=Decimal("100"),
            realized_pnl=Decimal("0"),
            u_pnl=Decimal("0")
        )
        db.add(pos)
    
    db.commit()
    db.close()
    
    # 呼叫 API（limit=2）
    response = client.get("/portfolio/positions?user_id=tony&limit=2")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["items"]) == 2
    assert data["next_cursor"] is None
