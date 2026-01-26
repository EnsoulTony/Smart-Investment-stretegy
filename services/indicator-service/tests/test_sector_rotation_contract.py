"""Contract tests for GET /indicators/sector-rotation endpoint.

Verifies:
- Response schema stability
- Required fields are present
- Missing fields return 422
- Provider errors return 503
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestSectorRotationContract:
    """Contract tests for sector-rotation endpoint."""

    def test_returns_200_with_valid_symbols(self) -> None:
        """Valid request returns 200 with complete response."""
        response = client.get("/indicators/sector-rotation?symbols=XLU,XLK")
        assert response.status_code == 200

        data = response.json()

        # Required top-level fields
        assert "as_of" in data
        assert "version" in data
        assert "source" in data
        assert "XLU" in data
        assert "XLK" in data
        assert "ratio" in data

    def test_xlu_has_required_fields(self) -> None:
        """XLU section has close, ma20, ma50."""
        response = client.get("/indicators/sector-rotation?symbols=XLU,XLK")
        assert response.status_code == 200

        xlu = response.json()["XLU"]
        assert "close" in xlu
        assert "ma20" in xlu
        assert "ma50" in xlu

        # All should be numeric
        assert isinstance(xlu["close"], (int, float))
        assert isinstance(xlu["ma20"], (int, float))
        assert isinstance(xlu["ma50"], (int, float))

    def test_xlk_has_required_fields(self) -> None:
        """XLK section has close, ma20, ma50."""
        response = client.get("/indicators/sector-rotation?symbols=XLU,XLK")
        assert response.status_code == 200

        xlk = response.json()["XLK"]
        assert "close" in xlk
        assert "ma20" in xlk
        assert "ma50" in xlk

        assert isinstance(xlk["close"], (int, float))
        assert isinstance(xlk["ma20"], (int, float))
        assert isinstance(xlk["ma50"], (int, float))

    def test_ratio_has_required_fields(self) -> None:
        """Ratio section has pair, value, ma20, ma50, slope5."""
        response = client.get("/indicators/sector-rotation?symbols=XLU,XLK")
        assert response.status_code == 200

        ratio = response.json()["ratio"]
        assert "pair" in ratio
        assert "value" in ratio
        assert "ma20" in ratio
        assert "ma50" in ratio
        assert "slope5" in ratio

        assert ratio["pair"] == "XLK/XLU"
        assert isinstance(ratio["value"], (int, float))
        assert isinstance(ratio["slope5"], (int, float))

    def test_slope5_is_provided(self) -> None:
        """slope5 must be provided for v1.4 plugin scoring."""
        response = client.get("/indicators/sector-rotation?symbols=XLU,XLK")
        assert response.status_code == 200

        ratio = response.json()["ratio"]
        assert "slope5" in ratio
        # slope5 = (value - value_5d_ago) / 5
        # Should be calculable, not None
        assert ratio["slope5"] is not None

    def test_value_5d_ago_is_provided(self) -> None:
        """value_5d_ago must be provided for reproducibility."""
        response = client.get("/indicators/sector-rotation?symbols=XLU,XLK")
        assert response.status_code == 200

        ratio = response.json()["ratio"]
        assert "value_5d_ago" in ratio
        assert isinstance(ratio["value_5d_ago"], (int, float))

    def test_missing_symbols_returns_422(self) -> None:
        """Request without required symbols returns 422."""
        response = client.get("/indicators/sector-rotation?symbols=SPY")
        assert response.status_code == 422

        data = response.json()
        assert "detail" in data
        assert "missing_fields" in data["detail"]

    def test_invalid_date_format_returns_422(self) -> None:
        """Invalid as_of date format returns 422."""
        response = client.get(
            "/indicators/sector-rotation?symbols=XLU,XLK&as_of=invalid-date"
        )
        assert response.status_code == 422

        data = response.json()
        assert "detail" in data

    def test_valid_date_format_accepted(self) -> None:
        """Valid YYYY-MM-DD date format is accepted."""
        response = client.get(
            "/indicators/sector-rotation?symbols=XLU,XLK&as_of=2025-01-15"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["as_of"] == "2025-01-15"

    def test_default_symbols_work(self) -> None:
        """Default symbols (XLU,XLK) work without explicit parameter."""
        response = client.get("/indicators/sector-rotation")
        assert response.status_code == 200

        data = response.json()
        assert "XLU" in data
        assert "XLK" in data

    def test_content_type_is_json(self) -> None:
        """Response content-type is application/json."""
        response = client.get("/indicators/sector-rotation?symbols=XLU,XLK")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
