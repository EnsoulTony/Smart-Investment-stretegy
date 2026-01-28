"""DB helpers for news-service persistence."""

import json
import os
from datetime import date, datetime
from typing import List, Dict, Tuple

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://investment:investment@postgres:5432/investment_db",
)

engine = create_engine(DATABASE_URL)


def _parse_published_date(published_at: str | None, as_of: str) -> date:
    if published_at:
        try:
            value = published_at.replace("Z", "+00:00")
            return datetime.fromisoformat(value).date()
        except ValueError:
            pass
    return date.fromisoformat(as_of)


def _compute_weight(item: Dict) -> int:
    """EDS proxy weight rule (fixed):
    - N1 = 2, N3 = 1
    - +1 if symbols exist
    - +1 if themes include macro/credit/war/tariff/ai_power
    - +1 if falsifiable_triggers exists
    """
    weight = 2 if item.get("tier") == "N1" else 1
    if item.get("symbols"):
        weight += 1
    themes = set(item.get("themes") or [])
    if themes.intersection({"rates_central_bank", "credit_event", "war_energy_supply", "tariff_sanctions", "ai_power"}):
        weight += 1
    if item.get("falsifiable_triggers"):
        weight += 1
    return weight


def _group_by_source_date(items: List[Dict], as_of: str, source: str) -> Dict[Tuple[str, date], List[Dict]]:
    grouped: Dict[Tuple[str, date], List[Dict]] = {}
    for item in items:
        published_date = _parse_published_date(item.get("published_at"), as_of)
        key = (source, published_date)
        grouped.setdefault(key, []).append(item)
    return grouped


def persist_news_signals(
    user_id: str,
    as_of: str,
    source: str,
    items: List[Dict],
) -> int:
    """Persist news signals to DB with dedup + per-source daily cap (30)."""
    if not items:
        return 0

    insert_sql = text(
        """
        INSERT INTO public.news_signals
          (user_id, item_id, title, summary_zh, published_at, published_date, tier, source_url, source, as_of, weight, payload)
        VALUES
          (:user_id, :item_id, :title, :summary_zh, :published_at, :published_date, :tier, :source_url, :source, :as_of, :weight, :payload)
        """
    )

    total_inserted = 0
    grouped = _group_by_source_date(items, as_of, source)

    with engine.begin() as conn:
        for (group_source, published_date), group_items in grouped.items():
            existing_titles = conn.execute(
                text(
                    """
                    SELECT title
                    FROM public.news_signals
                    WHERE source = :source AND published_date = :published_date
                    """
                ),
                {"source": group_source, "published_date": published_date},
            ).fetchall()
            existing_title_set = {row[0] for row in existing_titles}

            existing_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM public.news_signals
                    WHERE source = :source AND published_date = :published_date
                    """
                ),
                {"source": group_source, "published_date": published_date},
            ).scalar_one()

            remaining = max(0, 30 - int(existing_count))
            if remaining == 0:
                continue

            filtered = [item for item in group_items if item.get("title") not in existing_title_set]
            for item in filtered:
                item["weight"] = _compute_weight(item)

            filtered.sort(
                key=lambda x: (x.get("weight", 0), x.get("published_at") or ""),
                reverse=True,
            )
            selected = filtered[:remaining]

            rows = []
            for item in selected:
                rows.append(
                    {
                        "user_id": user_id,
                        "item_id": item.get("id"),
                        "title": item.get("title"),
                        "summary_zh": item.get("summary_zh"),
                        "published_at": item.get("published_at"),
                        "published_date": published_date,
                        "tier": item.get("tier"),
                        "source_url": item.get("source_url"),
                        "source": group_source,
                        "as_of": as_of,
                        "weight": item.get("weight", 0),
                        "payload": json.dumps(item, ensure_ascii=False),
                    }
                )

            if rows:
                conn.execute(insert_sql, rows)
                total_inserted += len(rows)

    return total_inserted
