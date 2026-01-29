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


def _normalize_analytics_rows(rows: list[dict]) -> list[dict]:
    normalized = []
    for row in rows:
        item = dict(row)
        total = int(item.get("total") or 0)
        wins = int(item.get("wins") or 0)
        losses = int(item.get("losses") or 0)
        neutral = int(item.get("neutral") or 0)
        unknown = int(item.get("unknown") or 0)
        if "triggered" in item:
            item["triggered"] = int(item.get("triggered") or 0)
        item["total"] = total
        item["wins"] = wins
        item["losses"] = losses
        item["neutral"] = neutral
        item["unknown"] = unknown
        item["win_rate"] = round((wins / total) if total else 0.0, 4)
        normalized.append(item)
    return normalized


def _tier_expr() -> str:
    return (
        "CASE "
        "WHEN COALESCE((ds.payload->'evidence'->'news_context'->'tiers_count'->>'N1')::int, 0) > 0 THEN 'N1' "
        "WHEN COALESCE((ds.payload->'evidence'->'news_context'->'tiers_count'->>'N3')::int, 0) > 0 THEN 'N3' "
        "ELSE 'unknown' "
        "END"
    )


def fetch_coverage_analytics(
    *,
    user_id: str,
    plugin: str,
    from_date: date,
    to_date: date,
) -> dict:
    total_sql = text(
        """
        SELECT COUNT(*) AS total_decisions
        FROM decision_snapshots
        WHERE user_id = :user_id
          AND plugin = :plugin
          AND as_of BETWEEN :from_date AND :to_date
        """
    )
    labeled_sql = text(
        """
        SELECT
          COUNT(outcomes.id) AS labeled_decisions,
          COALESCE(AVG(EXTRACT(EPOCH FROM (outcomes.labeled_at - ds.created_at))), 0) AS avg_label_delay_seconds,
          COALESCE(
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (outcomes.labeled_at - ds.created_at))),
            0
          ) AS label_delay_p95_seconds
        FROM decision_outcomes outcomes
        JOIN decision_snapshots ds
          ON ds.user_id = outcomes.user_id
         AND ds.as_of = outcomes.as_of
         AND ds.plugin = outcomes.plugin
         AND ds.inputs_hash = outcomes.decision_inputs_hash
        WHERE outcomes.user_id = :user_id
          AND outcomes.plugin = :plugin
          AND outcomes.as_of BETWEEN :from_date AND :to_date
          AND lower(outcomes.outcome_label) IN ('win', 'loss', 'neutral')
        """
    )
    dup_sql = text(
        """
        SELECT COUNT(*) AS duplicated_decisions
        FROM (
          SELECT outcomes.as_of
          FROM decision_outcomes outcomes
          WHERE outcomes.user_id = :user_id
            AND outcomes.plugin = :plugin
            AND outcomes.as_of BETWEEN :from_date AND :to_date
          GROUP BY outcomes.as_of
          HAVING COUNT(DISTINCT outcomes.decision_inputs_hash) > 1
        ) AS dup
        """
    )
    params = {
        "user_id": user_id,
        "plugin": plugin,
        "from_date": from_date,
        "to_date": to_date,
    }
    with engine.begin() as conn:
        total_decisions = int(conn.execute(total_sql, params).scalar() or 0)
        labeled_row = conn.execute(labeled_sql, params).mappings().first() or {}
        duplicated_decisions = int(conn.execute(dup_sql, params).scalar() or 0)

    labeled_decisions = int(labeled_row.get("labeled_decisions") or 0)
    avg_delay = float(labeled_row.get("avg_label_delay_seconds") or 0)
    p95_delay = float(labeled_row.get("label_delay_p95_seconds") or 0)

    coverage_rate = labeled_decisions / total_decisions if total_decisions else 0.0
    unknown_rate = (
        (total_decisions - labeled_decisions) / total_decisions if total_decisions else 0.0
    )
    duplicated_rate = (
        duplicated_decisions / total_decisions if total_decisions else 0.0
    )

    return {
        "total_decisions": total_decisions,
        "labeled_decisions": labeled_decisions,
        "coverage_rate": coverage_rate,
        "unknown_rate": unknown_rate,
        "avg_label_delay_seconds": avg_delay,
        "label_delay_p95_seconds": p95_delay,
        "duplicated_decision_rate": duplicated_rate,
    }


