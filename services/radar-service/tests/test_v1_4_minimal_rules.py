"""Tests for v1.4 plugin rules with fixed indicator scenarios.

Test cases per specification:
- Case A (Strong Risk-on): ON full → RISK_ON
- Case B (Strong Risk-off): OFF full → RISK_OFF
- Case C (Transition): score_on=3 score_off=3 → TRANSITION
"""

import pytest

from app.strategy_engine.schemas import (
    InputSchema,
    OutputSchema,
    PositionInput,
    IndicatorsInput,
    SectorRotationIndicators,
    SymbolIndicator,
    RatioIndicator,
    SignalsInput,
    Mode,
    Decision,
    Action,
)
from app.strategy_engine.plugins.v1_4.plugin import V1_4Plugin
from app.strategy_engine.plugins.v1_4.rules import (
    compute_mode_scores,
    determine_mode,
    compute_exposure,
    determine_decision,
    get_factor_group,
    FACTOR_GROUPS,
    GROUP_LIMITS,
)


# =============================================================================
# Test Fixtures: Fixed indicator scenarios
# =============================================================================

def make_risk_on_indicators() -> SectorRotationIndicators:
    """Strong RISK_ON scenario (all 5 ON rules pass).

    ON1) ratio.value > ratio.ma50 ✓
    ON2) ratio.ma20 > ratio.ma50 ✓
    ON3) ratio.slope5 > 0 ✓
    ON4) XLK.close > XLK.ma50 ✓
    ON5) XLU.close < XLU.ma50 ✓
    """
    return SectorRotationIndicators(
        as_of="2025-01-20",
        version="0.1",
        source="stub",
        XLU=SymbolIndicator(close=68.0, ma20=69.0, ma50=70.0),  # XLU < ma50
        XLK=SymbolIndicator(close=230.0, ma20=225.0, ma50=220.0),  # XLK > ma50
        ratio=RatioIndicator(
            pair="XLK/XLU",
            value=3.382,   # > ma50
            ma20=3.300,    # > ma50
            ma50=3.100,
            slope5=0.036,  # > 0
        ),
    )


def make_risk_off_indicators() -> SectorRotationIndicators:
    """Strong RISK_OFF scenario (all 5 OFF rules pass).

    OFF1) ratio.value < ratio.ma50 ✓
    OFF2) ratio.ma20 < ratio.ma50 ✓
    OFF3) ratio.slope5 < 0 ✓
    OFF4) XLU.close > XLU.ma50 ✓
    OFF5) XLK.close < XLK.ma50 ✓
    """
    return SectorRotationIndicators(
        as_of="2025-01-20",
        version="0.1",
        source="stub",
        XLU=SymbolIndicator(close=75.0, ma20=74.0, ma50=73.0),  # XLU > ma50
        XLK=SymbolIndicator(close=200.0, ma20=205.0, ma50=210.0),  # XLK < ma50
        ratio=RatioIndicator(
            pair="XLK/XLU",
            value=2.667,   # < ma50
            ma20=2.750,    # < ma50
            ma50=2.900,
            slope5=-0.0266,  # < 0
        ),
    )


def make_transition_indicators() -> SectorRotationIndicators:
    """TRANSITION scenario (balanced scores, neither dominates).

    score_on ~= 3, score_off ~= 2-3, diff < 2 or on < 4
    """
    return SectorRotationIndicators(
        as_of="2025-01-20",
        version="0.1",
        source="stub",
        XLU=SymbolIndicator(close=72.0, ma20=71.5, ma50=71.0),  # XLU > ma50: OFF4
        XLK=SymbolIndicator(close=220.0, ma20=218.0, ma50=215.0),  # XLK > ma50: ON4
        ratio=RatioIndicator(
            pair="XLK/XLU",
            value=3.055,   # > ma50: ON1
            ma20=3.050,    # > ma50: ON2
            ma50=3.028,
            slope5=0.002,  # > 0: ON3
        ),
        # ON: ON1, ON2, ON3, ON4 = 4 but diff = 4-1 = 3 >= 2, so this would be RISK_ON
        # Let me adjust to make it TRANSITION
    )


