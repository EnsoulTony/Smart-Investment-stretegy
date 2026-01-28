"""Tests for core holdings API (user-managed)."""

from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
from app.models_core import CoreHolding

client = TestClient(app)


def setup_function(function):
    # clean tables between tests
    db = next(get_db())
    db.query(CoreHolding).delete()
    db.commit()


def test_rebuild_core_holdings_deprecated():
    resp = client.post("/portfolio/core_holdings/rebuild", params={"user_id": "tony"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "deprecated"
    assert payload["rows_marked"] == 0
    assert payload["rows_upserted"] == 0


def test_replace_core_holdings_via_post():
    # seed existing core holding
    db = next(get_db())
    db.add(CoreHolding(user_id="tony", symbol="OLD", is_core=True))
    db.commit()

    resp = client.post(
        "/portfolio/core_holdings",
        params={"user_id": "tony"},
        json={
            "items": [
                {"symbol": "TSLA", "name_zh": "特斯拉"},
                {"symbol": "OXY", "name_zh": "西方石油"},
                {"symbol": "tsm", "name_zh": "台積電 ADR"},
                {"symbol": "TSLA", "name_zh": "特斯拉"},
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 3

    resp2 = client.get("/portfolio/core_holdings", params={"user_id": "tony"})
    syms = sorted(resp2.json()["symbols"])
    assert syms == ["OXY", "TSLA", "TSM"]
    items = resp2.json()["items"]
    name_map = {item["symbol"]: item["name_zh"] for item in items}
    assert name_map["TSLA"] == "特斯拉"
