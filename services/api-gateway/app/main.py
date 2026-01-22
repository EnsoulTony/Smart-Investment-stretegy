"""API Gateway / Web BFF 的 FastAPI 進入點。"""

import os
from fastapi import FastAPI

SERVICE_NAME = os.getenv("SERVICE_NAME", "api-gateway")
app = FastAPI(title="API Gateway / Web BFF", version="0.1.0")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """健康檢查端點，供 Docker / K8s 監控探活使用。"""
    return {"status": "ok", "service": SERVICE_NAME}
