"""DB helpers for news-service persistence."""

import json
import os
from typing import List, Dict

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://investment:investment@postgres:5432/investment_db",
)

engine = create_engine(DATABASE_URL)


def persist_news_signals(
    user_id: str,
    as_of: str,
    source: str,
    items: List[Dict],
) -> int:
    """Persist news signals to DB. Returns inserted rows count."""
    if not items:
        return 0

    insert_sql = text(
        """
        INSERT INTO public.news_signals
          (user_id, item_id, title, summary_zh, published_at, tier, source_url, source, as_of, payload)
        VALUES
          (:user_id, :item_id, :title, :summary_zh, :published_at, :tier, :source_url, :source, :as_of, :payload)
        """
    )

    rows = []
    for item in items:
        rows.append(
            {
                "user_id": user_id,
                "item_id": item.get("id"),
                "title": item.get("title"),
                "summary_zh": item.get("summary_zh"),
                "published_at": item.get("published_at"),
                "tier": item.get("tier"),
                "source_url": item.get("source_url"),
                "source": source,
                "as_of": as_of,
                "payload": json.dumps(item, ensure_ascii=False),
            }
        )

    with engine.begin() as conn:
        conn.execute(insert_sql, rows)
    return len(rows)
