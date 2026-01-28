"""Unit tests for news fusion helpers."""

from app.news_fusion import compute_news_score, apply_news_mode_override
from app.strategy_engine.schemas import Mode


def test_compute_news_score_caps_n3() -> None:
    assert compute_news_score(0, 0) == 0.0
    assert compute_news_score(1, 0) == 2.0
    assert compute_news_score(0, 1) == 0.5
    assert compute_news_score(0, 10) == 2.0  # N3 cap


def test_apply_news_mode_override() -> None:
    assert apply_news_mode_override(Mode.RISK_ON, 1) == Mode.RISK_ON
    assert apply_news_mode_override(Mode.RISK_ON, 2) == Mode.TRANSITION
    assert apply_news_mode_override(Mode.TRANSITION, 2) == Mode.RISK_OFF
    assert apply_news_mode_override(Mode.RISK_ON, 3) == Mode.RISK_OFF
