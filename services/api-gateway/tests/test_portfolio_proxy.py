"""API Gateway Portfolio 反向代理測試。"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_proxy_portfolio_sync_success():
    """測試成功轉發 /portfolio/sync 請求。"""
    # 模擬後端服務回應
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.content = b'{"run_id": "123", "inserted_count": 10, "status": "succeeded"}'
    mock_response.headers = {"content-type": "application/json"}
    
    # Mock httpx.AsyncClient
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        
        # 發送請求
        response = client.post("/portfolio/sync", json={})
        
        # 驗證回應
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "123"
        assert data["inserted_count"] == 10
        assert data["status"] == "succeeded"
        
        # 驗證轉發的 URL 正確
        mock_client.return_value.__aenter__.return_value.post.assert_called_once()
        call_args = mock_client.return_value.__aenter__.return_value.post.call_args
        assert call_args[0][0] == "http://portfolio-service:8001/portfolio/sync"


@pytest.mark.asyncio
async def test_proxy_portfolio_sync_backend_error():
    """測試後端服務回傳 500 錯誤。"""
    # 模擬後端服務回傳 500
    mock_response = AsyncMock()
    mock_response.status_code = 500
    mock_response.content = b'{"detail": "Internal Server Error"}'
    mock_response.headers = {"content-type": "application/json"}
    
    # Mock httpx.AsyncClient
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        
        # 發送請求
        response = client.post("/portfolio/sync", json={})
        
        # 驗證回應（應保留後端的 500 狀態碼）
        assert response.status_code == 500


@pytest.mark.asyncio
async def test_proxy_portfolio_sync_connection_error():
    """測試無法連線到後端服務。"""
    # Mock httpx.AsyncClient 拋出連線錯誤
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.RequestError("Connection refused")
        )
        
        # 發送請求
        response = client.post("/portfolio/sync", json={})
        
        # 驗證回應（應回傳 503）
        assert response.status_code == 503
        data = response.json()
        assert "無法連線到 Portfolio Service" in data["detail"]


@pytest.mark.asyncio
async def test_proxy_portfolio_health_success():
    """測試成功轉發 /portfolio/health 請求。"""
    # 模擬後端服務回應
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.content = b'{"status": "ok", "service": "portfolio-service"}'
    mock_response.headers = {"content-type": "application/json"}
    
    # Mock httpx.AsyncClient
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        # 發送請求
        response = client.get("/portfolio/health")
        
        # 驗證回應
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "portfolio-service"
        
        # 驗證轉發的 URL 正確
        mock_client.return_value.__aenter__.return_value.get.assert_called_once()
        call_args = mock_client.return_value.__aenter__.return_value.get.call_args
        assert call_args[0][0] == "http://portfolio-service:8001/health"


@pytest.mark.asyncio
async def test_proxy_portfolio_health_connection_error():
    """測試無法連線到後端服務（健康檢查）。"""
    # Mock httpx.AsyncClient 拋出連線錯誤
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.RequestError("Connection refused")
        )
        
        # 發送請求
        response = client.get("/portfolio/health")
        
        # 驗證回應（應回傳 503）
        assert response.status_code == 503
        data = response.json()
        assert "無法連線到 Portfolio Service" in data["detail"]


def test_portfolio_sync_preserves_request_body():
    """測試轉發時保留請求 body。"""
    # 模擬後端服務回應
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.content = b'{"status": "ok"}'
    mock_response.headers = {"content-type": "application/json"}
    
    # Mock httpx.AsyncClient
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        
        # 發送帶有 body 的請求
        test_body = {"test_key": "test_value"}
        response = client.post("/portfolio/sync", json=test_body)
        
        # 驗證回應
        assert response.status_code == 200
        
        # 驗證轉發時包含了原始 body
        mock_client.return_value.__aenter__.return_value.post.assert_called_once()
        call_kwargs = mock_client.return_value.__aenter__.return_value.post.call_args[1]
        # body 會被轉換為 bytes
        assert "content" in call_kwargs
