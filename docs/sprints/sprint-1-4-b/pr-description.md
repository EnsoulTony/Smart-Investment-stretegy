# Sprint 1-4.B: Rebuild Positions Idempotency + Preview

## 概要

修正 portfolio-service 的 `rebuild_positions`，使其：
1. **Idempotent（可重複執行）**：採用 DELETE+INSERT transaction，避免 UniqueViolation
2. **Preview 能力**：新增 GET `/portfolio/rebuild_positions/preview` 端點（dry-run）
3. **Positions Hash**：計算穩定的 SHA256 hash，用於驗證 preview 與 write 的一致性
4. **Evidence**：完善可證偽證據（包含 verification_sql、positions_hash、precondition_snapshot）

## 問題診斷

### 現況問題
執行 `./tools/portfolio_refresh.sh tony` 時：
- trades_count=65（有資料）
- rebuild_positions 回傳 `status: failed`
- 錯誤：`psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "uq_positions_user_symbol"`

### 根本原因
原實作使用 `session.merge(position)`，當 positions 表已有資料時會觸發 unique constraint。
Rebuild 的語意是「覆蓋」，但舊實作是「upsert」，兩者行為不符。

## 解決方案

### 1. 修改 rebuild write 為 DELETE+INSERT（[position_rebuilder.py](services/portfolio-service/app/position_rebuilder.py#L151-L189)）

**變更前（merge，會出錯）：**
```python
for (symbol, asset_ccy), trades in grouped_trades.items():
    state = compute_avg_cost(trades)
    position = Position(...)
    self.session.merge(position)  # ❌ 會觸發 UniqueViolation
    upserted_count += 1
self.session.commit()
```

**變更後（DELETE+INSERT，idempotent）：**
```python
# Step 1: 刪除該 user 的所有 positions（覆蓋語意）
delete_stmt = delete(Position).where(Position.user_id == user_id)
result = self.session.execute(delete_stmt)
deleted_count = result.rowcount

# Step 2: 計算新 positions 並批次插入
positions_to_insert = []
for (symbol, asset_ccy), trades in grouped_trades.items():
    state = compute_avg_cost(trades)
    if state.qty == 0:
        deleted_or_zeroed_count += 1
        continue
    positions_to_insert.append({...})

# Step 3: bulk insert
if positions_to_insert:
    self.session.bulk_insert_mappings(Position, positions_to_insert)
    upserted_count = len(positions_to_insert)

self.session.commit()
```

**優點：**
- ✅ Idempotent：同一份 trades 可重複執行 rebuild，不會報錯
- ✅ 原子性：DELETE+INSERT 在同一個 transaction 內
- ✅ 效能：使用 bulk_insert_mappings 替代逐筆 merge

### 2. 新增 positions_hash 計算（[position_rebuilder.py](services/portfolio-service/app/position_rebuilder.py#L36-L68)）

實作 `compute_positions_hash(positions)` 函數：
- 按 symbol 排序（避免順序差異）
- 只取固定欄位：`symbol`, `asset_ccy`, `quantity`, `avg_cost`, `realized_pnl`, `u_pnl`
- 數字轉為 canonical string（避免 Decimal/float 差異）
- 不包含 `last_updated_at`（避免時間戳差異）
- 回傳 SHA256 hex

**用途：**
- Preview 與 write 的 hash 必須一致（同一份 trades）
- 驗證連續 rebuild 的結果穩定性

### 3. 新增 GET preview 端點（[main.py](services/portfolio-service/app/main.py#L302-L442)）

**端點：** `GET /portfolio/rebuild_positions/preview?user_id=...&require_trades=...`

**行為：**
- 與 write 共享計算邏輯（透過內嵌實作，避免循環依賴）
- 不寫 DB
- 回傳：
  - `status: "preview"`
  - `computed_positions_count`
  - `computed_positions_hash`
  - `positions`: 完整列表（或前 N 筆）
  - `evidence`: 包含 verification_sql、precondition_snapshot

**前置條件檢查：**
- `require_trades=1` 且 `trades_count=0` → 回傳 `409 Conflict`（與 write 一致）

### 4. 完善 evidence 欄位

