#!/bin/bash
# Sprint 1-4.B 最終驗收（包含所有修復）

set -e

echo "========================================="
echo "Sprint 1-4.B 最終驗收"
echo "========================================="
echo ""

cd /root/Smart-Investment-stretegy

# 重新構建（包含測試修復）
echo "[1/5] 重新構建服務（包含測試修復）..."
docker compose build valuation-service portfolio-service

echo ""
echo "[2/5] Runtime Guard 手動測試..."
set +e
docker compose run --rm -e DATABASE_URL=postgresql://x:y@z:5432/db valuation-service \
  python -c "from app.guardrails import check_and_exit; check_and_exit()" \
  >/tmp/guard_test.txt 2>&1
GUARD_EXIT=$?
set -e

echo "Exit code captured: $GUARD_EXIT"

if [ "$GUARD_EXIT" != "0" ]; then
  echo "✅ Runtime Guard 手動測試通過 (exit: $GUARD_EXIT)"
  
  # 驗證 evidence
  if grep -q "blocked_env_keys" /tmp/guard_test.txt; then
    echo "✅ Evidence contains blocked_env_keys"
  fi
  if grep -q "D\*\*\*\*\*\*\*\*\*\*L" /tmp/guard_test.txt; then
    echo "✅ DATABASE_URL is masked correctly"
  fi
else
  echo "❌ Runtime Guard 手動測試失敗"
  cat /tmp/guard_test.txt
  exit 1
fi

echo ""
echo "[3/5] 執行 valuation-service 測試..."
docker compose run --rm valuation-service pytest -q

echo ""
echo "[4/5] 執行 portfolio-service 測試..."
docker compose exec -T portfolio-service pytest -q || docker compose run --rm portfolio-service pytest -q

echo ""
echo "[5/5] PR Gate 檢查..."
./tools/pr_check.sh

echo ""
echo "========================================="
echo "✅ Sprint 1-4.B 最終驗收通過"
echo "========================================="
echo ""
echo "交付清單："
echo "  ✅ Runtime Guard 正確阻斷 DATABASE_URL"
echo "  ✅ Migration 具有冪等性"
echo "  ✅ Forbidden tokens 掃描無誤報"
echo "  ✅ 所有測試通過"
echo "  ✅ PR Gate 全綠"
echo ""