def make_transition_indicators_v2() -> SectorRotationIndicators:
    """TRANSITION scenario v2 (score_on=3, score_off=2, diff=1 < 2).

    ON: ratio.value > ma50 (ON1), slope5 > 0 (ON3), XLK > ma50 (ON4) = 3
    OFF: XLU > ma50 (OFF4) = 1
    But on < 4, so TRANSITION
    """
    return SectorRotationIndicators(
        as_of="2025-01-20",
        version="0.1",
        source="stub",
        XLU=SymbolIndicator(close=72.0, ma20=71.5, ma50=71.0),  # XLU > ma50: OFF4
        XLK=SymbolIndicator(close=220.0, ma20=218.0, ma50=215.0),  # XLK > ma50: ON4
        ratio=RatioIndicator(
            pair="XLK/XLU",
            value=3.055,   # > ma50: ON1
            ma20=3.020,    # < ma50: OFF2 (not ON2)
            ma50=3.028,
            slope5=0.002,  # > 0: ON3
        ),
        # ON: ON1=T, ON2=F, ON3=T, ON4=T, ON5=F -> 3
        # OFF: OFF1=F, OFF2=T, OFF3=F, OFF4=T, OFF5=F -> 2
        # diff = 1 < 2, on=3 < 4 -> TRANSITION
    )


# =============================================================================
# Test: Mode Scoring Rules
# =============================================================================

class TestModeScoringRules:
    """Test mode scoring logic."""

    def test_risk_on_scores_5_on_rules(self) -> None:
        """RISK_ON indicators should score 5 ON rules."""
        indicators = make_risk_on_indicators()
        score_on, score_off, rules = compute_mode_scores(indicators)

        assert score_on == 5, f"Expected score_on=5, got {score_on}, rules={rules}"
        assert score_off == 0, f"Expected score_off=0, got {score_off}"

    def test_risk_off_scores_5_off_rules(self) -> None:
        """RISK_OFF indicators should score 5 OFF rules."""
        indicators = make_risk_off_indicators()
        score_on, score_off, rules = compute_mode_scores(indicators)

        assert score_on == 0, f"Expected score_on=0, got {score_on}"
        assert score_off == 5, f"Expected score_off=5, got {score_off}, rules={rules}"

    def test_transition_scores_balanced(self) -> None:
        """TRANSITION indicators should have balanced/low scores."""
        indicators = make_transition_indicators_v2()
        score_on, score_off, rules = compute_mode_scores(indicators)

        # Should not qualify for either RISK_ON or RISK_OFF
        is_risk_on = score_on >= 4 and (score_on - score_off) >= 2
        is_risk_off = score_off >= 4 and (score_off - score_on) >= 2

        assert not is_risk_on, f"Should not be RISK_ON: on={score_on}, off={score_off}"
        assert not is_risk_off, f"Should not be RISK_OFF: on={score_on}, off={score_off}"


class TestModeDetection:
    """Test mode determination logic."""

    def test_risk_on_detection(self) -> None:
        """score_on >= 4 AND diff >= 2 → RISK_ON."""
        mode = determine_mode(score_on=5, score_off=0)
        assert mode == Mode.RISK_ON

        mode = determine_mode(score_on=4, score_off=2)
        assert mode == Mode.RISK_ON

    def test_risk_off_detection(self) -> None:
        """score_off >= 4 AND diff >= 2 → RISK_OFF."""
        mode = determine_mode(score_on=0, score_off=5)
        assert mode == Mode.RISK_OFF

        mode = determine_mode(score_on=2, score_off=4)
        assert mode == Mode.RISK_OFF

    def test_transition_when_scores_close(self) -> None:
        """diff < 2 → TRANSITION."""
        mode = determine_mode(score_on=4, score_off=3)
        assert mode == Mode.TRANSITION  # diff = 1 < 2

        mode = determine_mode(score_on=3, score_off=3)
        assert mode == Mode.TRANSITION  # diff = 0

    def test_transition_when_on_below_threshold(self) -> None:
        """score_on < 4 → TRANSITION (even if diff >= 2)."""
        mode = determine_mode(score_on=3, score_off=0)
        assert mode == Mode.TRANSITION  # on < 4


# =============================================================================
# Test: Factor Groups
# =============================================================================

class TestFactorGroups:
    """Test factor group classification."""

    def test_growth_tech_symbols(self) -> None:
        """growth_tech symbols are classified correctly."""
        for symbol in ["TSLA", "TSM", "QQQ", "ARKK", "ARKQ", "0050"]:
            assert get_factor_group(symbol) == "growth_tech"

    def test_defensive_symbols(self) -> None:
        """defensive symbols are classified correctly."""
        for symbol in ["XLU", "TLT", "IEF", "00687B"]:
            assert get_factor_group(symbol) == "defensive"

    def test_energy_symbols(self) -> None:
        """energy symbols are classified correctly."""
        for symbol in ["OXY", "XLE", "URA", "CCJ", "MP"]:
            assert get_factor_group(symbol) == "energy"

    def test_unknown_symbols_are_other(self) -> None:
        """Unknown symbols are classified as 'other'."""
        assert get_factor_group("UNKNOWN") == "other"
        assert get_factor_group("AAPL") == "other"

    def test_group_limits(self) -> None:
        """Group limits are as specified."""
        assert GROUP_LIMITS["growth_tech"] == 0.45
        assert GROUP_LIMITS["energy"] == 0.45
        assert GROUP_LIMITS["defensive"] == 0.60
        assert GROUP_LIMITS["other"] == 0.40


