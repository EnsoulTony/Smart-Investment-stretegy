"""News fusion helpers for radar-service."""

from __future__ import annotations

from typing import Iterable

from .strategy_engine.schemas import ActionItem, Action, ActionConstraints, FalsifiableTrigger, Mode


def compute_news_score(n1_count: int, n3_count: int) -> float:
    """Compute risk_off score impact from news tiers."""
    n1_score = n1_count * 2.0
    n3_score = min(2.0, n3_count * 0.5)
    return n1_score + n3_score


def apply_news_mode_override(mode: Mode, n1_count: int) -> Mode:
    """Apply mode override rules based on N1 count."""
    if n1_count >= 3:
        return Mode.RISK_OFF
    if n1_count >= 2:
        if mode == Mode.RISK_ON:
            return Mode.TRANSITION
        if mode == Mode.TRANSITION:
            return Mode.RISK_OFF
    return mode


def build_triggers(raw_triggers: Iterable[dict]) -> list[FalsifiableTrigger]:
    """Convert raw trigger dicts to FalsifiableTrigger list with dedup."""
    result: list[FalsifiableTrigger] = []
    seen = set()
    for trigger in raw_triggers:
        key = (
            trigger.get("type"),
            trigger.get("name"),
            trigger.get("condition"),
            trigger.get("value"),
        )
        if key in seen:
            continue
        seen.add(key)
        value = trigger.get("value", 0)
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        result.append(
            FalsifiableTrigger(
                type=str(trigger.get("type") or "news"),
                name=str(trigger.get("name") or "news"),
                condition=str(trigger.get("condition") or "unknown"),
                value=value,
            )
        )
    return result


def attach_news_triggers(
    actions: list[ActionItem],
    n1_triggers: list[FalsifiableTrigger],
    n3_triggers: list[FalsifiableTrigger],
) -> tuple[list[ActionItem], list[FalsifiableTrigger]]:
    """Attach N1 triggers to primary action, return N3 triggers for watchlist."""
    if n1_triggers:
        if actions:
            actions[0].falsifiable_triggers.extend(n1_triggers)
        else:
            actions.append(
                ActionItem(
                    symbol="NEWS",
                    action=Action.HOLD,
                    reason="新聞風險（N1）觸發條件",
                    constraints=ActionConstraints(),
                    falsifiable_triggers=list(n1_triggers),
                )
            )
    return actions, n3_triggers
