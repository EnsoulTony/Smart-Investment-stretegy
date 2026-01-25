#!/bin/bash
# 快速測試 Runtime Guard 修復

echo "========================================="
echo "測試 Runtime Guard 修復"
echo "========================================="
echo ""

cd /root/Smart-Investment-stretegy

echo "[1/3] 重新構建 valuation-service..."
docker compose build valuation-service

echo ""
echo "[2/3] 測試 Runtime Guard（注入 DATABASE_URL）..."
set +e
docker compose run --rm -e DATABASE_URL=postgresql://x:y@z:5432/db valuation-service \
  python -c "from app.guardrails import check_and_exit; check_and_exit()" \
  2>&1 | tee /tmp/guard_test.txt
GUARD_EXIT=$?
set -e

echo ""
echo "[3/3] 驗證結果..."
echo "Exit code: $GUARD_EXIT"

if [ "$GUARD_EXIT" == "78" ]; then
  echo "✅ Guard blocked with correct exit code (78)"
elif [ "$GUARD_EXIT" != "0" ]; then
  echo "✅ Guard blocked (exit code: $GUARD_EXIT)"
else
  echo "❌ Guard did NOT block (exit code: 0)"
  echo "Output:"
  cat /tmp/guard_test.txt
  exit 1
fi

if grep -q "blocked_env_keys" /tmp/guard_test.txt; then
  echo "✅ Evidence contains blocked_env_keys"
fi

if grep -q "D\*\*\*\*\*\*\*\*\*\*L" /tmp/guard_test.txt; then
  echo "✅ DATABASE_URL is masked"
fi

if grep -q "postgresql://x:y@z" /tmp/guard_test.txt; then
  echo "❌ Guard leaked value!"
  exit 1
else
  echo "✅ Guard does not leak env values"
fi

echo ""
echo "========================================="
echo "✅ Runtime Guard 修復驗證通過"
echo "========================================="
