"""Radar Service 的 FastAPI 進入點。"""

import os
from fastapi import FastAPI

SERVICE_NAME = os.getenv("SERVICE_NAME", "radar-service")
app = FastAPI(title="Radar Service", version="0.1.0")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """健康檢查端點，確認技術指標服務是否存活。"""
    return {"status": "ok", "service": SERVICE_NAME}
