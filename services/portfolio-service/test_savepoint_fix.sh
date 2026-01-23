#!/bin/bash
# 驗證 SAVEPOINT 修正是否消除 SAWarning

set -euo pipefail

echo "=== 驗證 conftest.py SAVEPOINT 修正 ==="
echo ""

echo "步驟 1/2: 重建並啟動服務"
docker compose up -d --build portfolio-service
sleep 2
echo "✓ 服務已啟動"
echo ""

echo "步驟 2/2: 執行測試（檢查是否有 SAWarning）"
echo ""
docker compose exec portfolio-service pytest tests/test_db_schema.py -v

echo ""
echo "=== 驗證要點 ==="
echo "1. 所有測試應該通過（6 passed）"
echo "2. warnings summary 不應該出現 'SAWarning: transaction already deassociated from connection'"
echo "3. 如果有 datetime.utcnow deprecation warning，這是預期的（已在 models.py 修正）"
