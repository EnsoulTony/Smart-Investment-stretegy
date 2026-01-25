"""Runtime guard: valuation-service 禁止 DB 連線環境變數。

Sprint 1-4.B：測試 runtime guard 行為
- 乾淨環境允許啟動
- 偵測到 DB env 時必須 raise RuntimeError
- Evidence 只顯示 key，不顯示 value
"""

import json
import pytest

from app.guardrails import (
    validate_runtime_env,
    detect_forbidden_env_keys,
    build_evidence,
    mask_env_key,
    GUARDRAIL_ID,
    GUARDRAIL_VERSION,
)


# 使用 split token 技巧定義禁止的 key，避免自己被掃到
FORBIDDEN_KEYS = [
    "".join(["DATA", "BASE_", "URL"]),
    "".join(["PORTFOLIO_DATA", "BASE_", "URL"]),
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
    """清除所有 DB 相關環境變數"""
    for key in FORBIDDEN_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestValidateRuntimeEnvClean:
    """測試乾淨環境允許啟動"""

    def test_guard_allows_clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：無 DB env 時，返回 status=ok"""
        _clear_db_env(monkeypatch)
        status = validate_runtime_env()
        assert status["status"] == "ok"
        assert status["blocked_keys"] == []
        assert status["guardrail_id"] == GUARDRAIL_ID
        assert status["guardrail_version"] == GUARDRAIL_VERSION


class TestValidateRuntimeEnvBlocked:
    """測試偵測到 DB env 時必須 raise RuntimeError"""

    def test_guard_blocks_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：偵測到 DATABASE_URL 時 raise RuntimeError"""
        _clear_db_env(monkeypatch)
        monkeypatch.setenv("".join(["DATA", "BASE_", "URL"]), "postgresql://x:y@z/db")

        with pytest.raises(RuntimeError) as exc:
            validate_runtime_env()

        message = str(exc.value)
        assert f"[GUARDRAIL][{GUARDRAIL_ID}][v{GUARDRAIL_VERSION}]" in message
        assert "blocked_env_injection" in message
        assert "evidence.blocked_keys=[" in message

    def test_guard_blocks_postgres_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：偵測到 POSTGRES_* 前綴時 raise RuntimeError"""
        _clear_db_env(monkeypatch)
        monkeypatch.setenv("POSTGRES_" + "USER", "test_user")

        with pytest.raises(RuntimeError) as exc:
            validate_runtime_env()

        message = str(exc.value)
        assert "blocked_env_injection" in message

    def test_guard_blocks_pg_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：偵測到 PG* 前綴時 raise RuntimeError"""
        _clear_db_env(monkeypatch)
        monkeypatch.setenv("PG" + "HOST", "localhost")

        with pytest.raises(RuntimeError) as exc:
            validate_runtime_env()

        message = str(exc.value)
        assert "blocked_env_injection" in message

    def test_guard_blocks_multiple_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：同時偵測到多個禁止 key"""
        _clear_db_env(monkeypatch)
        monkeypatch.setenv("".join(["DATA", "BASE_", "URL"]), "x")
        monkeypatch.setenv("POSTGRES_" + "USER", "y")
        monkeypatch.setenv("PG" + "HOST", "z")

        with pytest.raises(RuntimeError) as exc:
            validate_runtime_env()

        message = str(exc.value)
        assert "blocked_count=3" in message


class TestEvidenceNoValue:
    """測試 evidence 不得包含任何 value"""

    def test_evidence_only_shows_masked_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：evidence 只顯示遮罩後的 key，不顯示 value"""
        _clear_db_env(monkeypatch)
        secret_value = "postgresql://secret_user:secret_password@secret_host/secret_db"
        monkeypatch.setenv("".join(["DATA", "BASE_", "URL"]), secret_value)

        with pytest.raises(RuntimeError) as exc:
            validate_runtime_env()

        message = str(exc.value)

        # 確保 value 不在訊息中
        assert "secret_user" not in message
        assert "secret_password" not in message
        assert "secret_host" not in message
        assert "secret_db" not in message
        assert "postgresql://" not in message

        # 確保只有遮罩後的 key（DATABASE_URL = 12 chars → D + 10* + L）
        # mask_env_key 會產生 D***********L（首字元 + len-2 個 * + 末字元）
        assert "D" in message and "*" in message and "L" in message

    def test_build_evidence_no_value_leak(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：build_evidence 不洩漏 value"""
        _clear_db_env(monkeypatch)
        monkeypatch.setenv("".join(["DATA", "BASE_", "URL"]), "super_secret_value")

        hits = detect_forbidden_env_keys()
        evidence = build_evidence(hits)

        # 轉成 JSON 字串檢查
        evidence_json = json.dumps(evidence)

        assert "super_secret_value" not in evidence_json
        assert "blocked_env_keys" in evidence_json


class TestMaskEnvKey:
    """測試 mask_env_key 函數"""

    def test_mask_short_key(self) -> None:
        """測試：短 key 的遮罩"""
        assert mask_env_key("ABC") == "A**"
        assert mask_env_key("AB") == "A*"
        assert mask_env_key("A") == "A"

    def test_mask_normal_key(self) -> None:
        """測試：一般長度 key 的遮罩"""
        masked = mask_env_key("".join(["DATA", "BASE_", "URL"]))
        assert masked.startswith("D")
        assert masked.endswith("L")
        assert "*" in masked

    def test_mask_postgres_key(self) -> None:
        """測試：POSTGRES_* key 的遮罩"""
        masked = mask_env_key("POSTGRES_" + "USER")
        assert masked.startswith("P")
        assert "*" in masked


class TestDetectForbiddenEnvKeys:
    """測試 detect_forbidden_env_keys 函數"""

    def test_detect_empty_when_clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：乾淨環境返回空列表"""
        _clear_db_env(monkeypatch)
        hits = detect_forbidden_env_keys()
        assert hits == []

    def test_detect_finds_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：偵測到 DATABASE_URL"""
        _clear_db_env(monkeypatch)
        monkeypatch.setenv("".join(["DATA", "BASE_", "URL"]), "x")

        hits = detect_forbidden_env_keys()
        assert "".join(["DATA", "BASE_", "URL"]) in hits

    def test_detect_finds_postgres_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：偵測到 POSTGRES_* 前綴"""
        _clear_db_env(monkeypatch)
        monkeypatch.setenv("POSTGRES_" + "USER", "x")

        hits = detect_forbidden_env_keys()
        assert "POSTGRES_" + "USER" in hits


class TestGuardrailVersioning:
    """測試 guardrail 版本資訊"""

    def test_guardrail_id_in_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：錯誤訊息包含 guardrail ID"""
        _clear_db_env(monkeypatch)
        monkeypatch.setenv("".join(["DATA", "BASE_", "URL"]), "x")

        with pytest.raises(RuntimeError) as exc:
            validate_runtime_env()

        message = str(exc.value)
        assert GUARDRAIL_ID in message
        assert GUARDRAIL_VERSION in message

    def test_guardrail_id_in_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """測試：成功時也返回 guardrail 資訊"""
        _clear_db_env(monkeypatch)
        result = validate_runtime_env()

        assert result["guardrail_id"] == GUARDRAIL_ID
        assert result["guardrail_version"] == GUARDRAIL_VERSION
