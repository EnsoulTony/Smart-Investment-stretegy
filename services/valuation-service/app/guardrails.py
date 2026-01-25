"""Runtime guardrails for valuation-service."""

import os


def enforce_no_db_env() -> None:
    """Reject startup when direct database configuration is detected."""
    forbidden_keys = {
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
    }

    present = [key for key in forbidden_keys if key in os.environ]
    if present:
        present_sorted = ", ".join(sorted(present))
        raise RuntimeError(
            "Direct database configuration is not allowed in valuation-service. "
            "Use portfolio-service API only. "
            f"Detected keys: {present_sorted}"
        )
