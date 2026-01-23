"""測試資料庫 schema 與 migration。

測試內容：
1. migration 能成功執行
2. 插入 trade 成功
3. source_hash 唯一性約束正常運作
"""

import pytest
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from datetime import datetime
import hashlib

from app.db import Base
from app.models import Trade, Position, SyncRun


# 測試用資料庫 URL（使用 docker-compose 的 postgres）
TEST_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://investment:investment@postgres:5432/investment_db")


@pytest.fixture(scope="module")
def db_engine():
    """建立測試用資料庫 engine。"""
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def db_session(db_engine):
    """建立測試用 session。"""
    # 執行 migration（確保 schema 已建立）
    Base.metadata.create_all(bind=db_engine)
    
    Session = sessionmaker(bind=db_engine)
    session = Session()
    
    yield session
    
    # 清理測試資料
    session.query(Trade).delete()
    session.query(Position).delete()
    session.query(SyncRun).delete()
    session.commit()
    session.close()


def test_migration_success(db_engine):
    """測試 migration 成功執行，資料表已建立。"""
    with db_engine.connect() as conn:
        # 檢查 trades 表存在
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'trades'"
        ))
        assert result.fetchone() is not None, "trades 表應該存在"
        
        # 檢查 positions 表存在
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'positions'"
        ))
        assert result.fetchone() is not None, "positions 表應該存在"
        
        # 檢查 sync_runs 表存在
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'sync_runs'"
        ))
        assert result.fetchone() is not None, "sync_runs 表應該存在"


def test_insert_trade_success(db_session):
    """測試插入一筆 trade 成功。"""
    # 建立測試資料
    source_hash = hashlib.sha256("test_trade_1".encode()).hexdigest()
    trade = Trade(
        user_id="test_user",
        symbol="QQQ",
        asset_ccy="USD",
        side="BUY",
        quantity=100,
        price=395.50,
        fee=1.5,
        trade_date=datetime(2026, 1, 15, 9, 30, 0),
        broker="IB",
        source_hash=source_hash
    )
    
    db_session.add(trade)
    db_session.commit()
    
    # 驗證資料已插入
    result = db_session.query(Trade).filter_by(source_hash=source_hash).first()
    assert result is not None
    assert result.user_id == "test_user"
    assert result.symbol == "QQQ"
    assert float(result.quantity) == 100.0
    assert float(result.price) == 395.50


def test_trade_source_hash_unique_constraint(db_session):
    """測試 source_hash 唯一性約束：插入相同 source_hash 會失敗。"""
    source_hash = hashlib.sha256("duplicate_test".encode()).hexdigest()
    
    # 第一筆成功
    trade1 = Trade(
        user_id="test_user",
        symbol="AAPL",
        asset_ccy="USD",
        side="BUY",
        quantity=50,
        price=180.00,
        fee=0.5,
        trade_date=datetime(2026, 1, 20, 10, 0, 0),
        broker="IB",
        source_hash=source_hash
    )
    db_session.add(trade1)
    db_session.commit()
    
    # 第二筆相同 source_hash 應該失敗
    trade2 = Trade(
        user_id="test_user",
        symbol="AAPL",
        asset_ccy="USD",
        side="SELL",
        quantity=25,
        price=182.00,
        fee=0.5,
        trade_date=datetime(2026, 1, 21, 14, 0, 0),
        broker="IB",
        source_hash=source_hash  # 相同的 hash
    )
    db_session.add(trade2)
    
    with pytest.raises(IntegrityError):
        db_session.commit()
    
    db_session.rollback()


def test_position_user_symbol_unique_constraint(db_session):
    """測試 positions 表的 (user_id, symbol) 唯一性約束。"""
    # 第一筆成功
    position1 = Position(
        user_id="test_user",
        symbol="QQQ",
        asset_ccy="USD",
        quantity=100,
        avg_cost=390.00,
        realized_pnl=0,
        unrealized_pnl=500
    )
    db_session.add(position1)
    db_session.commit()
    
    # 第二筆相同 (user_id, symbol) 應該失敗
    position2 = Position(
        user_id="test_user",
        symbol="QQQ",
        asset_ccy="USD",
        quantity=150,
        avg_cost=395.00,
        realized_pnl=0,
        unrealized_pnl=750
    )
    db_session.add(position2)
    
    with pytest.raises(IntegrityError):
        db_session.commit()
    
    db_session.rollback()


def test_sync_run_creation(db_session):
    """測試建立 sync_run 記錄。"""
    import uuid
    
    sync_run = SyncRun(
        run_id=uuid.uuid4(),
        status="succeeded",
        inserted_count=10,
        updated_count=2,
        skipped_count=3
    )
    
    db_session.add(sync_run)
    db_session.commit()
    
    # 驗證資料已插入
    result = db_session.query(SyncRun).filter_by(run_id=sync_run.run_id).first()
    assert result is not None
    assert result.status == "succeeded"
    assert result.inserted_count == 10
    assert result.updated_count == 2
    assert result.skipped_count == 3
