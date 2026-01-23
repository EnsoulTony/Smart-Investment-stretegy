#!/bin/bash
# Sprint 1-2 驗證：Google Sheets Client 與交易標準化

set -euo pipefail

echo "=== Sprint 1-2 驗證：Google Sheets Client 與交易標準化 ==="
echo ""

echo "步驟 1/3: 重建 portfolio-service（包含新依賴）"
docker compose build portfolio-service
echo "✓ 映像重建完成"
echo ""

echo "步驟 2/3: 啟動服務"
docker compose up -d portfolio-service
sleep 2
echo "✓ 服務已啟動"
echo ""

echo "步驟 3/3: 執行測試（不需連 Google，使用 fixture 假資料）"
echo ""
docker compose exec portfolio-service pytest tests/test_trade_normalizer.py -v

echo ""
echo "=== Sprint 1-2 驗證完成 ==="
echo ""
echo "✅ 已實作功能："
echo "  1. app/sheets_client.py - Google Sheets 客戶端（Service Account 認證）"
echo "  2. app/schemas.py - TradeRecord Pydantic 模型（支援中文買/賣轉換）"
echo "  3. app/trade_normalizer.py - 交易資料標準化與 source_hash 計算"
echo "  4. tests/test_trade_normalizer.py - 完整單元測試"
echo ""
echo "📝 後續步驟（Sprint 1-3）："
echo "  - 實作 POST /portfolio/sync 端點（呼叫 sheets_client 與 trade_normalizer）"
echo "  - 將標準化後的交易寫入 trades 表（使用 source_hash 去重）"
