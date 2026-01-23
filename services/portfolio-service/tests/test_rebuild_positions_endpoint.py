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
    - rebuilt_symbols_count 欄位存在且為整數
    - warnings 欄位存在且為陣列
    """
    response = client.post(
        "/portfolio/rebuild_positions",
        json={"user_id": "tony"}
    )
    
    data = response.json()
    
    # 驗證必要欄位存在
    assert "status" in data, "回應缺少 status 欄位"
    assert "rebuilt_symbols_count" in data, "回應缺少 rebuilt_symbols_count 欄位"
    assert "warnings" in data, "回應缺少 warnings 欄位"
    
    # 驗證欄位型別
    assert isinstance(data["status"], str), "status 應為字串"
    assert isinstance(data["rebuilt_symbols_count"], int), "rebuilt_symbols_count 應為整數"
    assert isinstance(data["warnings"], list), "warnings 應為陣列"


def test_rebuild_positions_status_succeeded(client):
    """測試：骨架階段回傳 succeeded 狀態。
    
    驗證：
    - status = "succeeded"
    - rebuilt_symbols_count = 0（當前階段固定值）
    - warnings = []（當前階段無警告）
    """
    response = client.post(
        "/portfolio/rebuild_positions",
        json={"user_id": "tony"}
    )
    
    data = response.json()
    
    assert data["status"] == "succeeded", f"預期 status=succeeded，實際：{data['status']}"
    assert data["rebuilt_symbols_count"] == 0, "當前階段應回傳 0"
    assert data["warnings"] == [], "當前階段應無警告訊息"


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
    # Pydantic V2 錯誤格式：{"detail": [{"type": "missing", "loc": ["body", "user_id"], ...}]}
    assert "detail" in error_detail


def test_rebuild_positions_empty_user_id(client):
    """測試：user_id 為空字串時回傳 422。
    
    驗證：
    - HTTP status code = 422（Pydantic min_length=1 驗證失敗）
    - 錯誤訊息包含驗證錯誤資訊
    
    Notes:
        - Pydantic 會在 request validation 階段就擋住空字串
        - 這是正確的防禦性設計（在最外層驗證輸入）
    """
    response = client.post(
        "/portfolio/rebuild_positions",
        json={"user_id": ""}
    )
    
    assert response.status_code == 422, f"預期 422，實際：{response.status_code}"
    error_detail = response.json()
    assert "detail" in error_detail


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
