#!/bin/bash
# 驗證 Pydantic V2 deprecation warnings 已修正

set -euo pipefail

echo "=== 驗證 Pydantic V2 Warnings 修正 ==="
echo ""

echo "重建映像並執行測試..."
docker compose build portfolio-service
docker compose up -d portfolio-service
sleep 2

echo ""
echo "執行測試（檢查 warnings）："
docker compose exec portfolio-service pytest tests/test_trade_normalizer.py -v 2>&1 | tee /tmp/test_output.log

echo ""
echo "=== Warnings 檢查 ==="
if grep -q "PydanticDeprecatedSince20" /tmp/test_output.log; then
    echo "❌ 仍有 Pydantic deprecation warnings"
    grep "PydanticDeprecatedSince20" /tmp/test_output.log
    exit 1
else
    echo "✅ 無 Pydantic deprecation warnings"
fi

echo ""
echo "測試結果檢查："
if grep -q "11 passed" /tmp/test_output.log; then
    echo "✅ 11 個測試全部通過（含新增的 timezone 測試）"
else
    echo "⚠️  測試通過數量異常"
    grep "passed" /tmp/test_output.log
fi
