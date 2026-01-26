"""Contract tests for Strategy Engine Input/Output schemas.

Verifies:
- InputSchema validation
- OutputSchema validation
- Schema version stability
"""

import pytest
from pydantic import ValidationError

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
    ActionItem,
    ActionConstraints,
    FalsifiableTrigger,
    Evidence,
)


class TestInputSchemaContract:
    """Input schema contract tests."""

    def test_minimal_valid_input(self) -> None:
        """Minimal valid input should pass validation."""
        input_data = InputSchema(
            schema_version="1.0",
            as_of="2025-01-20",
            user_id="tony",
            base_ccy="TWD",
            positions=[],
            indicators=IndicatorsInput(
                sector_rotation=SectorRotationIndicators(
                    as_of="2025-01-20",
                    version="0.1",
                    source="stub",
                    XLU=SymbolIndicator(close=72.0, ma20=71.5, ma50=71.0),
                    XLK=SymbolIndicator(close=220.0, ma20=218.0, ma50=215.0),
                    ratio=RatioIndicator(
                        pair="XLK/XLU",
                        value=3.055,
                        ma20=3.050,
                        ma50=3.028,
                        slope5=0.002,
                    ),
                ),
            ),
            signals=SignalsInput(news=[], research=[]),
        )

        assert input_data.schema_version == "1.0"
        assert input_data.user_id == "tony"
        assert input_data.base_ccy == "TWD"

    def test_input_with_positions(self) -> None:
        """Input with positions should pass validation."""
        input_data = InputSchema(
            schema_version="1.0",
            as_of="2025-01-20",
            user_id="tony",
            base_ccy="TWD",
            positions=[
                PositionInput(
                    symbol="TSLA",
                    asset_ccy="USD",
                    quantity=10.0,
                    avg_cost=200.0,
                    u_pnl=100.0,
                    realized_pnl=0.0,
                ),
            ],
            indicators=IndicatorsInput(
                sector_rotation=SectorRotationIndicators(
                    as_of="2025-01-20",
                    version="0.1",
                    source="stub",
                    XLU=SymbolIndicator(close=72.0, ma20=71.5, ma50=71.0),
                    XLK=SymbolIndicator(close=220.0, ma20=218.0, ma50=215.0),
                    ratio=RatioIndicator(
                        pair="XLK/XLU",
                        value=3.055,
                        ma20=3.050,
                        ma50=3.028,
                        slope5=0.002,
                    ),
                ),
            ),
        )

        assert len(input_data.positions) == 1
        assert input_data.positions[0].symbol == "TSLA"

    def test_input_requires_indicators(self) -> None:
        """Input without indicators should fail."""
        with pytest.raises(ValidationError):
            InputSchema(
                schema_version="1.0",
                as_of="2025-01-20",
                user_id="tony",
                base_ccy="TWD",
                positions=[],
                # Missing indicators
            )

    def test_input_requires_user_id(self) -> None:
        """Input without user_id should fail."""
        with pytest.raises(ValidationError):
            InputSchema(
                schema_version="1.0",
                as_of="2025-01-20",
                # Missing user_id
                base_ccy="TWD",
                positions=[],
                indicators=IndicatorsInput(
                    sector_rotation=SectorRotationIndicators(
                        as_of="2025-01-20",
                        version="0.1",
                        source="stub",
                        XLU=SymbolIndicator(close=72.0, ma20=71.5, ma50=71.0),
                        XLK=SymbolIndicator(close=220.0, ma20=218.0, ma50=215.0),
                        ratio=RatioIndicator(
                            pair="XLK/XLU",
                            value=3.055,
                            ma20=3.050,
                            ma50=3.028,
                            slope5=0.002,
                        ),
                    ),
                ),
            )


