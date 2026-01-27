"""Sprint 3 news signals contract tests."""

from fastapi.testclient import TestClient

from app.main import app
import app.signals as signals

client = TestClient(app)


def test_signals_contract_and_distribution(monkeypatch) -> None:
    monkeypatch.setattr(signals, "fetch_core_holdings", lambda user_id: ["TSLA", "OXY", "CCJ", "TSM", "URA"])
    response = client.get(
        "/news/signals",
        params={"user_id": "tony", "as_of": "2026-01-27"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["schema_version"]
    assert payload["as_of"] == "2026-01-27"
    assert payload["source"] == "stub"
    assert isinstance(payload["items"], list)
    assert len(payload["items"]) >= 5

    tiers = [item["tier"] for item in payload["items"]]
    assert tiers.count("N1") >= 2
    assert tiers.count("N3") >= 3

    for item in payload["items"]:
        assert item["id"]
        assert item["tier"] in {"N1", "N3"}
        assert item["title"]
        assert item["published_at"]
        assert item["summary_zh"]
        assert isinstance(item["symbols"], list)
        assert isinstance(item["factor_groups"], list)
        assert isinstance(item["themes"], list)
        assert isinstance(item["falsifiable_triggers"], list)
        assert len(item["falsifiable_triggers"]) >= 1
        assert item["confidence"] is not None

        for trigger in item["falsifiable_triggers"]:
            assert trigger["type"]
            assert trigger["name"]
            assert trigger["condition"]
            assert trigger["value"] is not None


def test_signals_deterministic(monkeypatch) -> None:
    monkeypatch.setattr(signals, "fetch_core_holdings", lambda user_id: ["TSLA", "OXY", "CCJ", "TSM", "URA"])
    params = {"user_id": "tony", "as_of": "2026-01-27"}
    first = client.get("/news/signals", params=params).json()
    second = client.get("/news/signals", params=params).json()
    assert first == second
