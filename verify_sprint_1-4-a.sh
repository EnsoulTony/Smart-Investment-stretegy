#!/bin/bash
# Sprint 1-4.A 完整驗收腳本

set -e  # 遇到錯誤立即停止

echo "======================================"
echo "Sprint 1-4.A 驗收測試開始"
echo "======================================"
echo ""

# 步驟 0：啟動服務
echo "步驟 0: 啟動 Docker Compose 服務..."
docker compose up -d --build portfolio-service postgres
echo "✅ 服務已啟動"
echo ""

# 等待服務就緒
echo "等待服務就緒（15 秒）..."
sleep 15
echo ""

# 步驟 1：執行 FX 模組單元測試
echo "======================================"
echo "步驟 1: 執行 FX 模組單元測試"
echo "======================================"
docker compose exec -T portfolio-service pytest tests/test_fx.py -v
echo "✅ FX 模組測試通過"
echo ""

# 步驟 2：執行規範守門測試
echo "======================================"
echo "步驟 2: 執行規範守門測試（Guardrail Tests）"
echo "======================================"
docker compose exec -T portfolio-service pytest tests/test_fx_guardrails.py -v
echo "✅ Guardrail 測試通過"
echo ""

# 步驟 3：驗證 API
echo "======================================"
echo "步驟 3: 驗證 FX Provider API"
echo "======================================"
docker compose exec -T portfolio-service python3 -c "
from app.fx import get_fx_provider
from decimal import Decimal

fx = get_fx_provider()
print(f'✅ Provider: {fx.source()}, is_stub: {fx.is_stub()}')

# 同幣別轉換
result = fx.convert(Decimal('100'), 'USD', 'USD')
assert result == Decimal('100'), f'同幣別轉換失敗: expected 100, got {result}'
print(f'✅ 100 USD -> USD = {result}')

# 跨幣別轉換（應失敗）
try:
    fx.convert(Decimal('100'), 'USD', 'TWD')
    print('❌ 錯誤：跨幣別轉換應該拋出 NotImplementedError')
    exit(1)
except NotImplementedError:
    print('✅ 跨幣別轉換正確失敗（預期行為）')

print('\\n✅ API 驗證完成')
"
echo ""

# 步驟 4：執行所有 portfolio-service 測試
echo "======================================"
echo "步驟 4: 執行所有 portfolio-service 測試"
echo "======================================"
docker compose exec -T portfolio-service pytest tests/ -q
echo "✅ 所有測試通過"
echo ""

# 步驟 5：驗證 Guardrail 有效性（可選，用於演示）
echo "======================================"
echo "步驟 5: 驗證 Guardrail 有效性（演示）"
echo "======================================"
echo "建立臨時違規檔案進行測試..."

# 建立臨時違規檔案
docker compose exec -T portfolio-service sh -c '
cat > /app/app/temp_violation.py << "EOF"
import os

def bad_function():
    # 這是違規：直接讀取 FX 環境變數
    fx_provider = os.getenv("FX_PROVIDER")
    return fx_provider
EOF
'

echo "執行 Guardrail 測試（應該檢測到違規）..."
if docker compose exec -T portfolio-service pytest tests/test_fx_guardrails.py::TestFxGuardrails::test_no_direct_fx_env_access_outside_fx_module -v 2>&1 | grep -q "FAILED"; then
    echo "✅ Guardrail 正確檢測到違規"
else
    echo "❌ Guardrail 未能檢測到違規"
    exit 1
fi

# 清除臨時檔案
docker compose exec -T portfolio-service rm -f /app/app/temp_violation.py
echo "✅ Guardrail 有效性驗證完成"
echo ""

# 最終報告
echo "======================================"
echo "✅ Sprint 1-4.A 驗收測試全部通過"
echo "======================================"
echo ""
echo "已驗證項目："
echo "  ✅ FX 模組單元測試"
echo "  ✅ 規範守門測試（Guardrail Tests）"
echo "  ✅ FX Provider API 正確性"
echo "  ✅ 所有 portfolio-service 測試"
echo "  ✅ Guardrail 有效性（能檢測違規）"
echo ""
echo "交付檔案："
echo "  - app/fx/__init__.py"
echo "  - app/fx/types.py"
echo "  - app/fx/interfaces.py"
echo "  - app/fx/stub_provider.py"
echo "  - tests/test_fx.py"
echo "  - tests/test_fx_guardrails.py"
echo ""
echo "文檔更新："
echo "  - DEVELOPMENT_MD_PATCH.md（待應用到 Development.md）"
echo "  - STRATEGY_MD_PATCH.md（待應用到 Strategy.md）"
echo "  - SPRINT_1-4-A_README.md"
echo ""
echo "下一步："
echo "  1. 手動應用文檔補丁到 Development.md 和 Strategy.md"
echo "  2. 繼續 Sprint 1-4.3（實作 rebuild_positions）"
echo ""
