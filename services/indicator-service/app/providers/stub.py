"""Stub Provider: Fixed indicator values for testing and offline CI.

All values are DETERMINISTIC and REPRODUCIBLE.
This provider is the DEFAULT for CI environments.
"""

from datetime import date
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class IndicatorSet:
    """Indicator values for a single symbol."""
    close: float
    ma20: float
    ma50: float


@dataclass
class RatioSet:
    """Ratio indicator values."""
    value: float
    ma20: float
    ma50: float
    value_5d_ago: float

    @property
    def slope5(self) -> float:
        """5-day slope: (value - value_5d_ago) / 5"""
        return (self.value - self.value_5d_ago) / 5.0


class StubProvider:
    """Stub indicator provider with fixed values.

    Provides three scenarios for testing:
    - Default: TRANSITION mode (balanced scores)
    - risk_on: Strong RISK_ON mode (all ON rules pass)
    - risk_off: Strong RISK_OFF mode (all OFF rules pass)

    Usage:
        provider = StubProvider()
        data = provider.get_sector_rotation()  # default scenario

        provider = StubProvider(scenario="risk_on")
        data = provider.get_sector_rotation()  # RISK_ON scenario
    """

    VERSION = "0.1"
    SOURCE = "stub"

    # ==========================================================================
    # Scenario configurations (FIXED VALUES - DO NOT CHANGE)
    # ==========================================================================

    # Default scenario: TRANSITION mode
    # score_on = 3, score_off = 3 (or close)
    SCENARIOS: Dict[str, Dict[str, Any]] = {
        "default": {
            "xlu": IndicatorSet(close=72.0, ma20=71.5, ma50=71.0),
            "xlk": IndicatorSet(close=220.0, ma20=218.0, ma50=215.0),
            "ratio": RatioSet(
                value=3.055,  # 220/72 ≈ 3.055
                ma20=3.050,
                ma50=3.028,   # value > ma50: ON1 pass
                value_5d_ago=3.045,  # slope5 = 0.002 > 0: ON3 pass
            ),
            # ON: ratio.value > ma50 (ON1), slope5 > 0 (ON3), XLK > ma50 (ON4) = 3
            # OFF: XLU > ma50 (OFF4) = 1
            # score_on=3, score_off=1 -> diff=2, but on<4 -> TRANSITION
        },
        # Strong RISK_ON: all 5 ON rules pass
        # ON1) ratio.value > ratio.ma50 ✓
        # ON2) ratio.ma20 > ratio.ma50 ✓
        # ON3) ratio.slope5 > 0 ✓
        # ON4) XLK.close > XLK.ma50 ✓
        # ON5) XLU.close < XLU.ma50 ✓
        "risk_on": {
            "xlu": IndicatorSet(close=68.0, ma20=69.0, ma50=70.0),  # XLU < ma50: ON5
            "xlk": IndicatorSet(close=230.0, ma20=225.0, ma50=220.0),  # XLK > ma50: ON4
            "ratio": RatioSet(
                value=3.382,   # 230/68 ≈ 3.38, > ma50: ON1
                ma20=3.300,    # > ma50: ON2
                ma50=3.100,
                value_5d_ago=3.200,  # slope5 = 0.036 > 0: ON3
            ),
            # score_on=5, score_off=0 -> RISK_ON
        },
        # Strong RISK_OFF: all 5 OFF rules pass
        # OFF1) ratio.value < ratio.ma50 ✓
        # OFF2) ratio.ma20 < ratio.ma50 ✓
        # OFF3) ratio.slope5 < 0 ✓
        # OFF4) XLU.close > XLU.ma50 ✓
        # OFF5) XLK.close < XLK.ma50 ✓
        "risk_off": {
            "xlu": IndicatorSet(close=75.0, ma20=74.0, ma50=73.0),  # XLU > ma50: OFF4
            "xlk": IndicatorSet(close=200.0, ma20=205.0, ma50=210.0),  # XLK < ma50: OFF5
            "ratio": RatioSet(
                value=2.667,   # 200/75 ≈ 2.67, < ma50: OFF1
                ma20=2.750,    # < ma50: OFF2
                ma50=2.900,
                value_5d_ago=2.800,  # slope5 = -0.0266 < 0: OFF3
            ),
            # score_on=0, score_off=5 -> RISK_OFF
        },
    }

    def __init__(self, scenario: str = "default"):
        """Initialize stub provider with scenario.

        Args:
            scenario: One of "default", "risk_on", "risk_off"
        """
        if scenario not in self.SCENARIOS:
            raise ValueError(
                f"Unknown scenario: {scenario}. "
                f"Available: {list(self.SCENARIOS.keys())}"
            )
        self.scenario = scenario
        self._data = self.SCENARIOS[scenario]

    def get_sector_rotation(self, as_of: date | None = None) -> Dict[str, Any]:
        """Get sector rotation indicators.

        Args:
            as_of: Date for indicators (default: today)

        Returns:
            Dict with XLU, XLK, and ratio indicators
        """
        as_of = as_of or date.today()

        xlu = self._data["xlu"]
        xlk = self._data["xlk"]
        ratio = self._data["ratio"]

        return {
            "as_of": as_of.isoformat(),
            "version": self.VERSION,
            "source": self.SOURCE,
            "XLU": {
                "close": xlu.close,
                "ma20": xlu.ma20,
                "ma50": xlu.ma50,
            },
            "XLK": {
                "close": xlk.close,
                "ma20": xlk.ma20,
                "ma50": xlk.ma50,
            },
            "ratio": {
                "pair": "XLK/XLU",
                "value": ratio.value,
                "ma20": ratio.ma20,
                "ma50": ratio.ma50,
                "slope5": ratio.slope5,
                "value_5d_ago": ratio.value_5d_ago,
            },
        }

    @classmethod
    def available_scenarios(cls) -> list[str]:
        """List available test scenarios."""
        return list(cls.SCENARIOS.keys())