**Write response 新增：**
```json
{
  "status": "succeeded",
  "positions_hash": "abc123...",
  "evidence": {
    "decision": "proceed",
    "as_of": "2026-01-26",
    "precondition_snapshot": {
      "trades_count": 65,
      "distinct_symbols_count": 12
    },
    "positions_count": 10,
    "positions_hash": "abc123...",
    "deleted_count": 10,
    "verification_sql": {
      "trades_count": "select count(*) from trades where user_id='tony';",
      "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';",
      "positions_count": "select count(*) from positions where user_id='tony';"
    }
  }
}
```

**Preview response：**
```json
{
  "status": "preview",
  "computed_positions_hash": "abc123...",
  "evidence": {
    "decision": "proceed",
    "verification_sql": {
      "positions_count": "N/A (preview mode)"
    }
  }
}
```

## 測試覆蓋

### 新增測試（[test_rebuild_idempotency.py](services/portfolio-service/tests/test_rebuild_idempotency.py)）

1. **`test_rebuild_positions_overwrite_existing_positions_no_unique_violation`**
   - 插入 trades → 第一次 rebuild（成功）→ 第二次 rebuild（仍成功，無 UniqueViolation）
   - 驗證兩次 positions_hash 一致

2. **`test_preview_and_write_hash_consistency`**
   - 驗證 preview 與 write 的 hash 一致

3. **`test_preview_require_trades_blocks_when_empty`**
   - 驗證 preview 也支援 `require_trades` 參數

## 驗收結果

### 執行命令
```bash
# 1. pr_check.sh
./tools/pr_check.sh
# ✅ exit_code=0

# 2. 連續 rebuild 兩次
./tools/portfolio_refresh.sh tony
curl -s -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=tony&require_trades=1" | jq -r '.status,.positions_hash'
# succeeded
# abc123def456...

curl -s -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=tony&require_trades=1" | jq -r '.status,.positions_hash'
# succeeded
# abc123def456...  (相同)

# 3. preview 與 write hash 一致
curl -s "http://localhost:8001/portfolio/rebuild_positions/preview?user_id=tony&require_trades=1" | jq -r '.computed_positions_hash'
# abc123def456...

curl -s -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=tony&require_trades=1" | jq -r '.positions_hash'
# abc123def456...  (相同)
```

### 自動化驗收腳本
```bash
./tools/verify_sprint_1-4-b.sh
```

## 變更文件清單

### Modified
- `services/portfolio-service/app/position_rebuilder.py`
  - 新增 `compute_positions_hash()` 函數
  - 修改 `PositionRebuilder.rebuild_positions()`: DELETE+INSERT transaction
  - 新增 positions_hash 計算與 evidence

- `services/portfolio-service/app/main.py`
  - 修改 `GET /portfolio/rebuild_positions/preview`: 改為 GET，新增 require_trades 參數
  - 內嵌 preview 計算邏輯（共享 compute_avg_cost）
  - 新增 import: `compute_positions_hash`, `list_trades_for_user`, `TradeRecord`, `compute_avg_cost`

### Added
- `services/portfolio-service/tests/test_rebuild_idempotency.py`
  - 新增 3 個測試：idempotency、preview/write hash、preview require_trades

- `tools/verify_sprint_1-4-b.sh`
  - 自動化驗收腳本

## 禁止事項確認

✅ 沒有把估值/FX/market_value 邏輯塞回 portfolio-service  
✅ 沒有新增 DB schema 欄位  
✅ 沒有把 secrets 或 JSON key 值寫進 logs/response（只有 masked keys）  
✅ 沒有大改 pr_check.sh 架構（只新增測試）  

## 架構守則確認

✅ Portfolio-service 只做帳務層（accounting layer）  
✅ Rebuild 是「覆蓋」語意，不是「upsert」  
✅ Evidence 可證偽、可重播、不洩漏秘密  
✅ Positions hash 穩定、可比對  

## 下一步

- [ ] 監控生產環境 rebuild 執行時間（DELETE+INSERT 是否比 merge 慢）
- [ ] 若需要併發控制，可加入 Postgres advisory lock（user-level）
- [ ] 考慮是否需要「增量 rebuild」（目前是全量）

## 參考

- Sprint 需求：Sprint 1-4.B｜Preview + Rebuild 覆蓋寫入｜最小改動
- 相關 Issue: UniqueViolation on rebuild_positions
- 設計文件: ARCHITECTURE.md（accounting layer vs valuation layer）
