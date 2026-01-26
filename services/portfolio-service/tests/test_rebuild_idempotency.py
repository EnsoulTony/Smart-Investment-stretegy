"""測試 rebuild_positions 的 idempotency（可重複執行性）。

Sprint 1-4.B 驗收測試：
- ✅ rebuild 第一次成功
- ✅ rebuild 第二次仍然成功（不會出現 UniqueViolation）
- ✅ positions_hash 兩次相同（trades 未變時）
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from decimal import Decimal
from datetime import date, timedelta

from app.models import Trade, Position

from app.main import app, get_db


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with database session dependency override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_rebuild_positions_overwrite_existing_positions_no_unique_violation(
    client: TestClient,
    db_session: Session
):
    """測試 rebuild_positions 覆蓋既有 positions 不會出現 UniqueViolation。
    
    驗收需求（Sprint 1-4.B）：
    - Arrange: 插入 trades，執行第一次 rebuild（成功）
    - Act: 執行第二次 rebuild（應仍然成功，不會UniqueViolation）
    - Assert:
        - 第二次 status == succeeded
        - DB positions_count == 回傳的 upserted_count
        - 沒有 IntegrityError/UniqueViolation
        - positions_hash 第二次與第一次一致（trades 未變）
    """
    user_id = "test_idempotent_user"
    
    # Arrange: 插入測試 trades
    trades = [
        Trade(
            user_id=user_id,
            symbol="AAPL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("150.00"),
            fee=Decimal("1.00"),
            trade_date=date.today() - timedelta(days=10),
            broker="IB",
            source_hash=f"test_hash_aapl_1"
        ),
        Trade(
            user_id=user_id,
            symbol="TSLA",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("50"),
            price=Decimal("200.00"),
            fee=Decimal("0.50"),
            trade_date=date.today() - timedelta(days=5),
            broker="IB",
            source_hash=f"test_hash_tsla_1"
        )
    ]
    
    for trade in trades:
        db_session.add(trade)
    db_session.commit()
    
    # Act 1: 第一次 rebuild
    response1 = client.post(
        f"/portfolio/rebuild_positions?user_id={user_id}&require_trades=1"
    )
    
    assert response1.status_code == 200, f"第一次 rebuild 失敗: {response1.text}"
    result1 = response1.json()
    
    assert result1["status"] == "succeeded", f"第一次 status 不是 succeeded: {result1}"
    positions_hash_1 = result1.get("positions_hash")
    assert positions_hash_1, "第一次 rebuild 沒有回傳 positions_hash"
    
    # 檢查 DB 中的 positions
    positions_count_1 = db_session.query(Position).filter(Position.user_id == user_id).count()
    assert positions_count_1 == result1["upserted_count"], f"DB positions_count 不符: {positions_count_1} != {result1['upserted_count']}"
    
    # Act 2: 第二次 rebuild（關鍵測試：不應該出現 UniqueViolation）
    response2 = client.post(
        f"/portfolio/rebuild_positions?user_id={user_id}&require_trades=1"
    )
    
    # Assert 2: 第二次也必須成功
    assert response2.status_code == 200, f"第二次 rebuild 失敗（UniqueViolation?）: {response2.text}"
    result2 = response2.json()
    
    assert result2["status"] == "succeeded", f"第二次 status 不是 succeeded: {result2}"
    positions_hash_2 = result2.get("positions_hash")
    assert positions_hash_2, "第二次 rebuild 沒有回傳 positions_hash"
    
    # 檢查 DB 中的 positions（數量應該相同）
    positions_count_2 = db_session.query(Position).filter(Position.user_id == user_id).count()
    assert positions_count_2 == result2["upserted_count"], f"第二次 DB positions_count 不符: {positions_count_2} != {result2['upserted_count']}"
    
    # 驗證 positions_hash 一致（trades 沒變的情況下）
    assert positions_hash_1 == positions_hash_2, f"positions_hash 不一致: {positions_hash_1} != {positions_hash_2}"
    
    # 驗證兩次的 positions 數量相同（idempotent）
    assert result1["upserted_count"] == result2["upserted_count"], f"upserted_count 不一致: {result1['upserted_count']} != {result2['upserted_count']}"
    
    print(f"✅ Idempotency test passed:")
    print(f"  - First rebuild: {result1['upserted_count']} positions, hash={positions_hash_1[:8]}...")
    print(f"  - Second rebuild: {result2['upserted_count']} positions, hash={positions_hash_2[:8]}...")
    print(f"  - No UniqueViolation occurred")


def test_preview_and_write_hash_consistency(
    client: TestClient,
    db_session: Session
):
    """測試 preview 與 write 的 positions_hash 一致性。
    
    驗收需求（Sprint 1-4.B）：
    - preview 與 write 的 hash 必須一致（同一份 trades）
    """
    user_id = "test_preview_write_user"
    
    # Arrange: 插入測試 trades
    trades = [
        Trade(
            user_id=user_id,
            symbol="GOOGL",
            asset_ccy="USD",
            side="BUY",
            quantity=Decimal("30"),
            price=Decimal("2800.00"),
            fee=Decimal("2.00"),
            trade_date=date.today() - timedelta(days=3),
            broker="IB",
            source_hash=f"test_hash_googl_1"
        )
    ]
    
    for trade in trades:
        db_session.add(trade)
    db_session.commit()
    
    # Act 1: preview
    preview_response = client.get(
        f"/portfolio/rebuild_positions/preview?user_id={user_id}&require_trades=1"
    )
    
    assert preview_response.status_code == 200, f"preview 失敗: {preview_response.text}"
    preview_result = preview_response.json()
    
    assert preview_result["status"] == "preview", f"preview status 不是 preview: {preview_result}"
    preview_hash = preview_result.get("positions_hash")
    assert preview_hash, "preview 沒有回傳 positions_hash"    
    # Act 2: write
    write_response = client.post(
        f"/portfolio/rebuild_positions?user_id={user_id}&require_trades=1"
    )
    
    assert write_response.status_code == 200, f"write 失敗: {write_response.text}"
    write_result = write_response.json()
    
    assert write_result["status"] == "succeeded", f"write status 不是 succeeded: {write_result}"
    write_hash = write_result.get("positions_hash")
    assert write_hash, "write 沒有回傳 positions_hash"
    
    # Assert: hash 必須一致
    assert preview_hash == write_hash, f"preview 與 write 的 hash 不一致: {preview_hash} != {write_hash}"
    
    print(f"✅ Preview/Write hash consistency test passed:")
    print(f"  - Preview hash: {preview_hash[:16]}...")
    print(f"  - Write hash: {write_hash[:16]}...")


def test_preview_require_trades_blocks_when_empty(
    client: TestClient,
    db_session: Session
):
    """測試 preview 的 require_trades=true 能正確擋住空 trades。
    
    驗收需求（Sprint 1-4.B）：
    - preview 也要支援 require_trades 參數
    - trades_count=0 且 require_trades=true → 回傳 409
    """
    user_id = "test_preview_empty_trades_user"
    
    # Arrange: 不插入任何 trades
    
    # Act: preview with require_trades=true
    response = client.get(
        f"/portfolio/rebuild_positions/preview?user_id={user_id}&require_trades=1"
    )
    
    # Assert: 應該回傳 409 Conflict
    assert response.status_code == 409, f"預期 409，但得到 {response.status_code}: {response.text}"
    
    result = response.json()
    assert "detail" in result
    detail = result["detail"]
    
    assert detail["status"] == "precondition_failed", f"status 不是 precondition_failed: {detail}"
    assert detail["trades_count"] == 0, f"trades_count 應該是 0: {detail}"
    assert detail["computed_positions_count"] == 0, f"computed_positions_count 應該是 0: {detail}"
    
    # 檢查 evidence
    evidence = detail.get("evidence", {})
    assert evidence["decision"] == "blocked", f"evidence decision 不是 blocked: {evidence}"
    assert "verification_sql" in evidence, "evidence 缺少 verification_sql"
    
    print(f"✅ Preview require_trades test passed:")
    print(f"  - Status: {detail['status']}")
    print(f"  - Trades count: {detail['trades_count']}")
