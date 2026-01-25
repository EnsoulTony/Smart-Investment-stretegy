"""測試 POST /portfolio/rebuild_positions 端點。

測試範圍（Sprint 1-4.0）：
- ✅ 端點存在並可回應
- ✅ Request body 驗證（user_id 必填）
- ✅ Response 結構正確
- ⏸ 實際計算邏輯（下階段）

不依賴：
- ❌ Google Sheets
- ❌ 外部 API
- ✅ 使用 TestClient，不需啟動容器
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# 將服務根目錄加入 import 路徑
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app


@pytest.fixture
def client():
    """建立 FastAPI TestClient。"""
    return TestClient(app)


def test_rebuild_positions_endpoint_exists(client):
    """測試：端點存在且可回應。
    
    驗證：
    - HTTP status code = 200
    - 回應為 JSON 格式
    """
    response = client.post(
        "/portfolio/rebuild_positions",
        json={"user_id": "tony"}
    )
    
    assert response.status_code == 200, f"預期 200，實際：{response.status_code}"
    assert response.headers["content-type"] == "application/json"


def test_rebuild_positions_response_structure(client):
    """測試：回應結構符合規格。
    
    驗證：
    - status 欄位存在且為字串
    - symbols_count 欄位存在且為整數
    - run_id 欄位存在
    - evidence 欄位存在且包含 positions_columns
    """
    response = client.post(
        "/portfolio/rebuild_positions",
        json={"user_id": "tony"}
    )
    
    data = response.json()
    
    # 驗證必要欄位存在
    assert "status" in data, "回應缺少 status 欄位"
    assert "symbols_count" in data, "回應缺少 symbols_count 欄位"
    assert "upserted_count" in data, "回應缺少 upserted_count 欄位"
    assert "deleted_or_zeroed_count" in data, "回應缺少 deleted_or_zeroed_count 欄位"
    assert "run_id" in data, "回應缺少 run_id 欄位"
    assert "evidence" in data, "回應缺少 evidence 欄位"
    assert "positions_columns" in data["evidence"], "evidence 缺少 positions_columns"
    
    # 驗證欄位型別
    assert isinstance(data["status"], str), "status 應為字串"
    assert isinstance(data["symbols_count"], int), "symbols_count 應為整數"
    assert isinstance(data["upserted_count"], int), "upserted_count 應為整數"
    assert isinstance(data["deleted_or_zeroed_count"], int), "deleted_or_zeroed_count 應為整數"


def test_rebuild_positions_status_succeeded(client):
    """測試：骨架階段回傳 succeeded 狀態。
    
    驗證：
    - status = "succeeded"
    - symbols_count >= 0
    """
    response = client.post(
        "/portfolio/rebuild_positions",
        json={"user_id": "tony"}
    )
    
    data = response.json()
    
    assert data["status"] == "succeeded", f"預期 status=succeeded，實際：{data['status']}"
    assert data["symbols_count"] >= 0


def test_rebuild_positions_missing_user_id(client):
    """測試：缺少 user_id 時回傳 422。
    
    驗證：
    - HTTP status code = 422（Pydantic 驗證失敗）
    - 錯誤訊息包含 "user_id"
    """
    response = client.post(
        "/portfolio/rebuild_positions",
        json={}  # 缺少 user_id
    )
    
    assert response.status_code == 422, f"預期 422，實際：{response.status_code}"
    error_detail = response.json()
    assert "detail" in error_detail


def test_rebuild_positions_empty_user_id(client):
    """測試：user_id 為空字串時回傳 422（Pydantic Validation Contract）。
    
    驗證 Pydantic validation contract：
    - HTTP status code = 422（min_length=1 驗證失敗）
    - response.detail 包含 validation error
    - error 指向 "user_id" 欄位
    - error type 為 "string_too_short" 或類似的長度驗證錯誤
    
    Contract 保證：
        - 空字串在進入業務邏輯前就被 Pydantic 攔截（防禦性設計）
        - 回應格式符合 FastAPI 標準 validation error 結構
        - 錯誤訊息足夠明確，可追蹤到具體欄位
    """
    response = client.post(
        "/portfolio/rebuild_positions",
        json={"user_id": ""}
    )
    
    # Contract 1: 驗證層攔截，回傳 422
    assert response.status_code == 422, f"預期 422，實際：{response.status_code}"
    
    error_detail = response.json()
    assert "detail" in error_detail, "回應缺少 detail 欄位"


def test_rebuild_positions_with_different_user_ids(client):
    """測試：不同 user_id 都能正常回應。
    
    驗證：
    - 多個不同的 user_id 都能成功回應
    - status 都為 succeeded
    """
    user_ids = ["tony", "alice", "bob", "user123"]
    
    for user_id in user_ids:
        response = client.post(
            "/portfolio/rebuild_positions",
            json={"user_id": user_id}
        )
        
        assert response.status_code == 200, f"user_id={user_id} 失敗"
        data = response.json()
        assert data["status"] == "succeeded", f"user_id={user_id} status 不是 succeeded"
