"""Valuation portfolio API tests."""

from datetime import date
from fastapi.testclient import TestClient

import app.main as main


class _StubClient:
    async def get_trades_summary(self, user_id: str):
        return {
            "user_id": user_id,
            "trades_count": 2,
            "symbols_count": 1,
            "evidence": {
                "verification_sql": {
                    "trades_count": "select count(*) from trades where user_id='tony';",
                    "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';",
                }
            },
        }

    async def get_positions(self, user_id: str):
        return [
            {
                "symbol": "AAPL",
                "asset_ccy": "USD",
                "quantity": 10,
                "avg_cost": 100,
            }
        ]


class _StubEmptyTradesClient(_StubClient):
    async def get_trades_summary(self, user_id: str):
        return {
            "user_id": user_id,
            "trades_count": 0,
            "symbols_count": 0,
            "evidence": {"verification_sql": {"trades_count": "select 0"}},
        }


def test_valuation_portfolio_success(monkeypatch):
    monkeypatch.setattr(main, "PortfolioClient", lambda: _StubClient())
    client = TestClient(main.app)

    response = client.get("/valuation/portfolio", params={"user_id": "tony", "base_ccy": "USD", "as_of": "2026-01-24"})
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "succeeded"
    assert data["user_id"] == "tony"
    assert data["base_ccy"] == "USD"
    assert data["as_of"] == "2026-01-24"
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["symbol"] == "AAPL"
    assert item["fx_rate_to_base"] == 1.0
    assert "market_value" in item
    assert "unrealized_pnl" in item

    evidence = data["evidence"]
    assert evidence["positions_count"] == 1
    assert evidence["trades_count"] == 2
    assert evidence["distinct_symbols_count"] == 1
    assert "positions_hash" in evidence
    assert "verification_sql" in evidence
    assert "providers" in evidence


def test_valuation_portfolio_precondition_failed(monkeypatch):
    monkeypatch.setattr(main, "PortfolioClient", lambda: _StubEmptyTradesClient())
    client = TestClient(main.app)

    response = client.get("/valuation/portfolio", params={"user_id": "tony"})
    assert response.status_code == 409
    data = response.json()
    assert data["detail"]["status"] == "precondition_failed"
    assert data["detail"]["evidence"]["trades_count"] == 0
