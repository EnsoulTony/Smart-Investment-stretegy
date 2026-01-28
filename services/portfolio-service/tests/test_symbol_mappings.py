"""Tests for symbol_name_mappings API."""

from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
from app.models_core import SymbolNameMapping

client = TestClient(app)


def setup_function(function):
    db = next(get_db())
    db.query(SymbolNameMapping).delete()
    db.commit()


def test_upsert_and_list_symbol_mappings():
    resp = client.post(
        "/portfolio/symbol_mappings",
        json={
            "symbol": "AAPL",
            "market": "US",
            "name_zh": "蘋果",
            "source": "manual",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["symbol"] == "AAPL"
    assert payload["market"] == "US"
    assert payload["name_zh"] == "蘋果"

    resp2 = client.get("/portfolio/symbol_mappings")
    assert resp2.status_code == 200
    items = resp2.json()["items"]
    assert len(items) == 1
    assert items[0]["symbol"] == "AAPL"
    assert items[0]["market"] == "US"

