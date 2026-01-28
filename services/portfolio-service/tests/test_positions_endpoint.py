"""positions API 端點測試（只讀帳務）。"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import get_db, engine
from app.main import app
from app.models import Base, Position

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_positions_endpoint_success():
    db = next(get_db())

    db.add_all(
        [
            Position(
                user_id="tony",
                symbol="TSLA",
                asset_ccy="USD",
                quantity=Decimal("100"),
                avg_cost=Decimal("250.00"),
                realized_pnl=Decimal("1500.00"),
                u_pnl=Decimal("0")
            ),
            Position(
                user_id="tony",
                symbol="NVDA",
                asset_ccy="USD",
                quantity=Decimal("50"),
                avg_cost=Decimal("500.00"),
                realized_pnl=Decimal("3000.00"),
                u_pnl=Decimal("0")
            ),
        ]
    )
    db.commit()
    db.close()

    response = client.get("/portfolio/positions?user_id=tony")
    assert response.status_code == 200

    data = response.json()
    assert data["user_id"] == "tony"
    assert data["asof"] is None
    assert data["next_cursor"] is None
    assert len(data["items"]) == 2

    items_by_symbol = {item["symbol"]: item for item in data["items"]}
    assert set(items_by_symbol.keys()) == {"TSLA", "NVDA"}
    first = items_by_symbol["TSLA"]
    assert first["asset_ccy"] == "USD"
    assert first["quantity"] == "100"
    assert first["avg_cost"] == "250.00"
    assert first["realized_pnl"] == "1500.00"
    assert first["cost_basis"] == "25000.00"


def test_positions_endpoint_empty_user_id():
    response = client.get("/portfolio/positions?user_id=")
    assert response.status_code == 422


def test_positions_endpoint_user_not_found():
    response = client.get("/portfolio/positions?user_id=missing")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "missing"
    assert data["items"] == []
    assert data["next_cursor"] is None
