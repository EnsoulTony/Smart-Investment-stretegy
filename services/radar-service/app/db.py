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


def insert_trigger_evaluations(
    *,
    user_id: str,
    as_of: date | str,
    plugin: str,
    decision_inputs_hash: str,
    evaluations: Iterable[dict],
) -> None:
    """Insert trigger evaluations (idempotent)."""
    if engine.dialect.name == "sqlite":
        return
    rows = []
    for evaluation in evaluations:
        rows.append(
            {
                "user_id": user_id,
                "as_of": as_of.isoformat() if isinstance(as_of, date) else as_of,
                "plugin": plugin,
                "decision_inputs_hash": decision_inputs_hash,
                "trigger_key": evaluation.get("trigger_key"),
                "trigger_type": evaluation.get("trigger_type"),
                "condition": json.dumps(evaluation.get("condition"), ensure_ascii=False),
                "observed_value": json.dumps(evaluation.get("observed_value"), ensure_ascii=False),
                "is_triggered": bool(evaluation.get("is_triggered")),
            }
        )

    if not rows:
        return

    sql = text(
        """
        INSERT INTO trigger_evaluations
          (user_id, as_of, plugin, decision_inputs_hash, trigger_key, trigger_type,
           condition, observed_value, is_triggered)
        VALUES
          (:user_id, :as_of, :plugin, :decision_inputs_hash, :trigger_key, :trigger_type,
           :condition, :observed_value, :is_triggered)
        ON CONFLICT ON CONSTRAINT uq_trigger_eval_identity DO NOTHING
        """
    )

    with engine.begin() as conn:
        conn.execute(sql, rows)


def fetch_trigger_history(
    *,
    user_id: str,
    plugin: str,
    from_date: date,
    to_date: date,
    trigger_type: str | None,
    is_triggered: bool | None,
    limit: int,
    offset: int,
) -> list[dict]:
    """Fetch trigger evaluations for history endpoint."""
    clauses = [
        "user_id = :user_id",
        "plugin = :plugin",
        "as_of BETWEEN :from_date AND :to_date",
    ]
    params: dict[str, Any] = {
        "user_id": user_id,
        "plugin": plugin,
        "from_date": from_date,
        "to_date": to_date,
        "limit": limit,
        "offset": offset,
    }

    if trigger_type is not None:
        clauses.append("trigger_type = :trigger_type")
        params["trigger_type"] = trigger_type
    if is_triggered is not None:
        clauses.append("is_triggered = :is_triggered")
        params["is_triggered"] = is_triggered

    where_sql = " AND ".join(clauses)
    sql = text(
        f"""
        SELECT as_of,
               decision_inputs_hash,
               trigger_key,
               trigger_type,
               is_triggered,
               observed_value,
               evaluated_at
        FROM trigger_evaluations
        WHERE {where_sql}
        ORDER BY evaluated_at DESC, trigger_key ASC
        LIMIT :limit OFFSET :offset
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [dict(row) for row in rows]