# =============================================================================
# Test: Exposure Calculation
# =============================================================================

class TestExposureCalculation:
    """Test exposure calculation (count-based)."""

    def test_empty_positions_zero_exposure(self) -> None:
        """Empty positions should have zero exposure."""
        exposure = compute_exposure([])

        assert exposure["growth_tech"] == 0.0
        assert exposure["defensive"] == 0.0
        assert exposure["energy"] == 0.0
        assert exposure["other"] == 0.0

    def test_single_group_full_exposure(self) -> None:
        """Single group positions should have 100% exposure."""
        positions = [
            PositionInput(symbol="TSLA", asset_ccy="USD", quantity=10, avg_cost=200, u_pnl=0, realized_pnl=0),
            PositionInput(symbol="QQQ", asset_ccy="USD", quantity=5, avg_cost=400, u_pnl=0, realized_pnl=0),
        ]

        exposure = compute_exposure(positions)

        assert exposure["growth_tech"] == 1.0
        assert exposure["defensive"] == 0.0

    def test_mixed_positions_proportional_exposure(self) -> None:
        """Mixed positions should have proportional exposure."""
        positions = [
            PositionInput(symbol="TSLA", asset_ccy="USD", quantity=10, avg_cost=200, u_pnl=0, realized_pnl=0),
            PositionInput(symbol="XLU", asset_ccy="USD", quantity=100, avg_cost=70, u_pnl=0, realized_pnl=0),
        ]

        exposure = compute_exposure(positions)

        assert exposure["growth_tech"] == 0.5
        assert exposure["defensive"] == 0.5


# =============================================================================
# Test: Decision Determination
# =============================================================================

class TestDecisionDetermination:
    """Test decision determination logic."""

    def test_transition_returns_watchlist(self) -> None:
        """TRANSITION mode → WATCHLIST decision."""
        decision, _ = determine_decision(
            mode=Mode.TRANSITION,
            exposure={"growth_tech": 0.3, "defensive": 0.3, "energy": 0.2, "other": 0.2},
        )

        assert decision == Decision.WATCHLIST

    def test_risk_on_no_action_when_balanced(self) -> None:
        """RISK_ON + balanced exposure → NO_ACTION."""
        decision, _ = determine_decision(
            mode=Mode.RISK_ON,
            exposure={"growth_tech": 0.3, "defensive": 0.3, "energy": 0.2, "other": 0.2},
        )

        assert decision == Decision.NO_ACTION

    def test_risk_on_rebalance_when_defensive_over_limit(self) -> None:
        """RISK_ON + defensive > 60% → REBALANCE."""
        decision, _ = determine_decision(
            mode=Mode.RISK_ON,
            exposure={"growth_tech": 0.2, "defensive": 0.65, "energy": 0.1, "other": 0.05},
        )

        assert decision == Decision.REBALANCE

    def test_risk_off_reduce_risk_when_growth_tech_over_limit(self) -> None:
        """RISK_OFF + growth_tech > 45% → REDUCE_RISK."""
        decision, _ = determine_decision(
            mode=Mode.RISK_OFF,
            exposure={"growth_tech": 0.50, "defensive": 0.2, "energy": 0.2, "other": 0.1},
        )

        assert decision == Decision.REDUCE_RISK

    def test_risk_off_no_action_when_low_growth_tech(self) -> None:
        """RISK_OFF + low growth_tech → NO_ACTION."""
        decision, _ = determine_decision(
            mode=Mode.RISK_OFF,
            exposure={"growth_tech": 0.20, "defensive": 0.4, "energy": 0.2, "other": 0.2},
        )

        assert decision == Decision.NO_ACTION


# =============================================================================
# Test: Full Plugin Execution (Case A, B, C)
# =============================================================================