def fetch_trigger_attribution(
    *,
    user_id: str,
    plugin: str,
    from_date: date,
    to_date: date,
    labeled_only: bool,
    only_triggered: bool,
) -> list[dict]:
    clauses = [
        "te.user_id = :user_id",
        "te.plugin = :plugin",
        "te.as_of BETWEEN :from_date AND :to_date",
    ]
    if only_triggered:
        clauses.append("te.is_triggered = TRUE")
    join_sql = "LEFT JOIN decision_outcomes outcomes"
    if labeled_only:
        join_sql = "JOIN decision_outcomes outcomes"
        clauses.append("lower(outcomes.outcome_label) IN ('win', 'loss', 'neutral')")

    where_sql = " AND ".join(clauses)
    sql = text(
        f"""
        SELECT
          te.trigger_key AS trigger_key,
          COUNT(*) AS total,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'win' THEN 1 ELSE 0 END) AS wins,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'loss' THEN 1 ELSE 0 END) AS losses,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'neutral' THEN 1 ELSE 0 END) AS neutral,
          SUM(
            CASE
              WHEN outcomes.outcome_label IS NULL
                OR lower(outcomes.outcome_label) NOT IN ('win', 'loss', 'neutral')
              THEN 1
              ELSE 0
            END
          ) AS unknown
        FROM trigger_evaluations te
        {join_sql}
          ON outcomes.user_id = te.user_id
         AND outcomes.as_of = te.as_of
         AND outcomes.plugin = te.plugin
         AND outcomes.decision_inputs_hash = te.decision_inputs_hash
        WHERE {where_sql}
        GROUP BY te.trigger_key
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(
            sql,
            {
                "user_id": user_id,
                "plugin": plugin,
                "from_date": from_date,
                "to_date": to_date,
            },
        ).mappings().all()
    return _normalize_analytics_rows([dict(row) for row in rows])


def fetch_tier_attribution(
    *,
    user_id: str,
    plugin: str,
    from_date: date,
    to_date: date,
    labeled_only: bool,
) -> list[dict]:
    tier_expr = _tier_expr()
    clauses = [
        "ds.user_id = :user_id",
        "ds.plugin = :plugin",
        "ds.as_of BETWEEN :from_date AND :to_date",
    ]
    join_sql = "LEFT JOIN decision_outcomes outcomes"
    if labeled_only:
        join_sql = "JOIN decision_outcomes outcomes"
        clauses.append("lower(outcomes.outcome_label) IN ('win', 'loss', 'neutral')")

    where_sql = " AND ".join(clauses)
    sql = text(
        f"""
        SELECT
          {tier_expr} AS tier,
          COUNT(*) AS total,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'win' THEN 1 ELSE 0 END) AS wins,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'loss' THEN 1 ELSE 0 END) AS losses,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'neutral' THEN 1 ELSE 0 END) AS neutral,
          SUM(
            CASE
              WHEN outcomes.outcome_label IS NULL
                OR lower(outcomes.outcome_label) NOT IN ('win', 'loss', 'neutral')
              THEN 1
              ELSE 0
            END
          ) AS unknown
        FROM decision_snapshots ds
        {join_sql}
          ON outcomes.user_id = ds.user_id
         AND outcomes.as_of = ds.as_of
         AND outcomes.plugin = ds.plugin
         AND outcomes.decision_inputs_hash = ds.inputs_hash
        WHERE {where_sql}
        GROUP BY {tier_expr}
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(
            sql,
            {
                "user_id": user_id,
                "plugin": plugin,
                "from_date": from_date,
                "to_date": to_date,
            },
        ).mappings().all()
    return _normalize_analytics_rows([dict(row) for row in rows])


