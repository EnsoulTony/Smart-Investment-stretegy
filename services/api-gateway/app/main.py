"""API Gateway / Web BFF 的 FastAPI 進入點。"""

import os
import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Any

SERVICE_NAME = os.getenv("SERVICE_NAME", "api-gateway")
PORTFOLIO_SERVICE_URL = os.getenv("PORTFOLIO_SERVICE_URL", "http://portfolio-service:8001")
NEWS_SERVICE_URL = os.getenv("NEWS_SERVICE_URL", "http://news-service:8003")
CORS_ALLOW_ORIGINS = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:8080,http://127.0.0.1:8080",
)

app = FastAPI(title="API Gateway / Web BFF", version="0.1.0")

origins = [origin.strip() for origin in CORS_ALLOW_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """健康檢查端點，供 Docker / K8s 監控探活使用。"""
    return {"status": "ok", "service": SERVICE_NAME}


# ============================================================================
# Portfolio Service 反向代理路由
# ============================================================================

@app.post("/portfolio/sync", tags=["portfolio"])
async def proxy_portfolio_sync(request: Request) -> Any:
    """轉發同步請求到 Portfolio Service。
    
    將請求轉發至 portfolio-service 的 /portfolio/sync 端點。
    保留原始請求的 body、headers，並回傳後端服務的完整回應。
    
    Returns:
        Any: Portfolio Service 的回應（狀態碼、JSON body）
        
    Raises:
        HTTPException: 當後端服務無法連線或回應錯誤時
    """
    target_url = f"{PORTFOLIO_SERVICE_URL}/portfolio/sync"
    
    try:
        # 讀取原始請求 body
        body = await request.body()
        
        # 使用 httpx 轉發請求
        async with httpx.AsyncClient() as client:
            response = await client.post(
                target_url,
                content=body,
                headers=dict(request.headers),
                timeout=30.0
            )
        
        # 回傳後端服務的回應（保留狀態碼與 body）
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type="application/json"
        )
    
    except httpx.RequestError as e:
        # 網路連線錯誤（無法連線到後端服務）
        raise HTTPException(
            status_code=503,
            detail=f"無法連線到 Portfolio Service: {str(e)}"
        )
    except Exception as e:
        # 其他未預期錯誤
        raise HTTPException(
            status_code=500,
            detail=f"轉發請求時發生錯誤: {str(e)}"
        )


@app.get("/portfolio/health", tags=["portfolio"])
async def proxy_portfolio_health() -> Any:
    """轉發健康檢查請求到 Portfolio Service。
    
    將請求轉發至 portfolio-service 的 /health 端點。
    用於檢查後端服務是否正常運作。
    
    Returns:
        Any: Portfolio Service 的健康檢查回應
        
    Raises:
        HTTPException: 當後端服務無法連線或回應錯誤時
    """
    target_url = f"{PORTFOLIO_SERVICE_URL}/health"
    
    try:
        # 使用 httpx 轉發請求
        async with httpx.AsyncClient() as client:
            response = await client.get(target_url, timeout=5.0)
        
        # 回傳後端服務的回應（保留狀態碼與 body）
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type="application/json"
        )
    
    except httpx.RequestError as e:
        # 網路連線錯誤（無法連線到後端服務）
        raise HTTPException(
            status_code=503,
            detail=f"無法連線到 Portfolio Service: {str(e)}"
        )
    except Exception as e:
        # 其他未預期錯誤
        raise HTTPException(
            status_code=500,
            detail=f"轉發請求時發生錯誤: {str(e)}"
        )


# ============================================================================
# News Service 反向代理路由
# ============================================================================

@app.get("/news/signals", tags=["news"])
async def proxy_news_signals(request: Request) -> Any:
    """轉發 news signals 請求到 News Service。"""
    target_url = f"{NEWS_SERVICE_URL}/news/signals"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                target_url,
                params=dict(request.query_params),
                timeout=10.0,
            )
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type="application/json",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=f"無法連線到 News Service: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"轉發請求時發生錯誤: {str(e)}",
        )
