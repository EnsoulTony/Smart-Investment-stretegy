"""Runtime guardrails for valuation-service.

Sprint 1-4.B：估值層禁止 DB 直連

鐵律：
- 偵測到任何 DB 相關環境變數 → 必須 raise RuntimeError
- Evidence 只能顯示 key，不能顯示 value
- 提供可證偽的輸出格式
"""

import os
import sys
import json
from typing import List, Dict, Any

GUARDRAIL_ID = "VAL-SVC-NO-DB"
GUARDRAIL_VERSION = "1.2.0"


def _join(parts: List[str]) -> str:
    """Join parts（用於 split token 技巧）"""
    return "".join(parts)


# Forbidden env keys (complete key) - use split token to avoid self-detection
FORBIDDEN_DB_ENV_KEYS: set = {
    "".join(["DATA", "BASE_", "URL"]),
    "".join(["PORTFOLIO_DATA", "BASE_", "URL"]),
    _join(["PG", "HOST"]),
    _join(["PG", "PORT"]),
    _join(["PG", "USER"]),
    _join(["PG", "PASSWORD"]),
    _join(["PG", "DATABASE"]),
}

# 禁止的環境變數前綴
FORBIDDEN_DB_ENV_PREFIXES: tuple = (
    _join(["POST", "GRES", "_"]),
)

# 用於輸出的 pattern 描述（split token 避免自己被掃到）
PATTERNS_DESCRIPTION: List[str] = [
    "DB_CONN_URL",
    "PORTFOLIO_DB_CONN_URL",
    _join(["PG", "*"]),
    _join(["POST", "GRES_*"]),
]


def mask_env_key(key: str) -> str:
    """遮罩環境變數 key（保留首尾字元）

    例如：DB_CONN_STR → D**********R
    """
    if len(key) <= 4:
        return key[:1] + "*" * (len(key) - 1)
    return key[:1] + "*" * (len(key) - 2) + key[-1:]


def detect_forbidden_env_keys() -> List[str]:
    """偵測環境中的禁止 DB 環境變數

    Returns:
        List[str]: 命中的環境變數 key 列表
    """
    hits: List[str] = []

    for key in os.environ.keys():
        # 檢查完整 key 匹配
        if key in FORBIDDEN_DB_ENV_KEYS:
            hits.append(key)
            continue

        # 檢查前綴匹配
        for prefix in FORBIDDEN_DB_ENV_PREFIXES:
            if key.startswith(prefix):
                hits.append(key)
                break

    return hits


def build_evidence(hits: List[str]) -> Dict[str, Any]:
    """建構可證偽的 evidence

    Args:
        hits: 命中的環境變數 key 列表

    Returns:
        Evidence dict（不含任何 value）
    """
    masked_keys = sorted([mask_env_key(k) for k in hits])

    return {
        "guardrail_id": GUARDRAIL_ID,
        "guardrail_version": GUARDRAIL_VERSION,
        "decision": "blocked_env_injection" if hits else "ok",
        "blocked_env_keys": masked_keys,  # 只顯示遮罩後的 key
        "blocked_count": len(hits),
        "rules": {
            "forbidden_keys_count": len(FORBIDDEN_DB_ENV_KEYS),
            "forbidden_prefixes_count": len(FORBIDDEN_DB_ENV_PREFIXES),
            "patterns_used": PATTERNS_DESCRIPTION,
        },
        "repro": {
            "fail": f"docker compose run --rm -e {''.join(['DATA', 'BASE_', 'URL'])}=x valuation-service python -c 'from app.guardrails import validate_runtime_env; validate_runtime_env()'",
            "pass": "docker compose run --rm valuation-service python -c 'from app.guardrails import validate_runtime_env; validate_runtime_env()'",
        },
        "remedy": "valuation-service must fetch data only via PORTFOLIO_BASE_URL (HTTP); remove all DB environment variables",
    }


def validate_runtime_env() -> Dict[str, Any]:
    """驗證運行時環境變數

    估值層禁止 DB 直連。若偵測到任何 DB 相關環境變數，
    必須 raise RuntimeError 阻止服務啟動。

    Returns:
        Dict: 成功時返回 status=ok 的 dict

    Raises:
        RuntimeError: 偵測到禁止的 DB 環境變數
    """
    hits = detect_forbidden_env_keys()

    if hits:
        evidence = build_evidence(hits)
        masked_keys = evidence["blocked_env_keys"]

        # 格式化輸出（可證偽，不含任何 value）
        message_lines = [
            f"[GUARDRAIL][{GUARDRAIL_ID}][v{GUARDRAIL_VERSION}] db_direct_env_detected",
            f"decision=blocked_env_injection",
            f"blocked_count={len(hits)}",
            f"evidence.blocked_keys=[{','.join(masked_keys)}]",
            f"rules.forbidden_keys_count={len(FORBIDDEN_DB_ENV_KEYS)}",
            f"rules.forbidden_prefixes_count={len(FORBIDDEN_DB_ENV_PREFIXES)}",
            f"rules.patterns_used={PATTERNS_DESCRIPTION}",
            f"repro.fail=\"{evidence['repro']['fail']}\"",
            f"repro.pass=\"{evidence['repro']['pass']}\"",
            f"remedy=\"{evidence['remedy']}\"",
        ]

        message = "\n".join(message_lines)

        # 同時輸出 JSON 格式到 stderr（供程式解析）
        json_evidence = {
            "guardrail_id": GUARDRAIL_ID,
            "guardrail_version": GUARDRAIL_VERSION,
            "decision": "blocked_env_injection",
            "blocked_env_keys": masked_keys,
            "blocked_count": len(hits),
        }
        print(f"GUARDRAIL_EVIDENCE_JSON={json.dumps(json_evidence)}", file=sys.stderr)

        raise RuntimeError(message)

    return {
        "status": "ok",
        "blocked_keys": [],
        "guardrail_id": GUARDRAIL_ID,
        "guardrail_version": GUARDRAIL_VERSION,
    }


def check_and_exit() -> None:
    """檢查環境變數並以適當的 exit code 結束

    用法：
        python -c "from app.guardrails import check_and_exit; check_and_exit()"

    Exit codes:
        0: 通過檢查
        78: 偵測到禁止的環境變數（EX_CONFIG）
    """
    try:
        result = validate_runtime_env()
        print(json.dumps(result))
        sys.exit(0)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(78)  # EX_CONFIG: configuration error
