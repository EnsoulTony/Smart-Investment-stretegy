"""Health Check Test for Valuation Service"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    """測試 /health 端點"""
    response = client.get("/health")
    
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "valuation-service"
    assert "portfolio_base_url" in data
    assert "capabilities" in data
    
    # 確認宣告了關鍵能力
    capabilities = data["capabilities"]
    assert any("API-only" in cap for cap in capabilities)
    assert any("no DB" in cap for cap in capabilities)
    assert any("Guardrails" in cap for cap in capabilities)


def test_health_check_exposes_portfolio_base_url():
    """確認 health 端點暴露 PORTFOLIO_BASE_URL 配置"""
    response = client.get("/health")
    data = response.json()
    
    # 應該能看到 portfolio-service 的位址
    assert "portfolio_base_url" in data
    assert "portfolio-service" in data["portfolio_base_url"]
