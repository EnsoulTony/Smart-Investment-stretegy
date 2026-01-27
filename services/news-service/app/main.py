"""News Service 的 FastAPI 進入點。"""

import os
from fastapi import FastAPI, Query

from app.signals import build_signal_items

SERVICE_NAME = os.getenv("SERVICE_NAME", "news-service")
app = FastAPI(title="News Service", version="0.1.0")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """健康檢查端點，確認新聞彙整服務是否存活。"""
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/news/signals", tags=["signals"])
async def news_signals(
    user_id: str = Query(..., description="User id"),
    as_of: str = Query(..., description="As of date (YYYY-MM-DD)"),
) -> dict:
    """Return deterministic Sprint 3 news signals."""
    items = build_signal_items(as_of, user_id=user_id)
    return {
        "schema_version": "3.0",
        "as_of": as_of,
        "source": "stub",
        "items": items,
    }
