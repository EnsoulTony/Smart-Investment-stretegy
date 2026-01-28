"""DB helpers for radar-service (news_signals + decision_snapshots)."""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, Iterable

from sqlalchemy import create_engine, text

from .strategy_engine.engine import canonical_json_hash

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://investment:investment@postgres:5432/investment_db",
)

engine = create_engine(DATABASE_URL)


def _coerce_payload(payload: Any) -> dict:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_signal(row: dict) -> dict:
    payload = _coerce_payload(row.get("payload"))
    signal_id = row.get("item_id") or f"news_signal:{row.get('id')}"
    tier = row.get("tier") or payload.get("tier") or "N3"
    return {
        "signal_id": signal_id,
        "tier": tier,
        "payload": payload,
        "signal_hash": canonical_json_hash(payload),
    }


def fetch_news_signals(user_id: str, as_of: date) -> list[dict]:
    """Fetch news_signals rows for a user/date."""
    query = text(
        """
        SELECT id, item_id, tier, payload
        FROM public.news_signals
        WHERE user_id = :user_id AND as_of = :as_of
        ORDER BY weight DESC, published_at DESC NULLS LAST
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(query, {"user_id": user_id, "as_of": as_of}).mappings().all()
    return [_normalize_signal(dict(row)) for row in rows]


def upsert_decision_snapshot(
    *,
    user_id: str,
    as_of: date | str,
    plugin: str,
    mode: str,
    decision: str,
    inputs_hash: str,
    payload: dict,
) -> None:
    """Insert or update decision snapshot (idempotent)."""
    sql = text(
        """
        INSERT INTO decision_snapshots
          (user_id, as_of, plugin, mode, decision, inputs_hash, payload)
        VALUES
          (:user_id, :as_of, :plugin, :mode, :decision, :inputs_hash, :payload)
        ON CONFLICT (user_id, as_of, plugin)
        DO UPDATE SET
          mode = EXCLUDED.mode,
          decision = EXCLUDED.decision,
          inputs_hash = EXCLUDED.inputs_hash,
          payload = EXCLUDED.payload,
          updated_at = CURRENT_TIMESTAMP
        """
    )
    if isinstance(as_of, date):
        as_of_value = as_of.isoformat()
    else:
        as_of_value = as_of

    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "user_id": user_id,
                "as_of": as_of_value,
                "plugin": plugin,
                "mode": mode,
                "decision": decision,
                "inputs_hash": inputs_hash,
                "payload": json.dumps(payload, ensure_ascii=False),
            },
        )


def fetch_decision_history(user_id: str, limit: int = 30) -> list[dict]:
    query = text(
        """
        SELECT as_of, mode, decision, inputs_hash, created_at
        FROM decision_snapshots
        WHERE user_id = :user_id
        ORDER BY as_of DESC, created_at DESC
        LIMIT :limit
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(query, {"user_id": user_id, "limit": limit}).mappings().all()
    return [dict(row) for row in rows]


def build_news_inputs(signals: Iterable[dict]) -> list[dict]:
    """Build minimal news signals for InputSchema hashing."""
    items = []
    for signal in signals:
        items.append(
            {
                "id": signal.get("signal_id"),
                "tier": signal.get("tier"),
                "hash": signal.get("signal_hash"),
            }
        )
    return sorted(items, key=lambda x: x.get("hash") or "")
