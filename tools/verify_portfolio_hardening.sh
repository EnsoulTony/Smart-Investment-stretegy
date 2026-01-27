#!/bin/bash
# Portfolio Service 加固驗收腳本

set -e

echo "=================================================="
echo "Portfolio Service 加固驗收"
echo "=================================================="
echo

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root/services/portfolio-service"

echo "1. 檢查 Python 語法..."
python -m py_compile app/trade_normalizer.py
python -m py_compile app/sync_service.py
echo "✓ 語法檢查通過"
echo

echo "2. 執行 Hash 版本控制測試..."
pytest tests/test_hash_versioning.py -v
echo

echo "3. 執行可觀測性測試..."
pytest tests/test_sync_observability.py -v
echo

echo "4. 執行所有測試..."
pytest tests/ -q --tb=short
echo

echo "=================================================="
echo "✓ 所有測試通過！"
echo "=================================================="
echo
echo "加固功能已實作："
echo "  1. source_hash 包含版本前綴 (CANONICAL_VERSION=v1)"
echo "  2. /portfolio/sync 回應增加可觀測性欄位"
echo "  3. 同步流程加入結構化 log"
echo "  4. 測試覆蓋 hash 版本控制與可觀測性"
