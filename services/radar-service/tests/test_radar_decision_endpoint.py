"""Tests for GET /radar/decision endpoint with mocked upstream services.

Verifies:
- Response contains evidence.inputs_hash
- Response contains at least 1 falsifiable trigger
- Response has cooldown=5
- Upstream errors return appropriate status codes
"""

from unittest.mock import patch, AsyncMock
import pytest
import httpx
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# =============================================================================
# Mock Response Data
# =============================================================================

MOCK_POSITIONS_RESPONSE = {
    "user_id": "tony",
    "asof": "2025-01-20",
    "items": [
        {
            "symbol": "TSLA",
            "asset_ccy": "USD",
            "quantity": 10.0,
            "avg_cost": 200.0,
            "realized_pnl": 0.0,
            "cost_basis": 2000.0,
        },
        {
            "symbol": "QQQ",
            "asset_ccy": "USD",
            "quantity": 5.0,
            "avg_cost": 400.0,
            "realized_pnl": 0.0,
            "cost_basis": 2000.0,
        },
    ],
    "next_cursor": None,
}

MOCK_INDICATORS_RESPONSE = {
    "as_of": "2025-01-20",
    "version": "0.1",
    "source": "stub",
    "XLU": {"close": 72.0, "ma20": 71.5, "ma50": 71.0},
    "XLK": {"close": 220.0, "ma20": 218.0, "ma50": 215.0},
    "ratio": {
        "pair": "XLK/XLU",
        "value": 3.055,
        "ma20": 3.020,
        "ma50": 3.028,
        "slope5": 0.002,
        "value_5d_ago": 3.045,
    },
}

MOCK_NEWS_SIGNALS = [
    {
        "signal_id": "stub-n1",
        "tier": "N1",
        "payload": {
            "tier": "N1",
            "falsifiable_triggers": [
                {"type": "market", "name": "US10Y", "condition": "break_above_4.5", "value": 4.5}
            ],
        },
        "signal_hash": "hash-n1",
    },
    {
        "signal_id": "stub-n3",
        "tier": "N3",
        "payload": {
            "tier": "N3",
            "falsifiable_triggers": [
                {"type": "market", "name": "WTI", "condition": "break_above_90", "value": 90}
            ],
        },
        "signal_hash": "hash-n3",
    },
]


def make_mock_httpx_client(positions_response, indicators_response):
    """Create mock httpx.AsyncClient that returns specified responses."""
    async def mock_get(url, params=None, **kwargs):
        mock_response = AsyncMock(spec=httpx.Response)

        if "/portfolio/positions" in url:
            mock_response.json.return_value = positions_response
            mock_response.status_code = 200
        elif "/indicators/sector-rotation" in url:
            mock_response.json.return_value = indicators_response
            mock_response.status_code = 200
        else:
            mock_response.status_code = 404
            mock_response.json.return_value = {"detail": "Not found"}

        mock_response.raise_for_status = lambda: None
        return mock_response

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    return mock_client


# =============================================================================
# Test: Successful Decision Endpoint
# =============================================================================

