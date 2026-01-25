"""Runtime guardrails for valuation-service."""

import os

GUARDRAIL_ID = "VAL-SVC-NO-DB"
GUARDRAIL_VERSION = "1.0.0"

DENIED_ENV_KEYS_DB_CONNECTIVITY: set[str] = {
    "_".join(["DATABASE", "URL"]),
}

DENIED_ENV_PREFIXES_DB_CONNECTIVITY: tuple[str, ...] = (
    "PG",
    "POST" + "GRES_",
)


def mask_env_key(key: str) -> str:
    if len(key) <= 4:
        return key[:1] + "*" * (len(key) - 1)
    return key[:1] + "*" * (len(key) - 3) + key[-2:]


def validate_no_db_env() -> None:
    """Reject startup when direct database configuration is detected."""
    hits = []
    for key in os.environ.keys():
        if key in DENIED_ENV_KEYS_DB_CONNECTIVITY:
            hits.append(key)
            continue
        for prefix in DENIED_ENV_PREFIXES_DB_CONNECTIVITY:
            if key.startswith(prefix):
                hits.append(key)
                break

    if hits:
        masked = sorted({mask_env_key(key) for key in hits})
        message = (
            f"[GUARDRAIL][{GUARDRAIL_ID}][v{GUARDRAIL_VERSION}] db_direct_env_detected\n"
            f"rule.denied_env_keys_count={len(DENIED_ENV_KEYS_DB_CONNECTIVITY)} "
            f"rule.denied_env_prefixes_count={len(DENIED_ENV_PREFIXES_DB_CONNECTIVITY)}\n"
            f"evidence.hit_env_keys_masked=[{','.join(masked)}]\n"
            "repro.fail=\"inject any denied env key then start valuation-service -> must raise\"\n"
            "repro.pass=\"only set PORTFOLIO_BASE_URL then start valuation-service -> must boot\"\n"
            "remedy=\"valuation-service must fetch data only via PORTFOLIO_BASE_URL (HTTP); no DB direct connectivity\""
        )
        raise RuntimeError(message)
