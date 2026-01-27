#!/usr/bin/env bash
# 診斷並修復測試問題
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

echo "=== Sprint 1-3 測試診斷 ==="
echo ""

echo "步驟 1: 檢查本地測試文件是否已更新..."
if grep -q "started_at.desc" services/portfolio-service/tests/test_sync_endpoint.py; then
    echo "✓ 本地測試文件已更新（使用 started_at）"
else
    echo "✗ 本地測試文件仍使用舊代碼（created_at）"
    exit 1
fi

if grep -q "class MockSheetsClient:" services/portfolio-service/tests/test_sync_endpoint.py; then
    echo "✓ 本地測試文件已更新（使用 MockSheetsClient）"
else
    echo "✗ 本地測試文件仍使用舊的 monkeypatch 方式"
    exit 1
fi

echo ""
echo "步驟 2: 重建 portfolio-service 容器..."
docker compose build portfolio-service

echo ""
echo "步驟 3: 重啟 portfolio-service..."
docker compose up -d portfolio-service

echo ""
echo "步驟 4: 等待服務啟動..."
sleep 3

echo ""
echo "步驟 5: 執行測試..."
docker compose exec -T portfolio-service pytest tests/test_sync_endpoint.py -v --tb=short

echo ""
echo "✓ 測試完成！"
