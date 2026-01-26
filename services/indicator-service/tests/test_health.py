"""Health endpoint tests for indicator-service."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_service_name() -> None:
    """Confirm /health endpoint returns standard status format."""
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "indicator-service"
    assert "provider" in payload
