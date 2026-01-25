"""Runtime guard: valuation-service 禁止 DB 連線環境變數。"""

import pytest

from app.guardrails import enforce_no_db_env


FORBIDDEN_KEYS = [
    "DATABASE_URL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "PGDATABASE",
]


def _clear_db_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in FORBIDDEN_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_guard_allows_clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_db_env(monkeypatch)
    enforce_no_db_env()


def test_guard_blocks_db_env_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_db_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "x")

    with pytest.raises(RuntimeError) as exc:
        enforce_no_db_env()

    message = str(exc.value)
    assert "not allowed" in message
    assert "DATABASE_URL" in message
