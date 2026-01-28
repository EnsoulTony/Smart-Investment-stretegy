"""Tests for /radar/decisions/history endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.fetch_decision_history")
def test_history_endpoint_returns_list(mock_fetch) -> None:
    mock_fetch.return_value = [
        {
            "as_of": "2026-01-28",
            "mode": "RISK_ON",
            "decision": "NO_ACTION",
            "inputs_hash": "hash",
            "created_at": "2026-01-28T00:00:00Z",
        }
    ]

    response = client.get("/radar/decisions/history?user_id=tony&limit=5")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["as_of"] == "2026-01-28"
