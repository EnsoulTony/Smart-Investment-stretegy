#!/usr/bin/env bash
# 運行單個測試並顯示詳細輸出
set -euo pipefail

echo "運行測試並顯示調試輸出..."
docker compose exec -T portfolio-service pytest tests/test_sync_endpoint.py::TestSyncEndpoint::test_first_sync_inserts_all_records -v -s

echo ""
echo "檢查 sync_service 實際執行流程..."
docker compose exec -T portfolio-service python3 -c "
from app.trade_normalizer import TradeNormalizer

# 測試資料
mock_data = [
    {
        'user_id': 'test_user',
        'symbol': 'AAPL',
        'asset_ccy': 'USD',
        'side': 'BUY',
        'quantity': '100',
        'price': '180.50',
        'fee': '1.50',
        'trade_date': '2026-01-20',
        'broker': 'IB'
    }
]

normalizer = TradeNormalizer()
valid_trades, failed_rows = normalizer.normalize_rows(mock_data)

print(f'Valid trades: {len(valid_trades)}')
print(f'Failed rows: {len(failed_rows)}')

if failed_rows:
    for failed in failed_rows:
        print(f'Failed row: {failed}')

if valid_trades:
    for trade in valid_trades:
        print(f'Valid trade: {trade}')
"
