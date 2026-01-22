"""Radar Service 的最小健康檢查測試。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_service_name() -> None:
    """確認 /health 端點可回傳標準狀態格式。"""
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"]
