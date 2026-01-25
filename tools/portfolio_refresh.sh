#!/bin/bash
#
# Portfolio Refresh Tool
# 標準流程：trades/summary → sync（若需要）→ rebuild_positions（require_trades=1）
#
# 用途：
# - 確保 trades 有資料後才執行 rebuild
# - 避免 "rebuild succeeded but symbols_count=0" 問題
# - 適用於 automation / CI / 手動運維
#
# 使用方式：
#   ./tools/portfolio_refresh.sh <user_id>
#
# 範例：
#   ./tools/portfolio_refresh.sh tony
#
# 退出碼：
#   0  - 成功（positions 已刷新）
#   1  - sync 失敗或 trades 仍為 0
#   2  - rebuild 失敗（前置條件不滿足或其他錯誤）
#   3  - 參數錯誤
#

set -euo pipefail

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 預設 API endpoint（可透過環境變數覆寫）
PORTFOLIO_API="${PORTFOLIO_API:-http://localhost:8001}"

# 參數檢查
if [ $# -ne 1 ]; then
    echo -e "${RED}❌ 錯誤：缺少 user_id 參數${NC}"
    echo "使用方式：$0 <user_id>"
    echo "範例：$0 tony"
    exit 3
fi

USER_ID="$1"

echo -e "${BLUE}=== Portfolio Refresh Tool ===${NC}"
echo "User: ${USER_ID}"
echo "Portfolio API: ${PORTFOLIO_API}"
echo ""

# Step 1: 檢查 trades summary
echo -e "${BLUE}📋 Step 1: 檢查 trades summary${NC}"
SUMMARY_URL="${PORTFOLIO_API}/portfolio/trades/summary?user_id=${USER_ID}"
echo "GET ${SUMMARY_URL}"

SUMMARY_RESPONSE=$(curl -s -w "\n%{http_code}" "${SUMMARY_URL}")
HTTP_CODE=$(echo "${SUMMARY_RESPONSE}" | tail -n1)
SUMMARY_BODY=$(echo "${SUMMARY_RESPONSE}" | sed '$d')

echo "HTTP ${HTTP_CODE}"

if [ "${HTTP_CODE}" != "200" ]; then
    echo -e "${RED}❌ trades/summary 失敗${NC}"
    echo "${SUMMARY_BODY}" | jq . 2>/dev/null || echo "${SUMMARY_BODY}"
    exit 1
fi

TRADES_COUNT=$(echo "${SUMMARY_BODY}" | jq -r '.trades_count')
SYMBOLS_COUNT=$(echo "${SUMMARY_BODY}" | jq -r '.symbols_count')

echo "  trades_count: ${TRADES_COUNT}"
echo "  symbols_count: ${SYMBOLS_COUNT}"

# 輸出 verification_sql（可證偽）
VERIFICATION_SQL=$(echo "${SUMMARY_BODY}" | jq -r '.evidence.verification_sql.trades_count' 2>/dev/null || echo "")
if [ -n "${VERIFICATION_SQL}" ]; then
    echo -e "${YELLOW}  🔍 Verification SQL:${NC}"
    echo "    ${VERIFICATION_SQL}"
fi

# Step 2: 若 trades_count == 0，執行 sync
if [ "${TRADES_COUNT}" -eq 0 ]; then
    echo -e "${YELLOW}⚠️  trades_count=0，需要執行 sync${NC}"
    echo ""
    echo -e "${BLUE}📥 Step 2: 執行 sync${NC}"
    
    SYNC_URL="${PORTFOLIO_API}/portfolio/sync?user_id=${USER_ID}"
    echo "POST ${SYNC_URL}"
    
    SYNC_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${SYNC_URL}")
    SYNC_HTTP_CODE=$(echo "${SYNC_RESPONSE}" | tail -n1)
    SYNC_BODY=$(echo "${SYNC_RESPONSE}" | sed '$d')
    
    echo "HTTP ${SYNC_HTTP_CODE}"
    
    if [ "${SYNC_HTTP_CODE}" != "200" ]; then
        echo -e "${RED}❌ sync 失敗${NC}"
        echo "${SYNC_BODY}" | jq . 2>/dev/null || echo "${SYNC_BODY}"
        exit 1
    fi
    
    SYNC_STATUS=$(echo "${SYNC_BODY}" | jq -r '.status')
    SYNC_SYNCED_COUNT=$(echo "${SYNC_BODY}" | jq -r '.synced_count')
    
    echo "  status: ${SYNC_STATUS}"
    echo "  synced_count: ${SYNC_SYNCED_COUNT}"
    
    # 再次檢查 trades summary
    echo ""
    echo -e "${BLUE}🔄 Step 2b: 再次檢查 trades summary${NC}"
    echo "GET ${SUMMARY_URL}"
    
    SUMMARY_RESPONSE=$(curl -s -w "\n%{http_code}" "${SUMMARY_URL}")
    HTTP_CODE=$(echo "${SUMMARY_RESPONSE}" | tail -n1)
    SUMMARY_BODY=$(echo "${SUMMARY_RESPONSE}" | sed '$d')
    
    echo "HTTP ${HTTP_CODE}"
    
    TRADES_COUNT=$(echo "${SUMMARY_BODY}" | jq -r '.trades_count')
    SYMBOLS_COUNT=$(echo "${SUMMARY_BODY}" | jq -r '.symbols_count')
    
    echo "  trades_count: ${TRADES_COUNT}"
    echo "  symbols_count: ${SYMBOLS_COUNT}"
    
    if [ "${TRADES_COUNT}" -eq 0 ]; then
        echo -e "${RED}❌ sync 後 trades_count 仍為 0，無法繼續${NC}"
        echo -e "${YELLOW}可能原因：${NC}"
        echo "  - Google Sheets 沒有該用戶的交易資料"
        echo "  - Sheets 權限問題"
        echo "  - sync 服務配置錯誤"
        echo ""
        echo -e "${YELLOW}🔍 Evidence:${NC}"
        echo "${SUMMARY_BODY}" | jq '.evidence' 2>/dev/null || echo "${SUMMARY_BODY}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ sync 成功，trades_count=${TRADES_COUNT}${NC}"
else
    echo -e "${GREEN}✅ trades 已有資料，跳過 sync${NC}"
fi

# Step 3: 執行 rebuild_positions（require_trades=1）
echo ""
echo -e "${BLUE}🔨 Step 3: 執行 rebuild_positions (require_trades=1)${NC}"

REBUILD_URL="${PORTFOLIO_API}/portfolio/rebuild_positions?user_id=${USER_ID}&require_trades=1"
echo "POST ${REBUILD_URL}"

REBUILD_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${REBUILD_URL}")
REBUILD_HTTP_CODE=$(echo "${REBUILD_RESPONSE}" | tail -n1)
REBUILD_BODY=$(echo "${REBUILD_RESPONSE}" | sed '$d')

echo "HTTP ${REBUILD_HTTP_CODE}"

# 409 Conflict = 前置條件失敗（不應該發生，因為我們已檢查過）
if [ "${REBUILD_HTTP_CODE}" = "409" ]; then
    echo -e "${RED}❌ rebuild 前置條件失敗（require_trades=true 被擋）${NC}"
    echo "${REBUILD_BODY}" | jq '.detail' 2>/dev/null || echo "${REBUILD_BODY}"
    exit 2
fi

# 其他非 200 錯誤
if [ "${REBUILD_HTTP_CODE}" != "200" ]; then
    echo -e "${RED}❌ rebuild 失敗${NC}"
    echo "${REBUILD_BODY}" | jq . 2>/dev/null || echo "${REBUILD_BODY}"
    exit 2
fi

# 解析成功回應
REBUILD_STATUS=$(echo "${REBUILD_BODY}" | jq -r '.status')
REBUILD_SYMBOLS=$(echo "${REBUILD_BODY}" | jq -r '.symbols_count')
REBUILD_UPSERTED=$(echo "${REBUILD_BODY}" | jq -r '.upserted_count')
REBUILD_DELETED=$(echo "${REBUILD_BODY}" | jq -r '.deleted_or_zeroed_count')

echo "  status: ${REBUILD_STATUS}"
echo "  symbols_count: ${REBUILD_SYMBOLS}"
echo "  upserted_count: ${REBUILD_UPSERTED}"
echo "  deleted_or_zeroed_count: ${REBUILD_DELETED}"

# 輸出 evidence（可證偽）
echo ""
echo -e "${YELLOW}🔍 Evidence (可證偽):${NC}"
EVIDENCE=$(echo "${REBUILD_BODY}" | jq '.evidence')
echo "${EVIDENCE}" | jq .

# 提取 verification_sql
VERIFICATION_SQL_TRADES=$(echo "${EVIDENCE}" | jq -r '.verification_sql.trades_count' 2>/dev/null || echo "")
VERIFICATION_SQL_POSITIONS=$(echo "${EVIDENCE}" | jq -r '.verification_sql.positions_count' 2>/dev/null || echo "")

if [ -n "${VERIFICATION_SQL_TRADES}" ]; then
    echo ""
    echo -e "${YELLOW}📊 可執行的驗證 SQL:${NC}"
    echo "  Trades:    ${VERIFICATION_SQL_TRADES}"
    if [ -n "${VERIFICATION_SQL_POSITIONS}" ]; then
        echo "  Positions: ${VERIFICATION_SQL_POSITIONS}"
    fi
fi

# 最終狀態檢查
echo ""
if [ "${REBUILD_STATUS}" = "succeeded" ] && [ "${REBUILD_SYMBOLS}" -gt 0 ]; then
    echo -e "${GREEN}✅ Portfolio refresh 成功！${NC}"
    echo "  - trades: ${TRADES_COUNT} 筆"
    echo "  - symbols: ${REBUILD_SYMBOLS} 個"
    echo "  - positions: ${REBUILD_UPSERTED} 筆寫入"
    exit 0
else
    echo -e "${RED}❌ rebuild 狀態異常${NC}"
    echo "  status: ${REBUILD_STATUS}"
    echo "  symbols_count: ${REBUILD_SYMBOLS}"
    exit 2
fi
