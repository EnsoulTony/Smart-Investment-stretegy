"""Guardrails: valuation-service 禁止 DB 直連。"""

from pathlib import Path

import pytest


FORBIDDEN_TOKENS = [
    "sqlalchemy",
    "psycopg2",
    "asyncpg",
    "postgresql://",
    "create_engine",
    "Session(",
]

FORBIDDEN_PATTERNS = [
    "import sqlalchemy",
    "from sqlalchemy",
    "from sqlalchemy.orm import Session",
    "from sqlalchemy import Session",
]


def test_no_db_access_in_app_code():
    """掃描 app/*.py，禁止任何 DB 直連關鍵字。"""
    app_dir = Path(__file__).parent.parent / "app"
    if not app_dir.exists():
        pytest.skip("app directory not found")

    violations: list[str] = []

    for py_file in app_dir.rglob("*.py"):
        with open(py_file, "r") as f:
            for line_no, line in enumerate(f, 1):
                lowered = line.lower()

                for token in FORBIDDEN_TOKENS:
                    if token in lowered:
                        violations.append(f"{py_file.name}:{line_no} - {token}")

                for pattern in FORBIDDEN_PATTERNS:
                    if pattern in line:
                        violations.append(f"{py_file.name}:{line_no} - {pattern}")

    assert not violations, (
        "❌ valuation-service 禁止 DB 直連（僅能透過 portfolio-service API）。\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
