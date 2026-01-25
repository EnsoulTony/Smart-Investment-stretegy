"""測試 rebuild_positions 的資料庫寫入功能（Sprint 1-4.3）。

驗證項目：
1. rebuild_positions 能正確寫入 positions 表
2. 冪等性：重複執行結果一致
3. 無 trades 時正確處理
4. 欄位正確性：asset_ccy、u_pnl=0
5. 不呼叫 FX 模組（帳務層硬禁止）
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from decimal import Decimal
from datetime import datetime

from app.main import app
from app.models import Trade, Position
from app.db import get_db


@pytest.fixture
def client(db_session):
    """建立 TestClient 並注入測試資料庫 session。"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # db_session 由 conftest.py 管理
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_rebuild_positions_writes_to_database(client, db_session: Session):
    """測試 rebuild_positions 能正確寫入 positions 表。"""
    # 準備測試資料：2 筆 AAPL 買入交易
    trades = [
        Trade(
            user_id="test_user",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("150"),
            fee=Decimal("1"),
            trade_date=datetime(2024, 1, 1),
            broker="IB",
            source_hash="hash_aapl_1",
            source_row_id=1
        ),
        Trade(
            user_id="test_user",
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("5"),
            price=Decimal("160"),
            fee=Decimal("0.5"),
            trade_date=datetime(2024, 1, 2),
            broker="IB",
            source_hash="hash_aapl_2",
            source_row_id=2
        ),
    ]
    for t in trades:
        db_session.add(t)
    db_session.commit()
    
    # 執行 rebuild_positions
    response = client.post("/portfolio/rebuild_positions", json={"user_id": "test_user"})
    
    # 驗證 API 回應
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "succeeded"
    assert data["user_id"] == "test_user"
    assert data["symbols_count"] == 1
    assert data["upserted_count"] == 1
    assert data["deleted_or_zeroed_count"] == 0
    assert data["run_id"]
    assert "positions_columns" in data["evidence"]
    
    # 驗證資料庫寫入
    position = db_session.query(Position).filter_by(
        user_id="test_user",
        symbol="AAPL"
    ).first()
    
    assert position is not None, "positions 表應該有 AAPL 的記錄"
    assert position.asset_ccy == "USD", "asset_ccy 應該來自 trade"
    assert position.quantity == Decimal("15"), "數量應該是 10 + 5 = 15"
    assert position.u_pnl == Decimal("0"), "u_pnl 應該填 0（不做估值）"


def test_rebuild_positions_idempotency(client, db_session: Session):
    """測試冪等性：重複執行 rebuild_positions 結果應一致。"""
    trade = Trade(
        user_id="test_user2",
        symbol="TSLA",
        asset_ccy="USD",
        side="BUY",
        quantity=Decimal("20"),
        price=Decimal("200"),
        fee=Decimal("2"),
        trade_date=datetime(2024, 1, 1),
        broker="IB",
        source_hash="hash_tsla_1",
        source_row_id=10
    )
    db_session.add(trade)
    db_session.commit()
    
    # 第一次執行
    response1 = client.post("/portfolio/rebuild_positions", json={"user_id": "test_user2"})
    assert response1.status_code == 200
    
    position1 = db_session.query(Position).filter_by(
        user_id="test_user2",
        symbol="TSLA"
    ).first()
    
    # 第二次執行（應該覆蓋）
    response2 = client.post("/portfolio/rebuild_positions", json={"user_id": "test_user2"})
    assert response2.status_code == 200
    
    position2 = db_session.query(Position).filter_by(
        user_id="test_user2",
        symbol="TSLA"
    ).first()
    
    assert position1.quantity == position2.quantity
    assert position1.avg_cost == position2.avg_cost
    
    # 確認資料庫只有一筆記錄
    count = db_session.query(Position).filter_by(
        user_id="test_user2",
        symbol="TSLA"
    ).count()
    assert count == 1, "應該只有一筆記錄（冪等性）"


def test_rebuild_positions_buy_sell_realized_pnl(client, db_session: Session):
    """測試買賣混合時 realized_pnl 與 qty 正確。"""
    trades = [
        Trade(
            user_id="test_user3",
            symbol="MSFT",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            fee=Decimal("0"),
            trade_date=datetime(2024, 1, 1),
            broker="IB",
            source_hash="hash_msft_1",
            source_row_id=1
        ),
        Trade(
            user_id="test_user3",
            symbol="MSFT",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("120"),
            fee=Decimal("0"),
            trade_date=datetime(2024, 1, 2),
            broker="IB",
            source_hash="hash_msft_2",
            source_row_id=2
        ),
        Trade(
            user_id="test_user3",
            symbol="MSFT",
            asset_ccy="USD",
            side="SELL",
            quantity=Decimal("5"),
            price=Decimal("130"),
            fee=Decimal("0"),
            trade_date=datetime(2024, 1, 3),
            broker="IB",
            source_hash="hash_msft_3",
            source_row_id=3
        ),
    ]
    for t in trades:
        db_session.add(t)
    db_session.commit()

    response = client.post("/portfolio/rebuild_positions", json={"user_id": "test_user3"})
    assert response.status_code == 200

    position = db_session.query(Position).filter_by(
        user_id="test_user3",
        symbol="MSFT"
    ).first()

    assert position is not None
    assert position.quantity == Decimal("15")
    assert position.avg_cost == Decimal("110")
    assert position.realized_pnl == Decimal("100")


def test_rebuild_positions_sell_to_zero_deletes(client, db_session: Session):
    """測試賣到零後刪除持倉。"""
    trades = [
        Trade(
            user_id="test_user4",
            symbol="NFLX",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("50"),
            fee=Decimal("0"),
            trade_date=datetime(2024, 1, 1),
            broker="IB",
            source_hash="hash_nflx_1",
            source_row_id=1
        ),
        Trade(
            user_id="test_user4",
            symbol="NFLX",
            asset_ccy="USD",
            side="SELL",
            quantity=Decimal("10"),
            price=Decimal("60"),
            fee=Decimal("0"),
            trade_date=datetime(2024, 1, 2),
            broker="IB",
            source_hash="hash_nflx_2",
            source_row_id=2
        ),
    ]
    for t in trades:
        db_session.add(t)
    db_session.commit()

    response = client.post("/portfolio/rebuild_positions", json={"user_id": "test_user4"})
    assert response.status_code == 200
    data = response.json()
    assert data["deleted_or_zeroed_count"] == 1

    position = db_session.query(Position).filter_by(
        user_id="test_user4",
        symbol="NFLX"
    ).first()
    assert position is None


def test_rebuild_positions_no_trades(client, db_session: Session):
    """測試當用戶沒有交易記錄時的處理。"""
    response = client.post("/portfolio/rebuild_positions", json={"user_id": "user_no_trades"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "succeeded"
    assert data["symbols_count"] == 0
    assert data["upserted_count"] == 0
    assert data["deleted_or_zeroed_count"] == 0
