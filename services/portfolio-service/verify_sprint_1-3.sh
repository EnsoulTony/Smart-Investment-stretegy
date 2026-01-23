#!/usr/bin/env bash
# Sprint 1-3 驗證腳本：POST /portfolio/sync 端點完整測試
set -euo pipefail

echo "=========================================="
echo "Sprint 1-3 驗證：POST /portfolio/sync"
echo "=========================================="

# 顏色定義
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 計數器
PASS=0
FAIL=0

# 輔助函式：檢查結果
check_result() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ PASS${NC}: $1"
        ((PASS++))
    else
        echo -e "${RED}✗ FAIL${NC}: $1"
        ((FAIL++))
        return 1
    fi
}

echo ""
echo "Step 1: 檢查服務狀態"
echo "--------------------"
docker compose ps postgres portfolio-service > /dev/null 2>&1
check_result "Docker Compose 服務運行中"

echo ""
echo "Step 2: 檢查 migrations 狀態"
echo "----------------------------"
docker compose exec -T portfolio-service alembic current > /dev/null 2>&1
check_result "Alembic migrations 已執行"

echo ""
echo "Step 3: 執行單元測試（test_trade_normalizer.py）"
echo "----------------------------------------------"
docker compose exec -T portfolio-service pytest tests/test_trade_normalizer.py -v --tb=short
check_result "TradeNormalizer 測試通過（11/11）"

echo ""
echo "Step 4: 執行端點測試（test_sync_endpoint.py）"
echo "-------------------------------------------"
docker compose exec -T portfolio-service pytest tests/test_sync_endpoint.py -v --tb=short
check_result "Sync endpoint 測試通過（5 個測試案例）"

echo ""
echo "Step 5: 檢查資料表結構"
echo "---------------------"
TABLES=$(docker compose exec -T postgres psql -U investment -d investment_db -t -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('trades', 'positions', 'sync_runs');" | wc -l)
if [ "$TABLES" -ge 3 ]; then
    check_result "資料表結構完整（trades, positions, sync_runs）"
else
    echo -e "${RED}✗ FAIL${NC}: 資料表不完整（預期 3 個，實際 $TABLES 個）"
    ((FAIL++))
fi

echo ""
echo "Step 6: 檢查 source_hash UNIQUE constraint"
echo "-----------------------------------------"
CONSTRAINT=$(docker compose exec -T postgres psql -U investment -d investment_db -t -c "SELECT constraint_name FROM information_schema.table_constraints WHERE table_name='trades' AND constraint_type='UNIQUE' AND constraint_name='uq_trades_source_hash';" | wc -l)
if [ "$CONSTRAINT" -ge 1 ]; then
    check_result "source_hash UNIQUE constraint 存在"
else
    echo -e "${RED}✗ FAIL${NC}: source_hash UNIQUE constraint 不存在"
    ((FAIL++))
fi

echo ""
echo "Step 7: 測試去重邏輯（手動驗證）"
echo "-------------------------------"
echo -e "${YELLOW}提示${NC}: 需要設定 GOOGLE_SA_JSON 環境變數才能手動測試"
echo "手動測試指令："
echo "  1. 第一次同步: curl -X POST http://localhost:8001/portfolio/sync"
echo "  2. 第二次同步: curl -X POST http://localhost:8001/portfolio/sync"
echo "  3. 預期結果: inserted_count=N, skipped_count=N（第二次全跳過）"

echo ""
echo "Step 8: 檢查 API_CONTRACTS.md 更新"
echo "---------------------------------"
if grep -q "errors_count" ../../API_CONTRACTS.md; then
    check_result "API_CONTRACTS.md 包含 errors_count 欄位"
else
    echo -e "${RED}✗ FAIL${NC}: API_CONTRACTS.md 缺少 errors_count 欄位"
    ((FAIL++))
fi

echo ""
echo "Step 9: 檢查 Development.md 更新"
echo "-------------------------------"
if grep -q "Sprint 1-3.*POST /portfolio/sync" ../../Development.md; then
    check_result "Development.md 包含 Sprint 1-3 說明"
else
    echo -e "${RED}✗ FAIL${NC}: Development.md 缺少 Sprint 1-3 說明"
    ((FAIL++))
fi

echo ""
echo "=========================================="
echo "驗證結果總結"
echo "=========================================="
echo -e "${GREEN}通過: $PASS${NC}"
echo -e "${RED}失敗: $FAIL${NC}"

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✓ Sprint 1-3 驗證通過！${NC}"
    exit 0
else
    echo -e "${RED}✗ Sprint 1-3 驗證失敗（$FAIL 個測試失敗）${NC}"
    exit 1
fi
