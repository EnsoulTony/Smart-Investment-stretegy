#!/bin/bash
# 測試 API Gateway 反向代理功能

set -e

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

echo "=================================================="
echo "測試 API Gateway 反向代理"
echo "=================================================="
echo

# 切換到 api-gateway 目錄
cd "$repo_root/services/api-gateway"

echo "1. 安裝測試依賴..."
pip install -q pytest pytest-asyncio httpx 2>/dev/null || true

echo "2. 執行測試..."
python -m pytest tests/test_portfolio_proxy.py -v --tb=short

echo
echo "=================================================="
echo "✓ 所有測試通過"
echo "=================================================="
