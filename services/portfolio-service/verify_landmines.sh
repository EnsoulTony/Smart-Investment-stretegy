#!/bin/bash
# 地雷驗收：檢查 requirements 衝突與 hash 穩定性

set -euo pipefail

echo "=== 地雷驗收：Sprint 1-2 隱性問題檢查 ==="
echo ""

echo "地雷 1：Requirements 衝突檢查"
echo "----------------------------------------"
echo "檢查點 1: pydantic 版本由 FastAPI 決定（避免衝突）"
if grep -q "^pydantic>=" services/portfolio-service/requirements.txt; then
    echo "❌ 發現 pydantic 版本約束，可能與 FastAPI 衝突"
    exit 1
else
    echo "✅ pydantic 版本由 FastAPI 決定"
fi
echo ""

echo "檢查點 2: 重建映像並檢查依賴安裝"
docker compose build portfolio-service > /tmp/build.log 2>&1
if [ $? -eq 0 ]; then
    echo "✅ 映像重建成功，無依賴衝突"
else
    echo "❌ 映像重建失敗"
    cat /tmp/build.log
    exit 1
fi
echo ""

echo "地雷 2：Hash Canonicalization 穩定性檢查"
echo "----------------------------------------"
echo "檢查點 3: 執行 timezone 一致性測試"
docker compose up -d portfolio-service
sleep 2
docker compose exec portfolio-service pytest tests/test_trade_normalizer.py::TestTradeNormalizer::test_compute_source_hash_timezone_consistency -v

if [ $? -eq 0 ]; then
    echo "✅ Hash 時區一致性測試通過"
else
    echo "❌ Hash 時區一致性測試失敗"
    exit 1
fi
echo ""

echo "檢查點 4: 執行完整測試套件"
docker compose exec portfolio-service pytest tests/test_trade_normalizer.py -v

if [ $? -eq 0 ]; then
    echo "✅ 完整測試套件通過"
else
    echo "❌ 測試套件失敗"
    exit 1
fi
echo ""

echo "=== 地雷驗收完成 ==="
echo ""
echo "✅ 地雷 1（Requirements 衝突）：已修復"
echo "   - 移除 pydantic 版本約束，由 FastAPI 決定相容版本"
echo ""
echo "✅ 地雷 2（Hash 不穩定）：已修復"
echo "   - Timezone-aware datetime 統一轉 UTC 後移除時區資訊"
echo "   - Naive datetime 直接使用"
echo "   - 確保相同 UTC 時刻產生相同 hash"
echo ""
echo "🎯 Sprint 1-2 可以安全進入 Sprint 1-3（POST /portfolio/sync）"
