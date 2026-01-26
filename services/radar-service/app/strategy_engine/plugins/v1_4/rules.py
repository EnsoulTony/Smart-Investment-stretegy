"""v1.4 Rules: Sector rotation scoring and exposure calculation.

This module contains the HARDCODED rules for v1.4 plugin:
- Mode scoring (RISK_ON / RISK_OFF / TRANSITION)
- Factor group classification
- Exposure calculation
- Decision determination

ALL RULES ARE FIXED AND MUST NOT BE CHANGED without version bump.
"""

from typing import Dict, List, Tuple
from enum import Enum

from ...schemas import (
    Mode,
    Decision,
    Action,
    SectorRotationIndicators,
    PositionInput,
)


# =============================================================================
# Factor Groups (HARDCODED - DO NOT CHANGE)
# =============================================================================

FACTOR_GROUPS: Dict[str, List[str]] = {
    "defensive": [
        "XLU", "TLT", "IEF", "00687B", "00953B", "00965",
        "009805", "00983A", "00984A", "00988A"
    ],
    "growth_tech": [
        "TSLA", "TSM", "QQQ", "ARKK", "ARKQ", "0050", "0052", "6789"
    ],
    "energy": [
        "OXY", "XLE", "URA", "CCJ", "MP"
    ],
}

# Position limits per factor group
GROUP_LIMITS: Dict[str, float] = {
    "growth_tech": 0.45,
    "energy": 0.45,
    "defensive": 0.60,
    "other": 0.40,
}


def get_factor_group(symbol: str) -> str:
    """Get factor group for a symbol.

    Args:
        symbol: Stock symbol

    Returns:
        Factor group name ('defensive', 'growth_tech', 'energy', or 'other')
    """
    symbol_upper = symbol.upper()
    for group_name, symbols in FACTOR_GROUPS.items():
        if symbol_upper in [s.upper() for s in symbols]:
            return group_name
    return "other"


# =============================================================================
# Mode Scoring Rules (HARDCODED - DO NOT CHANGE)
# =============================================================================

class ScoreRule(Enum):
    """Scoring rule identifiers."""
    # Risk-on rules (+1 each)
    ON1_RATIO_ABOVE_MA50 = "ON1"
    ON2_RATIO_MA20_ABOVE_MA50 = "ON2"
    ON3_SLOPE5_POSITIVE = "ON3"
    ON4_XLK_ABOVE_MA50 = "ON4"
    ON5_XLU_BELOW_MA50 = "ON5"

    # Risk-off rules (+1 each)
    OFF1_RATIO_BELOW_MA50 = "OFF1"
    OFF2_RATIO_MA20_BELOW_MA50 = "OFF2"
    OFF3_SLOPE5_NEGATIVE = "OFF3"
    OFF4_XLU_ABOVE_MA50 = "OFF4"
    OFF5_XLK_BELOW_MA50 = "OFF5"


def compute_mode_scores(
    indicators: SectorRotationIndicators,
) -> Tuple[int, int, Dict[str, bool]]:
    """Compute risk-on and risk-off scores from indicators.

    Scoring Rules (FIXED):
    - Risk-on (+1 each):
      ON1) ratio.value > ratio.ma50
      ON2) ratio.ma20 > ratio.ma50
      ON3) ratio.slope5 > 0
      ON4) XLK.close > XLK.ma50
      ON5) XLU.close < XLU.ma50

    - Risk-off (+1 each):
      OFF1) ratio.value < ratio.ma50
      OFF2) ratio.ma20 < ratio.ma50
      OFF3) ratio.slope5 < 0
      OFF4) XLU.close > XLU.ma50
      OFF5) XLK.close < XLK.ma50

    Args:
        indicators: Sector rotation indicators

    Returns:
        Tuple of (score_on, score_off, rule_results)
        rule_results is a dict mapping rule code to True/False
    """
    ratio = indicators.ratio
    xlu = indicators.XLU
    xlk = indicators.XLK

    # Evaluate each rule
    rule_results: Dict[str, bool] = {
        # Risk-on rules
        "ON1": ratio.value > ratio.ma50,
        "ON2": ratio.ma20 > ratio.ma50,
        "ON3": ratio.slope5 > 0,
        "ON4": xlk.close > xlk.ma50,
        "ON5": xlu.close < xlu.ma50,
        # Risk-off rules
        "OFF1": ratio.value < ratio.ma50,
        "OFF2": ratio.ma20 < ratio.ma50,
        "OFF3": ratio.slope5 < 0,
        "OFF4": xlu.close > xlu.ma50,
        "OFF5": xlk.close < xlk.ma50,
    }

    # Compute scores
    score_on = sum(1 for key in ["ON1", "ON2", "ON3", "ON4", "ON5"] if rule_results[key])
    score_off = sum(1 for key in ["OFF1", "OFF2", "OFF3", "OFF4", "OFF5"] if rule_results[key])

    return score_on, score_off, rule_results