def fetch_trigger_analytics(
    *,
    user_id: str,
    plugin: str,
    from_date: date,
    to_date: date,
    only_triggered: bool,
) -> list[dict]:
    clause_triggered = "AND te.is_triggered = TRUE" if only_triggered else ""
    sql = text(
        f"""
        SELECT
          te.trigger_key AS trigger_key,
          COUNT(outcomes.id) AS total,
          SUM(CASE WHEN te.is_triggered THEN 1 ELSE 0 END) AS triggered,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'win' THEN 1 ELSE 0 END) AS wins,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'loss' THEN 1 ELSE 0 END) AS losses,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'neutral' THEN 1 ELSE 0 END) AS neutral,
          SUM(CASE WHEN lower(outcomes.outcome_label) NOT IN ('win', 'loss', 'neutral') THEN 1 ELSE 0 END) AS unknown
        FROM trigger_evaluations te
        JOIN decision_outcomes outcomes
          ON outcomes.user_id = te.user_id
         AND outcomes.as_of = te.as_of
         AND outcomes.plugin = te.plugin
         AND outcomes.decision_inputs_hash = te.decision_inputs_hash
        WHERE te.user_id = :user_id
          AND te.plugin = :plugin
          AND te.as_of BETWEEN :from_date AND :to_date
          {clause_triggered}
        GROUP BY te.trigger_key
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(
            sql,
            {
                "user_id": user_id,
                "plugin": plugin,
                "from_date": from_date,
                "to_date": to_date,
            },
        ).mappings().all()
    return _normalize_analytics_rows([dict(row) for row in rows])


def fetch_decision_analytics(
    *,
    user_id: str,
    plugin: str,
    from_date: date,
    to_date: date,
    group_by: str,
) -> list[dict]:
    if group_by == "decision":
        label_expr = "COALESCE(ds.decision, 'unknown')"
        label_field = "decision"
    else:
        label_expr = (
            "CASE "
            "WHEN COALESCE((ds.payload->'evidence'->'news_context'->'tiers_count'->>'N1')::int, 0) > 0 THEN 'N1' "
            "WHEN COALESCE((ds.payload->'evidence'->'news_context'->'tiers_count'->>'N3')::int, 0) > 0 THEN 'N3' "
            "ELSE 'unknown' "
            "END"
        )
        label_field = "tier"

    sql = text(
        f"""
        SELECT
          {label_expr} AS label,
          {label_expr} AS {label_field},
          COUNT(outcomes.id) AS total,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'win' THEN 1 ELSE 0 END) AS wins,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'loss' THEN 1 ELSE 0 END) AS losses,
          SUM(CASE WHEN lower(outcomes.outcome_label) = 'neutral' THEN 1 ELSE 0 END) AS neutral,
          SUM(CASE WHEN lower(outcomes.outcome_label) NOT IN ('win', 'loss', 'neutral') THEN 1 ELSE 0 END) AS unknown
        FROM decision_outcomes outcomes
        LEFT JOIN decision_snapshots ds
          ON ds.user_id = outcomes.user_id
         AND ds.as_of = outcomes.as_of
         AND ds.plugin = outcomes.plugin
         AND ds.inputs_hash = outcomes.decision_inputs_hash
        WHERE outcomes.user_id = :user_id
          AND outcomes.plugin = :plugin
          AND outcomes.as_of BETWEEN :from_date AND :to_date
        GROUP BY {label_expr}
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(
            sql,
            {
                "user_id": user_id,
                "plugin": plugin,
                "from_date": from_date,
                "to_date": to_date,
            },
        ).mappings().all()
    return _normalize_analytics_rows([dict(row) for row in rows])
