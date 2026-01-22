"""Portfolio Service 的 FastAPI 進入點。"""

import os
from fastapi import FastAPI

SERVICE_NAME = os.getenv("SERVICE_NAME", "portfolio-service")
app = FastAPI(title="Portfolio Service", version="0.1.0")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """健康檢查端點，確認投資組合服務是否存活。"""
    return {"status": "ok", "service": SERVICE_NAME}