def determine_mode(score_on: int, score_off: int) -> Mode:
    """Determine market regime mode from scores.

    Rules (FIXED):
    - RISK_ON: score_on >= 4 AND score_on - score_off >= 2
    - RISK_OFF: score_off >= 4 AND score_off - score_on >= 2
    - TRANSITION: otherwise

    Args:
        score_on: Risk-on score (0-5)
        score_off: Risk-off score (0-5)

    Returns:
        Mode enum value
    """
    if score_on >= 4 and (score_on - score_off) >= 2:
        return Mode.RISK_ON
    elif score_off >= 4 and (score_off - score_on) >= 2:
        return Mode.RISK_OFF
    else:
        return Mode.TRANSITION


# =============================================================================
# Exposure Calculation (Count-based approximation)
# =============================================================================

def compute_exposure(positions: List[PositionInput]) -> Dict[str, float]:
    """Compute exposure percentage by factor group.

    Uses position COUNT as proxy (no FX/market price).
    exposure_pct(group) = count(symbols in group) / count(all symbols)

    Args:
        positions: List of positions

    Returns:
        Dict mapping group name to exposure percentage (0.0 - 1.0)
    """
    if not positions:
        return {
            "growth_tech": 0.0,
            "energy": 0.0,
            "defensive": 0.0,
            "other": 0.0,
        }

    total_count = len(positions)
    group_counts: Dict[str, int] = {
        "growth_tech": 0,
        "energy": 0,
        "defensive": 0,
        "other": 0,
    }

    for pos in positions:
        group = get_factor_group(pos.symbol)
        group_counts[group] += 1

    return {
        group: count / total_count
        for group, count in group_counts.items()
    }


# =============================================================================
# Decision Determination
# =============================================================================

def determine_decision(
    mode: Mode,
    exposure: Dict[str, float],
) -> Tuple[Decision, List[str]]:
    """Determine portfolio decision based on mode and exposure.

    Rules (FIXED):
    - TRANSITION -> WATCHLIST
    - RISK_ON:
      - If defensive exposure > 0.60 -> REBALANCE (trim defensive)
      - Otherwise -> NO_ACTION
    - RISK_OFF:
      - If growth_tech exposure > 0.45 -> REDUCE_RISK (trim growth_tech)
      - Otherwise -> NO_ACTION

    Args:
        mode: Market regime mode
        exposure: Exposure by factor group

    Returns:
        Tuple of (Decision, list of trigger reasons)
    """
    triggers: List[str] = []

    if mode == Mode.TRANSITION:
        return Decision.WATCHLIST, ["mode=TRANSITION requires observation"]

    if mode == Mode.RISK_ON:
        if exposure.get("defensive", 0.0) > GROUP_LIMITS["defensive"]:
            triggers.append(
                f"defensive_exposure={exposure['defensive']:.2%} > limit={GROUP_LIMITS['defensive']:.0%}"
            )
            return Decision.REBALANCE, triggers
        return Decision.NO_ACTION, ["mode=RISK_ON with balanced exposure"]

    if mode == Mode.RISK_OFF:
        if exposure.get("growth_tech", 0.0) > GROUP_LIMITS["growth_tech"]:
            triggers.append(
                f"growth_tech_exposure={exposure['growth_tech']:.2%} > limit={GROUP_LIMITS['growth_tech']:.0%}"
            )
            return Decision.REDUCE_RISK, triggers
        return Decision.NO_ACTION, ["mode=RISK_OFF with low growth_tech exposure"]

    # Should never reach here
    return Decision.NO_ACTION, ["unknown_mode"]


def get_positions_to_trim(
    positions: List[PositionInput],
    target_group: str,
    decision: Decision,
) -> List[str]:
    """Get list of symbols to trim in a factor group.

    Args:
        positions: All positions
        target_group: Factor group to trim ('growth_tech' or 'defensive')
        decision: Current decision

    Returns:
        List of symbols to trim (at least 1 if decision requires trim)
    """
    group_positions = [
        pos.symbol for pos in positions
        if get_factor_group(pos.symbol) == target_group
    ]

    if not group_positions:
        return []

    # Return at least 1 symbol to trim
    return group_positions[:1]
