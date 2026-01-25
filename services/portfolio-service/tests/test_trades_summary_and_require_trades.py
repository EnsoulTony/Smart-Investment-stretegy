"""測試 trades/summary 端點與 rebuild_positions 的 require_trades 參數。

測試範圍（Sprint: Prevent empty rebuild）：
- ✅ GET /portfolio/trades/summary 回傳正確統計
- ✅ rebuild_positions 的 require_trades=true 能正確擋住空 trades
- ✅ require_trades=false（預設）保持既有行為
- ✅ Evidence 包含可證偽的 verification_sql

設計原則（遵循 Sprint 1-4.2 加固經驗）：
- 使用 dependency_overrides 確保端點與測試共用同一個 db_session
- 避免 session 隔離問題（端點 commit 後測試看不到）
- 每個測試獨立 setup/teardown（避免互相影響）
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from decimal import Decimal
from datetime import datetime

# 將服務根目錄加入 import 路徑
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app
from app.db import get_db
from app.models import Trade, Position


# 全域變數：儲存測試用的 session（供 dependency_overrides 使用）
_test_session = None


def override_get_db():
    """覆寫 get_db 依賴注入，確保端點與測試共用同一個 session。"""
    global _test_session
    try:
        yield _test_session
    finally:
        pass  # 不在這裡 close，由 fixture 統一管理


@pytest.fixture
def db_session():
    """建立測試用的 database session（每個測試獨立）。
    
    特性：
    - 使用 dependency_overrides 讓端點與測試共用此 session
    - 測試結束後 rollback（避免污染資料庫）
    - 每個測試獨立執行（隔離性）
    """
    global _test_session
    
    # 建立新的 session
    from app.db import SessionLocal
    session = SessionLocal()
    _test_session = session
    
    # 覆寫 FastAPI 的 get_db 依賴注入
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        yield session
    finally:
        # 測試結束後 rollback（不污染資料庫）
        session.rollback()
        session.close()
        
        # 清除 override
        app.dependency_overrides.clear()
        _test_session = None


@pytest.fixture
def client():
    """建立 FastAPI TestClient。"""
    return TestClient(app)


def test_trades_summary_empty_returns_zero(client, db_session: Session):
    """測試：trades/summary 在無交易記錄時回傳 0。
    
    驗證：
    - trades_count = 0
    - symbols_count = 0
    - min_trade_date / max_trade_date = null
    - evidence 包含 verification_sql
    """
    # 確保該用戶無交易記錄
    db_session.query(Trade).filter(Trade.user_id == "test_empty_user").delete()
    db_session.commit()
    
    response = client.get("/portfolio/trades/summary?user_id=test_empty_user")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["user_id"] == "test_empty_user"
    assert data["trades_count"] == 0
    assert data["symbols_count"] == 0
    assert data["min_trade_date"] is None
    assert data["max_trade_date"] is None
    
    # 驗證 evidence
    assert "evidence" in data
    assert "verification_sql" in data["evidence"]
    assert "trades_count" in data["evidence"]["verification_sql"]
    assert "distinct_symbols" in data["evidence"]["verification_sql"]


def test_trades_summary_after_insert_returns_counts(client, db_session: Session):
    """測試：trades/summary 在插入交易後回傳正確統計。
    
    驗證：
    - trades_count = 插入筆數
    - symbols_count = 不重複標的數
    - min_trade_date / max_trade_date 正確
    - evidence 可證偽
    """
    user_id = "test_summary_user"
    
    # 清理舊資料
    db_session.query(Trade).filter(Trade.user_id == user_id).delete()
    db_session.commit()
    
    # 插入測試資料（3 筆交易，2 個標的）
    # 使用唯一的 source_hash 避免重複
    import uuid
    trades = [
        Trade(
            user_id=user_id,
            symbol="AAPL",
            asset_ccy="USD",
            quantity=Decimal("10"),
            price=Decimal("150.0"),
            fee=Decimal("0"),
            trade_date=datetime(2024, 1, 1),
            side="buy",
            broker="test",
            source_hash=f"hash_summary_{uuid.uuid4().hex[:8]}_1",
            created_at=datetime.now()
        ),
        Trade(
            user_id=user_id,
            symbol="AAPL",
            asset_ccy="USD",
            quantity=Decimal("5"),
            price=Decimal("160.0"),
            fee=Decimal("0"),
            trade_date=datetime(2024, 1, 15),
            side="buy",
            broker="test",
            source_hash=f"hash_summary_{uuid.uuid4().hex[:8]}_2",
            created_at=datetime.now()
        ),
        Trade(
            user_id=user_id,
            symbol="TSLA",
            asset_ccy="USD",
            quantity=Decimal("20"),
            price=Decimal("200.0"),
            fee=Decimal("0"),
            trade_date=datetime(2024, 2, 1),
            side="buy",
            broker="test",
            source_hash=f"hash_summary_{uuid.uuid4().hex[:8]}_3",
            created_at=datetime.now()
        )
    ]
    
    db_session.add_all(trades)
    db_session.commit()
    
    response = client.get(f"/portfolio/trades/summary?user_id={user_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["user_id"] == user_id
    assert data["trades_count"] == 3
    assert data["symbols_count"] == 2  # AAPL, TSLA
    assert data["min_trade_date"] == "2024-01-01"
    assert data["max_trade_date"] == "2024-02-01"
    
    # 驗證 evidence
    assert "verification_sql" in data["evidence"]


def test_rebuild_positions_require_trades_blocks_when_empty(client, db_session: Session):
    """測試：require_trades=true 且 trades=0 時，回傳 409 Conflict。
    
    驗證：
    - HTTP status = 409
    - detail.status = "precondition_failed"
    - detail.evidence.decision = "blocked_precondition"
    - detail.evidence 包含 verification_sql
    """
    user_id = "test_blocked_user"
    
    # 確保該用戶無交易記錄
    db_session.query(Position).filter(Position.user_id == user_id).delete()
    db_session.query(Trade).filter(Trade.user_id == user_id).delete()
    db_session.commit()
    
    response = client.post(
        f"/portfolio/rebuild_positions?user_id={user_id}&require_trades=1"
    )
    
    assert response.status_code == 409
    data = response.json()
    
    # 驗證 detail 結構（HTTPException 的 detail 會被放在 response.json()["detail"]）
    detail = data["detail"]
    
    assert detail["status"] == "precondition_failed"
    assert detail["user_id"] == user_id
    assert detail["symbols_count"] == 0
    assert detail["upserted_count"] == 0
    
    # 驗證 evidence
    assert "evidence" in detail
    evidence = detail["evidence"]
    
    assert evidence["require_trades"] is True
    assert evidence["decision"] == "blocked_precondition"
    assert evidence["trades_count"] == 0
    assert evidence["distinct_symbols_count"] == 0
    
    # 驗證可證偽的 verification_sql
    assert "verification_sql" in evidence
    assert "trades_count" in evidence["verification_sql"]
    assert "distinct_symbols" in evidence["verification_sql"]


def test_rebuild_positions_require_trades_proceeds_when_has_trades(client, db_session: Session):
    """測試：require_trades=true 且 trades>0 時，正常執行 rebuild。
    
    驗證：
    - HTTP status = 200
    - status = "succeeded"
    - symbols_count > 0
    - evidence.decision = "proceed"
    - evidence 包含可證偽的 verification_sql
    """
    user_id = "test_proceed_user"
    
    # 清理舊資料
    db_session.query(Position).filter(Position.user_id == user_id).delete()
    db_session.query(Trade).filter(Trade.user_id == user_id).delete()
    db_session.commit()
    
    # 插入測試交易
    import uuid
    trade = Trade(
        user_id=user_id,
        symbol="AAPL",
        asset_ccy="USD",
        quantity=Decimal("10"),
        price=Decimal("150.0"),
        fee=Decimal("0"),
        trade_date=datetime(2024, 1, 1),
        side="buy",
        broker="test",
        source_hash=f"hash_proceed_{uuid.uuid4().hex}",
        created_at=datetime.now()
    )
    db_session.add(trade)
    db_session.commit()
    
    response = client.post(
        f"/portfolio/rebuild_positions?user_id={user_id}&require_trades=1"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "succeeded"
    assert data["user_id"] == user_id
    assert data["symbols_count"] > 0
    
    # 驗證 evidence
    assert "evidence" in data
    evidence = data["evidence"]
    
    assert evidence["require_trades"] is True
    assert evidence["decision"] == "proceed"
    assert evidence["trades_count"] > 0
    assert evidence["distinct_symbols_count"] > 0
    
    # 驗證可證偽的 verification_sql
    assert "verification_sql" in evidence
    assert "trades_count" in evidence["verification_sql"]
    assert "distinct_symbols" in evidence["verification_sql"]
    assert "positions_count" in evidence["verification_sql"]


def test_rebuild_positions_default_require_trades_false_allows_empty(client, db_session: Session):
    """測試：require_trades 預設 false，允許 trades=0 的情況（保持相容）。
    
    驗證：
    - HTTP status = 200（不被擋）
    - status = "succeeded"
    - symbols_count = 0（因為無交易）
    - evidence.require_trades = false
    """
    user_id = "test_default_user"
    
    # 確保該用戶無交易記錄
    db_session.query(Position).filter(Position.user_id == user_id).delete()
    db_session.query(Trade).filter(Trade.user_id == user_id).delete()
    db_session.commit()
    
    # 不傳 require_trades（預設 false）
    response = client.post(
        f"/portfolio/rebuild_positions?user_id={user_id}"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "succeeded"
    assert data["symbols_count"] == 0
    
    # 驗證 evidence
    assert data["evidence"]["require_trades"] is False
    assert data["evidence"]["decision"] == "proceed"
    assert data["evidence"]["trades_count"] == 0


def test_evidence_verification_sql_contains_all_required_fields(client, db_session: Session):
    """測試：evidence.verification_sql 包含所有必要欄位。
    
    驗證（trades/summary）：
    - verification_sql.trades_count 存在
    - verification_sql.distinct_symbols 存在
    
    驗證（rebuild_positions）：
    - verification_sql.trades_count 存在
    - verification_sql.distinct_symbols 存在
    - verification_sql.positions_count 存在（當 proceed 時）
    """
    user_id = "test_verification_user"
    
    # 清理並插入測試資料
    db_session.query(Position).filter(Position.user_id == user_id).delete()
    db_session.query(Trade).filter(Trade.user_id == user_id).delete()
    db_session.commit()
    
    import uuid
    trade = Trade(
        user_id=user_id,
        symbol="AAPL",
        asset_ccy="USD",
        quantity=Decimal("10"),
        price=Decimal("150.0"),
        fee=Decimal("0"),
        trade_date=datetime(2024, 1, 1),
        side="buy",
        broker="test",
        source_hash=f"hash_verification_{uuid.uuid4().hex}",
        created_at=datetime.now()
    )
    db_session.add(trade)
    db_session.commit()
    
    # 測試 trades/summary
    response = client.get(f"/portfolio/trades/summary?user_id={user_id}")
    assert response.status_code == 200
    summary_data = response.json()
    
    assert "verification_sql" in summary_data["evidence"]
    summary_sql = summary_data["evidence"]["verification_sql"]
    assert "trades_count" in summary_sql
    assert "distinct_symbols" in summary_sql
    
    # 測試 rebuild_positions（require_trades=true）
    response = client.post(
        f"/portfolio/rebuild_positions?user_id={user_id}&require_trades=1"
    )
    assert response.status_code == 200
    rebuild_data = response.json()
    
    assert "verification_sql" in rebuild_data["evidence"]
    rebuild_sql = rebuild_data["evidence"]["verification_sql"]
    assert "trades_count" in rebuild_sql
    assert "distinct_symbols" in rebuild_sql
    assert "positions_count" in rebuild_sql
