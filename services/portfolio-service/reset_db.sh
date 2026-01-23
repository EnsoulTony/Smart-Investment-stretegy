#!/bin/bash
# Portfolio Service 資料庫重置腳本
# 用途：清除所有表格並重新執行 migration（會刪除所有資料！）

set -euo pipefail

echo "⚠️  警告：此操作將刪除 investment_db 中的所有資料！"
echo ""
read -p "確定要繼續嗎？(y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

echo ""
echo "=== 重置 Portfolio Service 資料庫 ==="
echo ""

echo "步驟 1/3: 清除所有表格"
docker compose exec postgres psql -U investment -d investment_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" > /dev/null
echo "✓ 已清除所有表格"
echo ""

echo "步驟 2/3: 執行 migration"
docker compose exec portfolio-service alembic upgrade head
echo "✓ Migration 完成"
echo ""

echo "步驟 3/3: 驗證表格建立"
docker compose exec postgres psql -U investment -d investment_db -c "\dt"
echo ""

echo "=== 重置完成！ ==="
echo ""
echo "可執行測試驗證："
echo "  docker compose exec portfolio-service pytest -q"