class TestV14PluginExecution:
    """Integration tests for v1.4 plugin execution."""

    def test_case_a_strong_risk_on(self) -> None:
        """Case A: Strong Risk-on → RISK_ON, NO_ACTION or REBALANCE."""
        plugin = V1_4Plugin()

        input_data = InputSchema(
            schema_version="1.0",
            as_of="2025-01-20",
            user_id="tony",
            base_ccy="TWD",
            positions=[
                PositionInput(symbol="TSLA", asset_ccy="USD", quantity=10, avg_cost=200, u_pnl=0, realized_pnl=0),
                PositionInput(symbol="QQQ", asset_ccy="USD", quantity=5, avg_cost=400, u_pnl=0, realized_pnl=0),
            ],
            indicators=IndicatorsInput(sector_rotation=make_risk_on_indicators()),
        )

        output = plugin.execute(input_data)

        assert output.mode == Mode.RISK_ON
        assert output.decision in [Decision.NO_ACTION, Decision.REBALANCE]

    def test_case_b_strong_risk_off(self) -> None:
        """Case B: Strong Risk-off → RISK_OFF, REDUCE_RISK if growth_tech over limit."""
        plugin = V1_4Plugin()

        # Growth tech > 45% (2 out of 3 = 66%)
        input_data = InputSchema(
            schema_version="1.0",
            as_of="2025-01-20",
            user_id="tony",
            base_ccy="TWD",
            positions=[
                PositionInput(symbol="TSLA", asset_ccy="USD", quantity=10, avg_cost=200, u_pnl=0, realized_pnl=0),
                PositionInput(symbol="QQQ", asset_ccy="USD", quantity=5, avg_cost=400, u_pnl=0, realized_pnl=0),
                PositionInput(symbol="AAPL", asset_ccy="USD", quantity=20, avg_cost=150, u_pnl=0, realized_pnl=0),
            ],
            indicators=IndicatorsInput(sector_rotation=make_risk_off_indicators()),
        )

        output = plugin.execute(input_data)

        assert output.mode == Mode.RISK_OFF
        assert output.decision == Decision.REDUCE_RISK

    def test_case_c_transition(self) -> None:
        """Case C: Transition → TRANSITION, WATCHLIST."""
        plugin = V1_4Plugin()

        input_data = InputSchema(
            schema_version="1.0",
            as_of="2025-01-20",
            user_id="tony",
            base_ccy="TWD",
            positions=[
                PositionInput(symbol="TSLA", asset_ccy="USD", quantity=10, avg_cost=200, u_pnl=0, realized_pnl=0),
            ],
            indicators=IndicatorsInput(sector_rotation=make_transition_indicators_v2()),
        )

        output = plugin.execute(input_data)

        assert output.mode == Mode.TRANSITION
        assert output.decision == Decision.WATCHLIST

    def test_output_contains_evidence_inputs_hash(self) -> None:
        """Output must contain evidence.inputs_hash."""
        plugin = V1_4Plugin()

        input_data = InputSchema(
            schema_version="1.0",
            as_of="2025-01-20",
            user_id="tony",
            base_ccy="TWD",
            positions=[],
            indicators=IndicatorsInput(sector_rotation=make_risk_on_indicators()),
        )

        output = plugin.execute(input_data)

        assert output.evidence.inputs_hash is not None
        assert len(output.evidence.inputs_hash) == 64  # SHA256 hex

    def test_output_contains_falsifiable_triggers(self) -> None:
        """Output actions must contain at least 1 falsifiable trigger."""
        plugin = V1_4Plugin()

        input_data = InputSchema(
            schema_version="1.0",
            as_of="2025-01-20",
            user_id="tony",
            base_ccy="TWD",
            positions=[
                PositionInput(symbol="TSLA", asset_ccy="USD", quantity=10, avg_cost=200, u_pnl=0, realized_pnl=0),
            ],
            indicators=IndicatorsInput(sector_rotation=make_risk_off_indicators()),
        )

        output = plugin.execute(input_data)

        # At least one action with triggers
        if output.actions:
            for action in output.actions:
                assert len(action.falsifiable_triggers) >= 1, \
                    f"Action {action.symbol} has no falsifiable triggers"

    def test_output_cooldown_is_5(self) -> None:
        """All actions should have cooldown_days=5."""
        plugin = V1_4Plugin()

        input_data = InputSchema(
            schema_version="1.0",
            as_of="2025-01-20",
            user_id="tony",
            base_ccy="TWD",
            positions=[
                PositionInput(symbol="TSLA", asset_ccy="USD", quantity=10, avg_cost=200, u_pnl=0, realized_pnl=0),
            ],
            indicators=IndicatorsInput(sector_rotation=make_risk_on_indicators()),
        )

        output = plugin.execute(input_data)

        for action in output.actions:
            assert action.constraints.cooldown_days == 5

    def test_output_scoring_detail_in_evidence(self) -> None:
        """Evidence should contain scoring_detail."""
        plugin = V1_4Plugin()

        input_data = InputSchema(
            schema_version="1.0",
            as_of="2025-01-20",
            user_id="tony",
            base_ccy="TWD",
            positions=[],
            indicators=IndicatorsInput(sector_rotation=make_risk_on_indicators()),
        )

        output = plugin.execute(input_data)

        assert output.evidence.scoring_detail is not None
        assert "score_on" in output.evidence.scoring_detail
        assert "score_off" in output.evidence.scoring_detail
        assert "rules" in output.evidence.scoring_detail
