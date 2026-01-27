#!/usr/bin/env bash
# 快速測試 TradeNormalizer
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

docker compose exec -T portfolio-service python3 << 'EOF'
from app.trade_normalizer import TradeNormalizer
import json

# 測試資料（與測試文件中相同）
mock_data = [
    {
        "user_id": "test_user",
        "symbol": "AAPL",
        "asset_ccy": "USD",
        "side": "BUY",
        "quantity": "100",
        "price": "180.50",
        "fee": "1.50",
        "trade_date": "2026-01-20",
        "broker": "IB"
    }
]

print("=== 測試 TradeNormalizer ===")
print(f"Input data: {json.dumps(mock_data, indent=2)}")
print()

normalizer = TradeNormalizer()
print(f"Column mapping: {normalizer.column_mapping}")
print()

valid_trades, failed_rows = normalizer.normalize_rows(mock_data)

print(f"Valid trades: {len(valid_trades)}")
print(f"Failed rows: {len(failed_rows)}")
print()

if failed_rows:
    print("Failed rows details:")
    for failed in failed_rows:
        print(f"  Row {failed['row_index']}: {failed['error']}")
        print(f"  Raw data: {failed['raw_data']}")
    print()

if valid_trades:
    print("Valid trades:")
    for i, trade in enumerate(valid_trades, 1):
        print(f"  Trade {i}: {trade.symbol} {trade.side} {trade.quantity}@{trade.price}")
else:
    print("⚠️  No valid trades!")

EOF
