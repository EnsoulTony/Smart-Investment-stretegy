#!/bin/bash
# Sprint 1-4.2 驗證腳本（加固版）

set -e  # 任何命令失敗立即退出

echo "=== 重新建置 portfolio-service 容器 ==="
echo "原因：Dockerfile COPY 了 tests/ 目錄，修改測試需要 rebuild"
docker compose up -d --build portfolio-service

echo ""
echo "=== 等待容器啟動 ==="
sleep 3

echo ""
echo "=== 執行預覽端點測試（含自我驗證檢查）==="
docker compose exec portfolio-service pytest tests/test_rebuild_positions_preview.py -v

echo ""
echo "=== 執行完整測試套件 ==="
echo "預期：55 個測試全部通過（48 既有 + 7 個預覽測試）"
docker compose exec portfolio-service pytest -q

echo ""
echo "=== ✅ 測試完成 ==="
echo ""
echo "如果出現 symbols 空的錯誤，請檢查："
echo "1. client fixture 是否正確 override get_db"
echo "2. 自我驗證的 count 是否 > 0（確認插入成功）"
echo "3. conftest.py 的 SAVEPOINT 機制是否正確"
