"""Tests for core holdings API and sync from trades."""

from fastapi.testclient import TestClient
from datetime import datetime

from app.main import app
from app.db import get_db
from app.models import Trade
from app.models_core import CoreHolding

client = TestClient(app)


def setup_function(function):
    # clean tables between tests
    db = next(get_db())
    db.query(CoreHolding).delete()
    db.query(Trade).delete()
    db.commit()


def test_rebuild_core_holdings_from_trades():
    db = next(get_db())
    trade = Trade(
        user_id="tony",
        symbol="TSLA",
        asset_ccy="USD",
        side="BUY",
        quantity=1,
        price=100,
        fee=0,
        trade_date=datetime(2026, 1, 20),
        broker="test",
        source_hash="hash1",
        is_core=True,
    )
    db.add(trade)
    db.commit()

    resp = client.post("/portfolio/core_holdings/rebuild", params={"user_id": "tony"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["rows_marked"] == 1
    assert payload["rows_upserted"] == 1

    resp2 = client.get("/portfolio/core_holdings", params={"user_id": "tony"})
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["symbols"] == ["TSLA"]


def test_core_holdings_only_is_core_true():
    db = next(get_db())
    trade_true = Trade(
        user_id="tony",
        symbol="OXY",
        asset_ccy="USD",
        side="BUY",
        quantity=1,
        price=60,
        fee=0,
        trade_date=datetime(2026, 1, 21),
        broker="test",
        source_hash="hash2",
        is_core=True,
    )
    trade_false = Trade(
        user_id="tony",
        symbol="CCJ",
        asset_ccy="USD",
        side="BUY",
        quantity=1,
        price=40,
        fee=0,
        trade_date=datetime(2026, 1, 22),
        broker="test",
        source_hash="hash3",
        is_core=False,
    )
    db.add_all([trade_true, trade_false])
    db.commit()

    client.post("/portfolio/core_holdings/rebuild", params={"user_id": "tony"})
    resp = client.get("/portfolio/core_holdings", params={"user_id": "tony"})
    symbols = resp.json()["symbols"]
    assert symbols == ["OXY"]


def test_replace_core_holdings_via_post():
    # seed existing core holding
    db = next(get_db())
    db.add(CoreHolding(user_id="tony", symbol="OLD", is_core=True))
    db.commit()

    resp = client.post(
        "/portfolio/core_holdings",
        params={"user_id": "tony"},
        json={"symbols": ["TSLA", "OXY", "tsm", "TSLA"]},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 3

    resp2 = client.get("/portfolio/core_holdings", params={"user_id": "tony"})
    syms = sorted(resp2.json()["symbols"])
    assert syms == ["OXY", "TSLA", "TSM"]
