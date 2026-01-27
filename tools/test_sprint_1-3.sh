#!/usr/bin/env bash
# 快速測試腳本
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

echo "執行 Sprint 1-3 測試..."
docker compose exec portfolio-service pytest tests/test_sync_endpoint.py -v --tb=short

echo ""
echo "✓ 測試通過！"
