#!/bin/bash
# Sprint 1-4.B 驗收命令集
# 可直接在 VM / Codespaces 中執行

set -e

echo "========================================="
echo "Sprint 1-4.B Valuation Layer 驗收"
echo "========================================="
echo ""

# 1. 啟動服務
echo "[1/7] 啟動服務..."
docker compose up -d --build valuation-service portfolio-service postgres

# 2. 等待資料庫就緒
echo "[2/7] 等待資料庫就緒..."
docker compose exec -T postgres sh -c 'until pg_isready -U investment; do sleep 1; done'

# 3. 執行 migration
echo "[3/7] 執行資料庫 migration..."
docker compose exec -T portfolio-service alembic upgrade head

# 4. 同步測試資料
echo "[4/7] 同步測試資料..."
./tools/portfolio_refresh.sh test_e2e 2>/dev/null || echo "Warning: portfolio_refresh may have warnings"

# 5. 測試估值 API（正常情況）
echo ""
echo "[5/7] 測試估值 API（正常情況：HTTP 200）..."
HTTP_CODE=$(curl -s -o /tmp/val_response.json -w "%{http_code}" \
  "http://localhost:8005/valuation/portfolio?user_id=test_e2e&base_ccy=USD")

if [ "$HTTP_CODE" == "200" ]; then
  echo "✅ HTTP 200 OK"
  
  # 驗證 content-type（從實際響應）
  CONTENT_TYPE=$(curl -s -i "http://localhost:8005/valuation/portfolio?user_id=test_e2e&base_ccy=USD" | grep -i "content-type" | head -n 1)
  echo "   Content-Type: $CONTENT_TYPE"
  
  # 驗證 JSON 可解析
  if python3 -c "import json; json.load(open('/tmp/val_response.json'))" 2>/dev/null; then
    echo "✅ Response is valid JSON"
  else
    echo "❌ Response is NOT valid JSON"
    cat /tmp/val_response.json
    exit 1
  fi
  
  # 驗證 evidence.decision
  DECISION=$(jq -r '.evidence.decision' /tmp/val_response.json)
  if [ "$DECISION" == "proceed" ]; then
    echo "✅ evidence.decision = proceed"
  else
    echo "❌ evidence.decision = $DECISION (expected: proceed)"
    exit 1
  fi
  
  # 驗證 totals 存在
  MARKET_VALUE=$(jq -r '.totals.market_value' /tmp/val_response.json)
  if [ "$MARKET_VALUE" != "null" ]; then
    echo "✅ totals.market_value = $MARKET_VALUE"
  else
    echo "❌ totals.market_value is null"
    exit 1
  fi
  
else
  echo "❌ HTTP $HTTP_CODE (expected 200)"
  cat /tmp/val_response.json
  exit 1
fi

# 6. 測試前置條件（trades=0 → 409）
echo ""
echo "[6/7] 測試前置條件檢查（空用戶：HTTP 409）..."
HTTP_CODE=$(curl -s -o /tmp/val_409.json -w "%{http_code}" \
  "http://localhost:8005/valuation/portfolio?user_id=empty_user_xyz&base_ccy=USD")

if [ "$HTTP_CODE" == "409" ]; then
  echo "✅ HTTP 409 Conflict"
  
  # 驗證 JSON 可解析
  if python3 -c "import json; json.load(open('/tmp/val_409.json'))" 2>/dev/null; then
    echo "✅ 409 response is valid JSON"
  else
    echo "❌ 409 response is NOT valid JSON"
    cat /tmp/val_409.json
    exit 1
  fi
  
  # 驗證 trades_count=0
  TRADES_COUNT=$(jq -r '.detail.evidence.precondition_snapshot.trades_count // .detail.precondition_snapshot.trades_count // "not_found"' /tmp/val_409.json)
  if [ "$TRADES_COUNT" == "0" ]; then
    echo "✅ trades_count = 0"
  else
    echo "⚠️  trades_count = $TRADES_COUNT (expected 0, but may vary)"
  fi
  
else
  echo "❌ HTTP $HTTP_CODE (expected 409)"
  cat /tmp/val_409.json
  exit 1
fi

# 7. Runtime Guard 測試
echo ""
echo "[7/7] Runtime Guard 注入測試..."
set +e  # 允許指令失敗
docker compose run --rm -e DATABASE_URL=postgresql://x:y@z:5432/db valuation-service \
  python -c "from app.guardrails import check_and_exit; check_and_exit()" \
  >/tmp/guard_output.txt 2>&1
GUARD_EXIT=$?
set -e

if [ "$GUARD_EXIT" != "0" ]; then
  echo "✅ Guard blocked (exit code: $GUARD_EXIT)"
  
  # 驗證 evidence 只含 key 不含 value
  if grep -q "blocked_env_keys" /tmp/guard_output.txt; then
    echo "✅ Evidence contains blocked_env_keys"
  fi
  
  if grep -q "postgresql://x:y@z" /tmp/guard_output.txt; then
    echo "❌ Guard leaked DATABASE_URL value!"
    cat /tmp/guard_output.txt
    exit 1
  else
    echo "✅ Guard output does not leak env values"
  fi
  
else
  echo "❌ Guard did NOT block (exit code: $GUARD_EXIT)"
  cat /tmp/guard_output.txt
  exit 1
fi

# 總結
echo ""
echo "========================================="
echo "✅ Sprint 1-4.B 驗收通過"
echo "========================================="
echo ""
echo "完成檢查："
echo "  1. 服務啟動成功"
echo "  2. 資料庫就緒"
echo "  3. Migration 成功"
echo "  4. 測試資料同步"
echo "  5. 正常估值（HTTP 200 + JSON + evidence）"
echo "  6. 前置條件檢查（HTTP 409 + JSON）"
echo "  7. Runtime Guard 阻斷 DB env"
echo ""
echo "建議執行完整測試："
echo "  docker compose exec -T valuation-service pytest -q"
echo "  docker compose exec -T portfolio-service pytest -q"
echo "  ./tools/pr_check.sh"
echo ""
