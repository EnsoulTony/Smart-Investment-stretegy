# Sprint 1-4.2 驗收命令

本文件提供 Sprint 1-4.2（DB 查詢整合、預覽重算端點與測試加固）的完整驗收命令。

## 環境要求

- Docker Compose 已安裝
- 工作目錄：`/workspaces/Smart-Investment-stretegy`

## 快速驗收（一鍵執行）

```bash
# 方法 1：使用專案提供的腳本
chmod +x tools/test_preview.sh
./tools/test_preview.sh
```

## 詳細驗收步驟

### 步驟 1：重建容器

```bash
# 重建 portfolio-service（包含最新測試程式碼）
docker compose up -d --build portfolio-service

# 等待容器啟動
sleep 3

# 確認容器運行中
docker compose ps portfolio-service
```

**預期結果**：
- 容器狀態為 `Up`
- 沒有錯誤訊息

### 步驟 2：執行預覽端點測試

```bash
# 執行 Sprint 1-4.2 新增的預覽測試
docker compose exec portfolio-service pytest tests/test_rebuild_positions_preview.py -v
```

**預期結果**：
```
collected 7 items

tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_endpoint_exists PASSED [ 14%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_with_no_trades_returns_empty_symbols PASSED [ 28%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_with_single_buy_calculates_correctly PASSED [ 42%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_with_buy_and_sell_calculates_pnl PASSED [ 57%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_with_multiple_symbols_groups_correctly PASSED [ 71%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_response_structure_complete PASSED [ 85%]
tests/test_rebuild_positions_preview.py::TestRebuildPositionsPreview::test_preview_missing_user_id_returns_422 PASSED [100%]

========================= 7 passed in X.XXs =========================
```

**關鍵檢查點**：
- ✅ 所有 7 個測試通過
- ✅ `test_preview_with_single_buy_calculates_correctly` 通過（自我驗證 count = 1）
- ✅ 沒有 `AssertionError: 應有 1 個標的` 錯誤（表示 symbols 不為空）

### 步驟 3：執行完整測試套件

```bash
# 執行所有 portfolio-service 測試
docker compose exec portfolio-service pytest -q
```

**預期結果**：
```
....................................................         [100%]
55 passed in X.XXs
```

**測試分布**：
- 48 個既有測試（Sprint 1-4.0 + 1-4.1 + 其他）
- 7 個新增預覽測試（Sprint 1-4.2）

### 步驟 4：驗證加固措施（可選）

檢查測試程式碼是否包含四個關鍵加固點：

```bash
# 檢查 1: dependency override
docker compose exec portfolio-service grep -A 5 "def client" tests/test_rebuild_positions_preview.py | grep "dependency_overrides"

# 檢查 2: context manager
docker compose exec portfolio-service grep "with TestClient" tests/test_rebuild_positions_preview.py

# 檢查 3: 自我驗證 count
docker compose exec portfolio-service grep "自我驗證" tests/test_rebuild_positions_preview.py

# 檢查 4: 清除 overrides
docker compose exec portfolio-service grep "dependency_overrides.clear()" tests/test_rebuild_positions_preview.py
```

**預期結果**：每個檢查都應該有輸出（找到對應程式碼）

### 步驟 5：手動測試 API 端點（可選）

```bash
# 插入測試資料（在容器內執行 Python）
docker compose exec portfolio-service python3 -c "
from app.db import SessionLocal
from app.models import Trade
from decimal import Decimal
from datetime import datetime

db = SessionLocal()
trade = Trade(
    user_id='manual_test',
    symbol='AAPL',
    asset_ccy='USD',
    side='BUY',
    quantity=Decimal('100'),
    price=Decimal('150.00'),
    fee=Decimal('1.50'),
    trade_date=datetime(2026, 1, 1),
    broker='IB',
    source_hash='manual_hash_1'
)
db.add(trade)
db.commit()
print('Trade inserted successfully')
db.close()
"

# 呼叫預覽 API
curl -X POST http://localhost:8001/portfolio/rebuild_positions/preview \
  -H "Content-Type: application/json" \
  -d '{"user_id": "manual_test"}'

# 清理測試資料
docker compose exec portfolio-service python3 -c "
from app.db import SessionLocal
from app.models import Trade

db = SessionLocal()
db.query(Trade).filter_by(user_id='manual_test').delete()
db.commit()
print('Test data cleaned')
db.close()
"
```

**預期 API 回應**：
```json
{
  "status": "succeeded",
  "user_id": "manual_test",
  "symbols": [
    {
      "symbol": "AAPL",
      "asset_ccy": "USD",
      "qty": 100.0,
      "avg_cost": 150.015,
      "realized_pnl": 0.0,
      "total_fee": 1.5,
      "trades_count": 1
    }
  ],
  "warnings": []
}
```

## Troubleshooting

### 問題 1：symbols 為空

**症狀**：
```
AssertionError: 應有 1 個標的
assert 0 == 1
 +  where 0 = len([])
```

**檢查**：
1. 確認 client fixture 是否正確 override get_db
2. 檢查自我驗證的 count 輸出（如果 count = 0，表示插入失敗）
3. 查看 RUNBOOK.md「2.1. 測試隔離問題」章節

**修正**：參考 `tests/test_rebuild_positions_preview.py` 的 client fixture 實作。

### 問題 2：測試使用舊程式碼

**症狀**：修改測試檔案後，測試結果沒有改變。

**原因**：Dockerfile COPY 了 tests/ 目錄，需要重建容器。

**解決**：
```bash
docker compose up -d --build portfolio-service
```

### 問題 3：容器啟動失敗

**檢查**：
```bash
docker compose logs portfolio-service
```

**常見原因**：
- Postgres 未啟動：`docker compose up -d postgres`
- Alembic migration 未執行：`docker compose exec portfolio-service alembic upgrade head`

## 驗收標準

Sprint 1-4.2 驗收通過的標準：

- ✅ 步驟 2：7 個預覽測試全部通過
- ✅ 步驟 3：55 個測試全部通過
- ✅ 步驟 4：四個加固措施都存在於程式碼中
- ✅ 步驟 5（可選）：手動 API 測試回傳正確的 symbols 資料

## 相關文件

- [RUNBOOK.md](RUNBOOK.md) - 維運指南（包含測試隔離問題 Troubleshooting）
- [Development.md](Development.md) - 開發指南（包含 Sprint 1-4.2 詳細說明與測試加固指南）
- [tests/test_rebuild_positions_preview.py](services/portfolio-service/tests/test_rebuild_positions_preview.py) - 測試實作範例
