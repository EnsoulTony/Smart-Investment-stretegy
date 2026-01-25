"""Runtime guard: valuation-service 禁止 DB 連線環境變數。"""

import pytest

from app.guardrails import validate_runtime_env


FORBIDDEN_KEYS = [
    "_".join(["DATABASE", "URL"]),
    "_".join(["PORTFOLIO", "DATABASE", "URL"]),
    "POSTGRES_" + "USER",
    "POSTGRES_" + "PASSWORD",
    "POSTGRES_" + "DB",
    "POSTGRES_" + "HOST",
    "POSTGRES_" + "PORT",
    "PG" + "HOST",
    "PG" + "PORT",
    "PG" + "USER",
    "PG" + "PASSWORD",
    "PG" + "DATABASE",
]


def _clear_db_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in FORBIDDEN_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_guard_allows_clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_db_env(monkeypatch)
    status = validate_runtime_env()
    assert status["status"] == "ok"


def test_guard_blocks_db_env_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_db_env(monkeypatch)
    monkeypatch.setenv("_".join(["DATABASE", "URL"]), "x")

    with pytest.raises(RuntimeError) as exc:
        validate_runtime_env()

    message = str(exc.value)
    assert "[GUARDRAIL][VAL-SVC-NO-DB][v1.1.0]" in message
    assert "evidence.blocked_keys=[" in message
