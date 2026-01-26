"""v1.4 Plugin: EDS (Economic Direction Signal) Minimum Viable Implementation.

Based on XLU/XLK sector rotation indicators with scoring-based mode detection.
All outputs are falsifiable with explicit triggers and cooldown.
"""

from typing import Optional, List

from ...schemas import (
    InputSchema,
    OutputSchema,
    MissingDataError,
    Mode,
    Decision,
    Action,
    ActionItem,
    ActionConstraints,
    FalsifiableTrigger,
    Evidence,
)
from ...engine import StrategyPlugin, canonical_json_hash

from .rules import (
    compute_mode_scores,
    determine_mode,
    compute_exposure,
    determine_decision,
    get_factor_group,
    get_positions_to_trim,
    GROUP_LIMITS,
)


class V1_4Plugin(StrategyPlugin):
    """v1.4 Strategy Plugin: EDS Minimum Viable.

    Features:
    - Scoring-based mode detection (RISK_ON / RISK_OFF / TRANSITION)
    - Count-based exposure calculation (no FX/market price needed)
    - Falsifiable triggers for all recommendations
    - Fixed 5-day cooldown for all actions
    """

    @property
    def plugin_name(self) -> str:
        return "v1.4"

    @property
    def plugin_version(self) -> str:
        return "1.4.0"

    def validate_input(self, input_data: InputSchema) -> Optional[MissingDataError]:
        """Validate that required indicator data is present.

        Required fields for v1.4:
        - indicators.sector_rotation.XLU (close, ma20, ma50)
        - indicators.sector_rotation.XLK (close, ma20, ma50)
        - indicators.sector_rotation.ratio (value, ma20, ma50, slope5)
        """
        missing_fields: List[str] = []

        # Check sector_rotation exists
        if not hasattr(input_data, "indicators") or input_data.indicators is None:
            missing_fields.append("indicators")
            return MissingDataError(
                status="missing_data",
                missing_fields=missing_fields,
                message="indicators block is required",
            )

        sr = input_data.indicators.sector_rotation
        if sr is None:
            missing_fields.append("indicators.sector_rotation")
            return MissingDataError(
                status="missing_data",
                missing_fields=missing_fields,
                message="indicators.sector_rotation is required",
            )

        # Check XLU
        if sr.XLU is None:
            missing_fields.append("indicators.sector_rotation.XLU")
        else:
            for field in ["close", "ma20", "ma50"]:
                if getattr(sr.XLU, field, None) is None:
                    missing_fields.append(f"indicators.sector_rotation.XLU.{field}")

        # Check XLK
        if sr.XLK is None:
            missing_fields.append("indicators.sector_rotation.XLK")
        else:
            for field in ["close", "ma20", "ma50"]:
                if getattr(sr.XLK, field, None) is None:
                    missing_fields.append(f"indicators.sector_rotation.XLK.{field}")

        # Check ratio
        if sr.ratio is None:
            missing_fields.append("indicators.sector_rotation.ratio")
        else:
            for field in ["value", "ma20", "ma50", "slope5"]:
                if getattr(sr.ratio, field, None) is None:
                    missing_fields.append(f"indicators.sector_rotation.ratio.{field}")

        if missing_fields:
            return MissingDataError(
                status="missing_data",
                missing_fields=missing_fields,
                message=f"Missing required indicator fields: {', '.join(missing_fields)}",
            )

        return None

    def execute(self, input_data: InputSchema) -> OutputSchema:
        """Execute v1.4 strategy logic.

        Steps:
        1. Compute mode scores from indicators
        2. Determine mode (RISK_ON / RISK_OFF / TRANSITION)
        3. Compute exposure by factor group
        4. Determine decision (NO_ACTION / REDUCE_RISK / REBALANCE / WATCHLIST)
        5. Generate per-position actions with falsifiable triggers
        6. Build evidence block with inputs_hash

        Args:
            input_data: Validated InputSchema

        Returns:
            OutputSchema with complete decision and evidence
        """
        # Step 1: Compute mode scores
        indicators = input_data.indicators.sector_rotation
        score_on, score_off, rule_results = compute_mode_scores(indicators)

        # Step 2: Determine mode
        mode = determine_mode(score_on, score_off)

        # Step 3: Compute exposure
        exposure = compute_exposure(input_data.positions)

        # Step 4: Determine decision
        decision, decision_reasons = determine_decision(mode, exposure)

        # Step 5: Generate actions
        actions = self._generate_actions(
            positions=input_data.positions,
            mode=mode,
            decision=decision,
            exposure=exposure,
            indicators=indicators,
        )

        # Step 6: Build evidence
        inputs_hash = canonical_json_hash(input_data.model_dump())
        evidence = Evidence(
            engine="strategy_engine",
            plugin=self.plugin_name,
            inputs_hash=inputs_hash,
            notes=decision_reasons,
            scoring_detail={
                "score_on": score_on,
                "score_off": score_off,
                "rules": rule_results,
                "exposure": exposure,
            },
        )

        return OutputSchema(
            schema_version="1.0",
            as_of=input_data.as_of,
            user_id=input_data.user_id,
            mode=mode,
            decision=decision,
            actions=actions,
            evidence=evidence,
        )

    def _generate_actions(
        self,
        positions: list,
        mode: Mode,
        decision: Decision,
        exposure: dict,
        indicators,
    ) -> List[ActionItem]:
        """Generate per-position action recommendations.

        Rules:
        - REDUCE_RISK + growth_tech over limit -> TRIM growth_tech (at least 1)
        - REBALANCE + defensive over limit -> TRIM defensive (at least 1)
        - WATCHLIST -> actions can be empty but triggers must exist
        - All other positions -> HOLD

        Args:
            positions: Current positions
            mode: Market mode
            decision: Portfolio decision
            exposure: Exposure by group
            indicators: Sector rotation indicators

        Returns:
            List of ActionItem with falsifiable triggers
        """
        actions: List[ActionItem] = []

        # Build base triggers (apply to all actions)
        base_triggers = self._build_falsifiable_triggers(mode, indicators)

        # Determine which positions to trim
        trim_symbols: set = set()
        trim_reason = ""

        if decision == Decision.REDUCE_RISK:
            # Trim growth_tech
            to_trim = get_positions_to_trim(positions, "growth_tech", decision)
            trim_symbols.update(to_trim)
            trim_reason = f"REDUCE_RISK: growth_tech exposure {exposure.get('growth_tech', 0):.1%} > {GROUP_LIMITS['growth_tech']:.0%}"

        elif decision == Decision.REBALANCE:
            # Trim defensive
            to_trim = get_positions_to_trim(positions, "defensive", decision)
            trim_symbols.update(to_trim)
            trim_reason = f"REBALANCE: defensive exposure {exposure.get('defensive', 0):.1%} > {GROUP_LIMITS['defensive']:.0%}"

        # Generate action for each position
        for pos in positions:
            symbol = pos.symbol
            group = get_factor_group(symbol)
            max_pct = GROUP_LIMITS.get(group, GROUP_LIMITS["other"])

            if symbol in trim_symbols:
                action = ActionItem(
                    symbol=symbol,
                    action=Action.TRIM,
                    reason=trim_reason,
                    constraints=ActionConstraints(
                        cooldown_days=5,
                        max_position_pct=max_pct,
                    ),
                    falsifiable_triggers=base_triggers,
                )
            else:
                # Default to HOLD
                hold_reason = self._get_hold_reason(mode, decision, group)
                action = ActionItem(
                    symbol=symbol,
                    action=Action.HOLD,
                    reason=hold_reason,
                    constraints=ActionConstraints(
                        cooldown_days=5,
                        max_position_pct=max_pct,
                    ),
                    falsifiable_triggers=base_triggers,
                )

            actions.append(action)

        # For WATCHLIST with no positions, still return triggers in evidence
        # Actions can be empty but the output will have triggers in evidence

        return actions

    def _build_falsifiable_triggers(
        self, mode: Mode, indicators
    ) -> List[FalsifiableTrigger]:
        """Build falsifiable trigger conditions.

        Required triggers (at least 2):
        T1: XLK/XLU ratio cross_below_ma50 or cross_above_ma50 (depends on mode)
        T2: ratio.slope5 sign_flip (>0 becomes <0 or vice versa)

        Args:
            mode: Current mode
            indicators: Sector rotation indicators

        Returns:
            List of at least 2 FalsifiableTrigger
        """
        ratio = indicators.ratio
        triggers: List[FalsifiableTrigger] = []

        # T1: Ratio cross MA50 trigger
        if mode == Mode.RISK_ON:
            triggers.append(FalsifiableTrigger(
                type="indicator",
                name="XLK/XLU",
                condition="cross_below_ma50",
                value=ratio.ma50,
            ))
        elif mode == Mode.RISK_OFF:
            triggers.append(FalsifiableTrigger(
                type="indicator",
                name="XLK/XLU",
                condition="cross_above_ma50",
                value=ratio.ma50,
            ))
        else:  # TRANSITION
            # Could go either way
            triggers.append(FalsifiableTrigger(
                type="indicator",
                name="XLK/XLU",
                condition="cross_ma50_either_direction",
                value=ratio.ma50,
            ))

        # T2: Slope sign flip trigger
        if ratio.slope5 > 0:
            triggers.append(FalsifiableTrigger(
                type="indicator",
                name="ratio.slope5",
                condition="sign_flip_to_negative",
                value=ratio.slope5,
            ))
        elif ratio.slope5 < 0:
            triggers.append(FalsifiableTrigger(
                type="indicator",
                name="ratio.slope5",
                condition="sign_flip_to_positive",
                value=ratio.slope5,
            ))
        else:
            # slope5 == 0, any change triggers
            triggers.append(FalsifiableTrigger(
                type="indicator",
                name="ratio.slope5",
                condition="any_change",
                value=ratio.slope5,
            ))

        return triggers

    def _get_hold_reason(self, mode: Mode, decision: Decision, group: str) -> str:
        """Get reason string for HOLD action.

        Args:
            mode: Current mode
            decision: Portfolio decision
            group: Position's factor group

        Returns:
            Concise reason string
        """
        if decision == Decision.NO_ACTION:
            return f"mode={mode.value}, exposure within limits"
        elif decision == Decision.WATCHLIST:
            return f"mode=TRANSITION, monitoring {group} positions"
        elif decision == Decision.REDUCE_RISK:
            if group != "growth_tech":
                return f"not in growth_tech group, maintain position"
            return f"REDUCE_RISK active but position retained"
        elif decision == Decision.REBALANCE:
            if group != "defensive":
                return f"not in defensive group, maintain position"
            return f"REBALANCE active but position retained"

        return f"mode={mode.value}, hold"