class TestOutputSchemaContract:
    """Output schema contract tests."""

    def test_minimal_valid_output(self) -> None:
        """Minimal valid output should pass validation."""
        output = OutputSchema(
            schema_version="1.0",
            as_of="2025-01-20",
            user_id="tony",
            mode=Mode.TRANSITION,
            decision=Decision.WATCHLIST,
            actions=[],
            evidence=Evidence(
                engine="strategy_engine",
                plugin="v1.4",
                inputs_hash="abc123",
                notes=["test"],
            ),
        )

        assert output.mode == Mode.TRANSITION
        assert output.decision == Decision.WATCHLIST

    def test_output_with_actions(self) -> None:
        """Output with actions should pass validation."""
        output = OutputSchema(
            schema_version="1.0",
            as_of="2025-01-20",
            user_id="tony",
            mode=Mode.RISK_OFF,
            decision=Decision.REDUCE_RISK,
            actions=[
                ActionItem(
                    symbol="TSLA",
                    action=Action.TRIM,
                    reason="REDUCE_RISK: growth_tech exposure > 45%",
                    constraints=ActionConstraints(
                        cooldown_days=5,
                        max_position_pct=0.45,
                    ),
                    falsifiable_triggers=[
                        FalsifiableTrigger(
                            type="indicator",
                            name="XLK/XLU",
                            condition="cross_above_ma50",
                            value=2.9,
                        ),
                    ],
                ),
            ],
            evidence=Evidence(
                engine="strategy_engine",
                plugin="v1.4",
                inputs_hash="abc123",
                notes=[],
            ),
        )

        assert output.mode == Mode.RISK_OFF
        assert len(output.actions) == 1
        assert output.actions[0].action == Action.TRIM
        assert output.actions[0].constraints.cooldown_days == 5
        assert len(output.actions[0].falsifiable_triggers) >= 1

    def test_output_requires_evidence(self) -> None:
        """Output without evidence should fail."""
        with pytest.raises(ValidationError):
            OutputSchema(
                schema_version="1.0",
                as_of="2025-01-20",
                user_id="tony",
                mode=Mode.TRANSITION,
                decision=Decision.WATCHLIST,
                actions=[],
                # Missing evidence
            )

    def test_output_requires_mode(self) -> None:
        """Output without mode should fail."""
        with pytest.raises(ValidationError):
            OutputSchema(
                schema_version="1.0",
                as_of="2025-01-20",
                user_id="tony",
                # Missing mode
                decision=Decision.WATCHLIST,
                actions=[],
                evidence=Evidence(
                    engine="strategy_engine",
                    plugin="v1.4",
                    inputs_hash="abc123",
                    notes=[],
                ),
            )

    def test_evidence_requires_inputs_hash(self) -> None:
        """Evidence without inputs_hash should fail."""
        with pytest.raises(ValidationError):
            Evidence(
                engine="strategy_engine",
                plugin="v1.4",
                # Missing inputs_hash
                notes=[],
            )


class TestModeAndDecisionEnums:
    """Test Mode and Decision enum values."""

    def test_mode_values(self) -> None:
        """Mode enum has expected values."""
        assert Mode.RISK_ON.value == "RISK_ON"
        assert Mode.RISK_OFF.value == "RISK_OFF"
        assert Mode.TRANSITION.value == "TRANSITION"

    def test_decision_values(self) -> None:
        """Decision enum has expected values."""
        assert Decision.NO_ACTION.value == "NO_ACTION"
        assert Decision.REDUCE_RISK.value == "REDUCE_RISK"
        assert Decision.REBALANCE.value == "REBALANCE"
        assert Decision.WATCHLIST.value == "WATCHLIST"

    def test_action_values(self) -> None:
        """Action enum has expected values."""
        assert Action.HOLD.value == "HOLD"
        assert Action.TRIM.value == "TRIM"
        assert Action.ADD.value == "ADD"
        assert Action.AVOID.value == "AVOID"


class TestFalsifiableTrigger:
    """Test FalsifiableTrigger schema."""

    def test_valid_trigger(self) -> None:
        """Valid trigger should pass."""
        trigger = FalsifiableTrigger(
            type="indicator",
            name="XLK/XLU",
            condition="cross_below_ma50",
            value=3.05,
        )

        assert trigger.type == "indicator"
        assert trigger.name == "XLK/XLU"
        assert trigger.condition == "cross_below_ma50"

    def test_trigger_requires_all_fields(self) -> None:
        """Trigger without required fields should fail."""
        with pytest.raises(ValidationError):
            FalsifiableTrigger(
                type="indicator",
                # Missing name, condition, value
            )
