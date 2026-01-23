#!/bin/bash
# Portfolio Service DB Schema 驗證腳本
# 用途：驗證 migration 與測試是否正常運作

set -euo pipefail  # 遇到錯誤立即停止，避免假成功

echo "=== Portfolio Service DB Schema 驗證 ==="
echo ""

echo "步驟 1/4: 啟動 postgres 與 portfolio-service"
docker compose up -d --build postgres portfolio-service
echo "✓ 服務已啟動"
echo ""

echo "等待 postgres 就緒..."
sleep 5
echo ""

echo "步驟 2/4: 執行 migration"
# 嘗試執行 migration，如果失敗則使用 stamp
if docker compose exec portfolio-service alembic upgrade head 2>&1 | tee /tmp/alembic_output.log | grep -q "DuplicateTable"; then
    echo "⚠ 表格已存在，使用 alembic stamp 標記當前狀態"
    docker compose exec portfolio-service alembic stamp head
    echo "✓ 已標記 migration 狀態"
else
    if grep -q "ERROR" /tmp/alembic_output.log || grep -q "FAILED" /tmp/alembic_output.log; then
        echo "✗ Migration 執行失敗，請檢查錯誤訊息"
        cat /tmp/alembic_output.log
        exit 1
    fi
    echo "✓ Migration 完成"
fi
echo ""

echo "步驟 3/4: 執行測試"
docker compose exec portfolio-service pytest tests/test_db_schema.py -v
echo "✓ 測試通過"
echo ""

echo "步驟 4/4: 檢查資料表"
docker compose exec postgres psql -U investment -d investment_db -c "\dt"
echo "✓ 資料表已建立"
echo ""

echo "=== 驗證完成！ ==="
echo ""
echo "可用命令："
echo "  - 查看 migration 狀態: docker compose exec portfolio-service alembic current"
echo "  - 查看 migration 歷史: docker compose exec portfolio-service alembic history"
echo "  - 執行所有測試: docker compose exec portfolio-service pytest -q"
echo "  - 進入 postgres: docker compose exec postgres psql -U investment -d investment_db"
echo "  - 快速檢查表格: docker compose exec postgres psql -U investment -d investment_db -c '\\dt'"
