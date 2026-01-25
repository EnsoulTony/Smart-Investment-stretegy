"""Guardrails: 禁止估值/匯率字串滲入帳務層。"""

from pathlib import Path

import pytest


FORBIDDEN_TOKENS = [
    "get_fx_provider",
    ".get_rate(",
    ".convert(",
    "unrealized",
    "market_value",
    "valuation",
    "fx_rate",
    "exchange_rate",
]


def _iter_app_files() -> list[Path]:
    app_dir = Path(__file__).parent.parent / "app"
    if not app_dir.exists():
        return []

    files: list[Path] = []
    for path in app_dir.rglob("*.py"):
        if "app/fx" in str(path.as_posix()):
            continue
        files.append(path)
    return files


def test_no_valuation_or_fx_tokens_in_app():
    files = _iter_app_files()
    if not files:
        pytest.skip("app directory not found")

    violations: list[str] = []
    for path in files:
        content = path.read_text()
        for token in FORBIDDEN_TOKENS:
            if token in content:
                violations.append(f"{path}:{token}")

    assert not violations, (
        "❌ 偵測到估值/匯率相關字串（帳務層禁止）。\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
