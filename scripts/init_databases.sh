#!/bin/bash
# 初始化所有服務的資料庫遷移
# 用途：在首次部署或資料庫重置後，確保所有資料表都已建立

set -e

echo "=== 資料庫初始化腳本 ==="
echo "執行時間: $(date)"
echo ""

# 等待 postgres 啟動
echo "等待 PostgreSQL 啟動..."
until docker compose exec -T postgres pg_isready -U investment; do
  echo "PostgreSQL 尚未就緒，等待 2 秒..."
  sleep 2
done
echo "✓ PostgreSQL 已就緒"
echo ""

# Portfolio Service 遷移
echo "=== Portfolio Service 資料庫遷移 ==="
docker compose exec -T portfolio-service alembic upgrade head
echo "✓ Portfolio Service 遷移完成"
echo ""

# Radar Service 遷移
echo "=== Radar Service 資料庫遷移 ==="
docker compose exec -T radar-service alembic upgrade head
echo "✓ Radar Service 遷移完成"
echo ""

# News Service 遷移
echo "=== News Service 資料庫遷移 ==="
docker compose exec -T news-service alembic upgrade head
echo "✓ News Service 遷移完成"
echo ""

echo "=== 所有資料庫遷移完成 ==="
echo ""
echo "驗證資料表是否建立："
docker compose exec -T postgres psql -U investment -d investment_db -c "\dt" | grep -E "trades|positions|core_holdings|decision_snapshots|news_signals" || echo "請檢查資料表"
echo ""
echo "完成時間: $(date)"