class TestRadarDecisionEndpoint:
    """Test GET /radar/decision with mocked upstream services."""

    @patch("app.main.upsert_decision_snapshot")
    @patch("app.main.fetch_news_signals")
    @patch("httpx.AsyncClient")
    def test_decision_returns_200(self, mock_client_class, mock_fetch_news, mock_upsert) -> None:
        """Valid request returns 200."""
        mock_fetch_news.return_value = MOCK_NEWS_SIGNALS
        mock_client_class.return_value = make_mock_httpx_client(
            MOCK_POSITIONS_RESPONSE, MOCK_INDICATORS_RESPONSE
        )

        response = client.get("/radar/decision?user_id=tony&base_ccy=TWD")

        assert response.status_code == 200

    @patch("app.main.upsert_decision_snapshot")
    @patch("app.main.fetch_news_signals")
    @patch("httpx.AsyncClient")
    def test_decision_contains_evidence_inputs_hash(self, mock_client_class, mock_fetch_news, mock_upsert) -> None:
        """Response must contain evidence.inputs_hash."""
        mock_fetch_news.return_value = MOCK_NEWS_SIGNALS
        mock_client_class.return_value = make_mock_httpx_client(
            MOCK_POSITIONS_RESPONSE, MOCK_INDICATORS_RESPONSE
        )

        response = client.get("/radar/decision?user_id=tony")
        data = response.json()

        assert "evidence" in data
        assert "inputs_hash" in data["evidence"]
        assert len(data["evidence"]["inputs_hash"]) == 64  # SHA256

    @patch("app.main.upsert_decision_snapshot")
    @patch("app.main.fetch_news_signals")
    @patch("httpx.AsyncClient")
    def test_decision_contains_required_fields(self, mock_client_class, mock_fetch_news, mock_upsert) -> None:
        """Response contains all required OutputSchema fields."""
        mock_fetch_news.return_value = MOCK_NEWS_SIGNALS
        mock_client_class.return_value = make_mock_httpx_client(
            MOCK_POSITIONS_RESPONSE, MOCK_INDICATORS_RESPONSE
        )

        response = client.get("/radar/decision?user_id=tony")
        data = response.json()

        # Required fields
        assert "schema_version" in data
        assert "as_of" in data
        assert "user_id" in data
        assert "mode" in data
        assert "decision" in data
        assert "actions" in data
        assert "evidence" in data
        assert "news_context" in data["evidence"]
        assert "tiers_count" in data["evidence"]["news_context"]

        # Mode must be valid
        assert data["mode"] in ["RISK_ON", "RISK_OFF", "TRANSITION"]

        # Decision must be valid
        assert data["decision"] in ["NO_ACTION", "REDUCE_RISK", "REBALANCE", "WATCHLIST"]

    @patch("app.main.upsert_decision_snapshot")
    @patch("app.main.fetch_news_signals")
    @patch("httpx.AsyncClient")
    def test_decision_actions_have_triggers(self, mock_client_class, mock_fetch_news, mock_upsert) -> None:
        """Actions must have at least 1 falsifiable trigger."""
        mock_fetch_news.return_value = MOCK_NEWS_SIGNALS
        mock_client_class.return_value = make_mock_httpx_client(
            MOCK_POSITIONS_RESPONSE, MOCK_INDICATORS_RESPONSE
        )

        response = client.get("/radar/decision?user_id=tony")
        data = response.json()

        # If there are actions, each must have triggers
        for action in data.get("actions", []):
            assert "falsifiable_triggers" in action
            assert len(action["falsifiable_triggers"]) >= 1, \
                f"Action {action.get('symbol')} has no triggers"

    @patch("app.main.upsert_decision_snapshot")
    @patch("app.main.fetch_news_signals")
    @patch("httpx.AsyncClient")
    def test_decision_actions_have_cooldown_5(self, mock_client_class, mock_fetch_news, mock_upsert) -> None:
        """All actions should have cooldown_days=5."""
        mock_fetch_news.return_value = MOCK_NEWS_SIGNALS
        mock_client_class.return_value = make_mock_httpx_client(
            MOCK_POSITIONS_RESPONSE, MOCK_INDICATORS_RESPONSE
        )

        response = client.get("/radar/decision?user_id=tony")
        data = response.json()

        for action in data.get("actions", []):
            assert "constraints" in action
            assert action["constraints"].get("cooldown_days") == 5

    @patch("app.main.upsert_decision_snapshot")
    @patch("app.main.fetch_news_signals")
    @patch("httpx.AsyncClient")
    def test_decision_with_empty_positions(self, mock_client_class, mock_fetch_news, mock_upsert) -> None:
        """Empty positions should still return valid response."""
        mock_fetch_news.return_value = MOCK_NEWS_SIGNALS
        mock_client_class.return_value = make_mock_httpx_client(
            {"user_id": "tony", "items": [], "next_cursor": None},
            MOCK_INDICATORS_RESPONSE,
        )

        response = client.get("/radar/decision?user_id=tony")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] in ["RISK_ON", "RISK_OFF", "TRANSITION"]


# =============================================================================
# Test: Error Handling
# =============================================================================

class TestRadarDecisionErrors:
    """Test error handling for /radar/decision endpoint."""

    def test_missing_user_id_returns_422(self) -> None:
        """Missing user_id returns 422."""
        response = client.get("/radar/decision")

        assert response.status_code == 422

    def test_invalid_date_returns_422(self) -> None:
        """Invalid as_of date format returns 422."""
        response = client.get("/radar/decision?user_id=tony&as_of=invalid")

        assert response.status_code == 422
        data = response.json()
        assert "Invalid date format" in data.get("detail", {}).get("message", "")

    def test_invalid_plugin_returns_422(self) -> None:
        """Invalid plugin name returns 422."""
        response = client.get("/radar/decision?user_id=tony&plugin=invalid_plugin")

        assert response.status_code == 422
        data = response.json()
        assert "not found" in data.get("detail", {}).get("message", "").lower()

    @patch("httpx.AsyncClient")
    def test_portfolio_service_error_returns_502(self, mock_client_class) -> None:
        """Portfolio service connection error returns 502."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        response = client.get("/radar/decision?user_id=tony")

        assert response.status_code == 502
        data = response.json()
        assert data["detail"]["service"] == "portfolio-service"

    @patch("httpx.AsyncClient")
    def test_indicator_service_error_returns_502(self, mock_client_class) -> None:
        """Indicator service error after positions success returns 502."""
        call_count = 0

        async def mock_get(url, params=None, **kwargs):
            nonlocal call_count
            call_count += 1

            mock_response = AsyncMock(spec=httpx.Response)

            if "/portfolio/positions" in url:
                mock_response.json.return_value = MOCK_POSITIONS_RESPONSE
                mock_response.status_code = 200
                mock_response.raise_for_status = lambda: None
                return mock_response
            elif "/indicators/sector-rotation" in url:
                raise httpx.RequestError("Connection refused")
            else:
                mock_response.status_code = 404
                return mock_response

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        response = client.get("/radar/decision?user_id=tony")

        assert response.status_code == 502
        data = response.json()
        assert data["detail"]["service"] == "indicator-service"


# =============================================================================
# Test: Health and Plugins Endpoints
# =============================================================================

class TestHealthAndPlugins:
    """Test health and plugins endpoints."""

    def test_health_endpoint(self) -> None:
        """Health endpoint returns ok with plugins list."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "plugins" in data
        assert "v1.4" in data["plugins"]

    def test_plugins_endpoint(self) -> None:
        """Plugins endpoint lists available plugins."""
        response = client.get("/radar/plugins")

        assert response.status_code == 200
        data = response.json()
        assert "plugins" in data
        assert len(data["plugins"]) >= 1
        assert data["default"] == "v1.4"
