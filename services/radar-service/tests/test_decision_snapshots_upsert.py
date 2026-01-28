"""Tests for decision_snapshots upsert idempotency."""

from datetime import date

from sqlalchemy import create_engine, text

import app.db as db


def _setup_sqlite() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE decision_snapshots (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT NOT NULL,
                  as_of TEXT NOT NULL,
                  plugin TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  decision TEXT NOT NULL,
                  inputs_hash TEXT NOT NULL,
                  payload TEXT NOT NULL,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
                  UNIQUE(user_id, as_of, plugin)
                )
                """
            )
        )
    db.engine = engine


def test_upsert_is_idempotent() -> None:
    _setup_sqlite()
    as_of = date.fromisoformat("2026-01-28")

    db.upsert_decision_snapshot(
        user_id="tony",
        as_of=as_of,
        plugin="v1.4",
        mode="RISK_ON",
        decision="NO_ACTION",
        inputs_hash="hash1",
        payload={"decision": "NO_ACTION"},
    )
    db.upsert_decision_snapshot(
        user_id="tony",
        as_of=as_of,
        plugin="v1.4",
        mode="RISK_OFF",
        decision="REDUCE_RISK",
        inputs_hash="hash2",
        payload={"decision": "REDUCE_RISK"},
    )

    with db.engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM decision_snapshots WHERE user_id='tony'")
        ).scalar_one()
        decision = conn.execute(
            text(
                """
                SELECT decision FROM decision_snapshots
                WHERE user_id='tony' AND as_of='2026-01-28' AND plugin='v1.4'
                """
            )
        ).scalar_one()

    assert count == 1
    assert decision == "REDUCE_RISK"
