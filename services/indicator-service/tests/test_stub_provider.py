"""Tests for StubProvider: reproducibility and fixed outputs.

Verifies:
- Stub outputs are deterministic
- All scenarios produce valid data
- slope5 calculation is correct
"""

from datetime import date
import pytest

from app.providers.stub import StubProvider


class TestStubProviderReproducibility:
    """Verify stub provider produces reproducible outputs."""

    def test_default_scenario_is_deterministic(self) -> None:
        """Same scenario produces same output."""
        provider1 = StubProvider(scenario="default")
        provider2 = StubProvider(scenario="default")

        data1 = provider1.get_sector_rotation()
        data2 = provider2.get_sector_rotation()

        # Remove as_of (date-dependent) for comparison
        del data1["as_of"]
        del data2["as_of"]

        assert data1 == data2

    def test_risk_on_scenario_is_deterministic(self) -> None:
        """risk_on scenario produces consistent output."""
        provider = StubProvider(scenario="risk_on")
        data1 = provider.get_sector_rotation()
        data2 = provider.get_sector_rotation()

        del data1["as_of"]
        del data2["as_of"]

        assert data1 == data2

    def test_risk_off_scenario_is_deterministic(self) -> None:
        """risk_off scenario produces consistent output."""
        provider = StubProvider(scenario="risk_off")
        data1 = provider.get_sector_rotation()
        data2 = provider.get_sector_rotation()

        del data1["as_of"]
        del data2["as_of"]

        assert data1 == data2


class TestStubProviderScenarios:
    """Verify each scenario produces valid data for expected mode."""

    def test_default_scenario_has_all_fields(self) -> None:
        """Default scenario has all required fields."""
        provider = StubProvider(scenario="default")
        data = provider.get_sector_rotation()

        # Top-level fields
        assert "as_of" in data
        assert "version" in data
        assert "source" in data
        assert data["source"] == "stub"

        # XLU fields
        assert "XLU" in data
        assert all(k in data["XLU"] for k in ["close", "ma20", "ma50"])

        # XLK fields
        assert "XLK" in data
        assert all(k in data["XLK"] for k in ["close", "ma20", "ma50"])

        # Ratio fields
        assert "ratio" in data
        assert all(k in data["ratio"] for k in ["pair", "value", "ma20", "ma50", "slope5", "value_5d_ago"])

    def test_risk_on_scenario_triggers_risk_on_mode(self) -> None:
        """risk_on scenario should score 5 ON rules.

        Expected:
        - ON1: ratio.value > ratio.ma50 ✓
        - ON2: ratio.ma20 > ratio.ma50 ✓
        - ON3: ratio.slope5 > 0 ✓
        - ON4: XLK.close > XLK.ma50 ✓
        - ON5: XLU.close < XLU.ma50 ✓
        """
        provider = StubProvider(scenario="risk_on")
        data = provider.get_sector_rotation()

        ratio = data["ratio"]
        xlu = data["XLU"]
        xlk = data["XLK"]

        # ON1: ratio.value > ratio.ma50
        assert ratio["value"] > ratio["ma50"], "ON1 should pass"

        # ON2: ratio.ma20 > ratio.ma50
        assert ratio["ma20"] > ratio["ma50"], "ON2 should pass"

        # ON3: ratio.slope5 > 0
        assert ratio["slope5"] > 0, "ON3 should pass"

        # ON4: XLK.close > XLK.ma50
        assert xlk["close"] > xlk["ma50"], "ON4 should pass"

        # ON5: XLU.close < XLU.ma50
        assert xlu["close"] < xlu["ma50"], "ON5 should pass"

    def test_risk_off_scenario_triggers_risk_off_mode(self) -> None:
        """risk_off scenario should score 5 OFF rules.

        Expected:
        - OFF1: ratio.value < ratio.ma50 ✓
        - OFF2: ratio.ma20 < ratio.ma50 ✓
        - OFF3: ratio.slope5 < 0 ✓
        - OFF4: XLU.close > XLU.ma50 ✓
        - OFF5: XLK.close < XLK.ma50 ✓
        """
        provider = StubProvider(scenario="risk_off")
        data = provider.get_sector_rotation()

        ratio = data["ratio"]
        xlu = data["XLU"]
        xlk = data["XLK"]

        # OFF1: ratio.value < ratio.ma50
        assert ratio["value"] < ratio["ma50"], "OFF1 should pass"

        # OFF2: ratio.ma20 < ratio.ma50
        assert ratio["ma20"] < ratio["ma50"], "OFF2 should pass"

        # OFF3: ratio.slope5 < 0
        assert ratio["slope5"] < 0, "OFF3 should pass"

        # OFF4: XLU.close > XLU.ma50
        assert xlu["close"] > xlu["ma50"], "OFF4 should pass"

        # OFF5: XLK.close < XLK.ma50
        assert xlk["close"] < xlk["ma50"], "OFF5 should pass"


class TestSlope5Calculation:
    """Verify slope5 is calculated correctly."""

    def test_slope5_formula(self) -> None:
        """slope5 = (value - value_5d_ago) / 5"""
        provider = StubProvider(scenario="default")
        data = provider.get_sector_rotation()

        ratio = data["ratio"]
        expected_slope5 = (ratio["value"] - ratio["value_5d_ago"]) / 5.0

        assert abs(ratio["slope5"] - expected_slope5) < 0.0001

    def test_slope5_positive_for_risk_on(self) -> None:
        """risk_on scenario has positive slope5."""
        provider = StubProvider(scenario="risk_on")
        data = provider.get_sector_rotation()

        assert data["ratio"]["slope5"] > 0

    def test_slope5_negative_for_risk_off(self) -> None:
        """risk_off scenario has negative slope5."""
        provider = StubProvider(scenario="risk_off")
        data = provider.get_sector_rotation()

        assert data["ratio"]["slope5"] < 0


class TestStubProviderConfiguration:
    """Test provider configuration options."""

    def test_unknown_scenario_raises_error(self) -> None:
        """Unknown scenario raises ValueError."""
        with pytest.raises(ValueError, match="Unknown scenario"):
            StubProvider(scenario="invalid_scenario")

    def test_available_scenarios_returns_list(self) -> None:
        """available_scenarios returns list of valid scenarios."""
        scenarios = StubProvider.available_scenarios()
        assert isinstance(scenarios, list)
        assert "default" in scenarios
        assert "risk_on" in scenarios
        assert "risk_off" in scenarios

    def test_custom_as_of_date(self) -> None:
        """Custom as_of date is reflected in output."""
        provider = StubProvider()
        custom_date = date(2025, 6, 15)
        data = provider.get_sector_rotation(as_of=custom_date)

        assert data["as_of"] == "2025-06-15"
