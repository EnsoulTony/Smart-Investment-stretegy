# Portfolio Service 加固完成報告

## 實作目標
避免因 canonical/hash 規則變動或多來源寫入造成重複污染，並讓同步回應可觀測。

## 完成項目

### 1. ✅ Source Hash 版本控制

**目的**：避免未來 canonical 規則變動造成 hash 衝突

**修改內容**：
- 檔案：`services/portfolio-service/app/trade_normalizer.py`
- 新增常數：`CANONICAL_VERSION = "v1"`
- 修改 `compute_source_hash()` 方法：
  ```python
  # 舊版（無版本前綴）
  canonical = "user_id|symbol|asset_ccy|side|quantity|price|fee|trade_date|broker"
  
  # 新版（包含版本前綴）
  canonical = f"{CANONICAL_VERSION}|user_id|symbol|asset_ccy|side|quantity|price|fee|trade_date|broker"
  ```
- 確保未來規則變更時不會與舊資料產生相同 hash

**測試覆蓋**：
- 檔案：`tests/test_hash_versioning.py`
- 測試案例：
  1. `test_hash_includes_version_prefix` - 驗證 hash 一致性
  2. `test_hash_changes_with_version` - 驗證版本變更時 hash 不同（使用 monkeypatch）
  3. `test_hash_identical_for_same_trade_data` - 驗證相同交易產生相同 hash
  4. `test_hash_different_for_different_trade_data` - 驗證不同交易產生不同 hash
  5. `test_canonical_version_constant_exists` - 驗證常數存在且為 v1

### 2. ✅ 可觀測性欄位增強

**目的**：清楚區分「格式錯誤」與「DB 重複」，方便 debug

**修改內容**：
- 檔案：`services/portfolio-service/app/sync_service.py`
- 修改 `SyncResult` 類別，新增欄位：
  - `sheet_rows_count`: 從 Google Sheets 讀取的總列數
  - `normalized_valid_count`: 成功轉換為 TradeRecord 的筆數
  - `normalized_invalid_count`: 格式錯誤無法轉換的筆數
  - `duplicates_count`: 因 source_hash 重複被 DB 去重的筆數

**API 回應範例**：
```json
{
  "run_id": "uuid",
  "inserted_count": 10,
  "updated_count": 0,
  "skipped_count": 5,
  "errors_count": 2,
  "status": "partial_succeeded",
  "sheet_rows_count": 17,
  "normalized_valid_count": 13,
  "normalized_invalid_count": 2,
  "duplicates_count": 3
}
```

**數學關係**：
- `skipped_count = duplicates_count + errors_count`
- `normalized_valid_count + normalized_invalid_count ≈ sheet_rows_count`（扣除空行/表頭）

**測試覆蓋**：
- 檔案：`tests/test_sync_observability.py`
- 測試案例：
  1. `test_sync_result_includes_observability_fields` - 驗證欄位存在
  2. `test_run_sync_returns_correct_observability_metrics` - 驗證指標正確性
  3. `test_sync_result_to_dict_format` - 驗證輸出格式與數學關係

### 3. ✅ 結構化日誌

**目的**：追蹤同步流程，不記錄敏感資料

**修改內容**：
- 檔案：`services/portfolio-service/app/sync_service.py`
- 新增 logger 並在關鍵步驟輸出：
  ```python
  logger.info(f"同步開始 run_id={run_id}")
  logger.info(f"從 Google Sheets 讀取 {sheet_rows_count} 列資料")
  logger.info(f"標準化結果：成功 {normalized_valid_count} 筆，失敗 {normalized_invalid_count} 筆")
  logger.info(f"準備寫入 {len(valid_trades)} 筆交易記錄到資料庫")
  logger.info(f"寫入完成：插入 {inserted_count} 筆，重複跳過 {duplicates_count} 筆")
  logger.info(f"同步狀態：{status}")
  logger.exception(f"同步過程發生錯誤 run_id={run_id}: {e}")
  ```

### 4. ✅ 文檔更新

**修改檔案**：
1. `CHANGELOG.md` - 新增 v0.2.3 版本說明
2. `Development.md` - 補充 hash 版本控制與可觀測性說明
3. `API_CONTRACTS.md` - 更新 `/portfolio/sync` 回應格式

## 驗收方式

### 執行測試
```bash
# 在容器內執行所有測試
docker compose exec portfolio-service pytest -q

# 只執行新測試
docker compose exec portfolio-service pytest tests/test_hash_versioning.py -v
docker compose exec portfolio-service pytest tests/test_sync_observability.py -v

# 本地執行（需先安裝依賴）
cd services/portfolio-service
pytest tests/test_hash_versioning.py tests/test_sync_observability.py -v
```

### 測試覆蓋率
- Hash 版本控制：5 個測試案例
- 可觀測性：3 個測試案例
- 所有測試必須通過

## 技術細節

### Hash 版本控制原理
```python
# v1 版本
canonical_v1 = "v1|tony|AAPL|USD|BUY|100|150.5|1.5|2026-01-23 10:30:00|IB"
hash_v1 = sha256(canonical_v1)  # 某個值

# 未來 v2 版本（例如加入新欄位）
canonical_v2 = "v2|tony|AAPL|USD|BUY|100|150.5|1.5|2026-01-23 10:30:00|IB|新欄位"
hash_v2 = sha256(canonical_v2)  # 不同的值

# 確保不會衝突
assert hash_v1 != hash_v2
```

### 可觀測性欄位用途
- **sheet_rows_count**：確認 Google Sheets API 有正常讀取
- **normalized_valid_count**：驗證資料格式轉換成功率
- **normalized_invalid_count**：快速找出格式錯誤（symbol 不合法、日期錯誤等）
- **duplicates_count**：了解資料重複程度（可能是手動重複匯入、或 cron job 重跑）

### 錯誤診斷範例
```
# 情境 1：全部資料都被跳過
sheet_rows_count: 100
normalized_valid_count: 100
duplicates_count: 100
inserted_count: 0
→ 診斷：所有資料都是重複的，可能是重複執行同步

# 情境 2：大量格式錯誤
sheet_rows_count: 100
normalized_valid_count: 20
normalized_invalid_count: 80
→ 診斷：Google Sheet 資料格式有問題，需檢查 error_message 詳情

# 情境 3：部分成功
sheet_rows_count: 100
normalized_valid_count: 95
duplicates_count: 50
inserted_count: 45
→ 診斷：正常情況，有新資料也有重複資料
```

## 不需修改 DB Schema

所有新欄位都在 API 回應層級處理，不影響資料庫結構：
- `sync_runs` 表保持不變
- `trades` 表保持不變
- 僅在記憶體中計算並回傳可觀測性指標

## 升級影響評估

### 對現有資料的影響
- ⚠️ **重要**：舊版本產生的 source_hash 與新版本不同
- 升級後首次同步會將所有交易視為新資料（因為 hash 不同）
- 解決方案：
  1. 保留舊資料不動
  2. 新交易使用新 hash
  3. 或一次性重算所有舊交易的 hash（需額外腳本）

### 建議升級步驟
1. 備份現有 `trades` 表
2. 部署新版本
3. 執行同步測試（使用測試 Sheet）
4. 確認新 hash 正常運作
5. 正式環境同步
