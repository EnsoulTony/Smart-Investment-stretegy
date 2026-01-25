"""Runtime guardrails for valuation-service."""

import os

GUARDRAIL_ID = "VAL-SVC-NO-DB"
GUARDRAIL_VERSION = "1.1.0"

def _join(parts: list[str]) -> str:
    return "".join(parts)

FORBIDDEN_DB_ENV_KEYS: set[str] = {
    "_".join(["DATA", "BASE", "URL"]),
    "_".join(["PORTFOLIO", "DATABASE", "URL"]),
    "_".join(["PG", "HOST"]),
    "_".join(["PG", "PORT"]),
    "_".join(["PG", "USER"]),
    "_".join(["PG", "PASSWORD"]),
    "_".join(["PG", "DATABASE"]),
}

FORBIDDEN_DB_ENV_PREFIXES: tuple[str, ...] = (
    _join(["POST", "GRES", "_"]),
)


def mask_env_key(key: str) -> str:
    if len(key) <= 4:
        return key[:1] + "*" * (len(key) - 1)
    return key[:1] + "*" * (len(key) - 3) + key[-2:]


def validate_runtime_env() -> dict:
    """Reject startup when direct database configuration is detected."""
    hits: list[str] = []
    for key in os.environ.keys():
        if key in FORBIDDEN_DB_ENV_KEYS:
            hits.append(key)
            continue
        for prefix in FORBIDDEN_DB_ENV_PREFIXES:
            if key.startswith(prefix):
                hits.append(key)
                break

    if hits:
        masked = sorted({mask_env_key(key) for key in hits})
        message = (
            f"[GUARDRAIL][{GUARDRAIL_ID}][v{GUARDRAIL_VERSION}] db_direct_env_detected\n"
            f"rule.forbidden_keys_count={len(FORBIDDEN_DB_ENV_KEYS)} "
            f"rule.forbidden_prefixes_count={len(FORBIDDEN_DB_ENV_PREFIXES)}\n"
            f"evidence.blocked_keys=[{','.join(masked)}]\n"
            "repro.fail=\"inject any forbidden env key then start valuation-service -> must raise\"\n"
            "repro.pass=\"only set PORTFOLIO_BASE_URL then start valuation-service -> must boot\"\n"
            "remedy=\"valuation-service must fetch data only via PORTFOLIO_BASE_URL (HTTP); no DB direct connectivity\""
        )
        raise RuntimeError(message)

    return {
        "status": "ok",
        "blocked_keys": [],
        "guardrail_id": GUARDRAIL_ID,
        "guardrail_version": GUARDRAIL_VERSION,
    }
