# Sprint 1-4.3 驗收報告：rebuild_positions 寫回 positions 表

## 執行時間
2026-01-24

## 目標
實作 `rebuild_positions` 端點，從 `trades` 表重算帳務並寫入 `positions` 表。

## 完成項目

### 1. 核心功能實作
✅ **PositionRebuilder.rebuild_positions()** 方法實作
   - 使用既有的 `preview_rebuild()` 計算邏輯
   - 寫入 `positions` 表（使用 `session.merge()` 實現冪等性）
   - 回傳格式：`{status, symbols, affected_count}`

### 2. 欄位策略（符合帳務層規範）
✅ **asset_ccy**: 來自 trade 的原幣別
✅ **u_pnl**: 固定填 0（不做估值）
✅ **不呼叫 FX 模組**：帳務層硬禁止（已驗證無 `from app.fx` import）

### 3. API Schema 更新
✅ **RebuildPositionsResponse** 更新為：
```python
{
  "status": "succeeded",  # 或 "failed"
  "symbols": ["AAPL", "TSLA"],  # 受影響的標的列表
  "affected_count": 2  # 受影響的標的數量
}
```

### 4. 測試覆蓋

#### 新增測試檔案：test_rebuild_positions_write.py
✅ **test_rebuild_positions_writes_to_database**
   - 驗證正確寫入 `positions` 表
   - 驗證 `asset_ccy`、`quantity`、`u_pnl` 欄位
   
✅ **test_rebuild_positions_idempotency**
   - 驗證重複執行結果一致
   - 確認使用 `merge()`（覆蓋而非新增）

✅ **test_rebuild_positions_no_trades**
   - 驗證空 trades 時回傳 `{status: "succeeded", affected_count: 0, symbols: []}`

#### 更新既有測試
✅ **test_rebuild_positions_endpoint.py** (6 個測試)
   - 更新 schema 驗證（`rebuilt_symbols_count` → `affected_count` + `symbols`）
   - 所有既有測試通過

✅ **test_rebuild_positions_preview.py** (7 個測試)
   - preview 端點不受影響，所有測試通過

## 測試結果

**執行時間**：2026-01-24 17:18 UTC  
**執行環境**：GitHub Codespaces (Linux)  
**容器**：docker compose run --rm portfolio-service

### 全部測試
```bash
$ docker compose run --rm portfolio-service pytest -q
```

```
........................................................................ [ 92%]
......                                                                   [100%]
78 passed in 1.20s
```

### Sprint 1-4.3 相關測試
```bash
$ docker compose run --rm portfolio-service pytest -q -k rebuild
```

```
................                                                         [100%]
16 passed in 0.45s
```

### FX 模組測試（架構邊界驗證）
```bash
# 測試 1：介面與 Stub
$ docker compose run --rm portfolio-service pytest -q tests/test_fx.py
..............                                                           [100%]
14 passed in 0.03s

# 測試 2：Guardrails
$ docker compose run --rm portfolio-service pytest -q tests/test_fx_guardrails.py
......                                                                   [100%]
6 passed in 0.07s
```

**總計**：
- ✅ 78 個測試全部通過
- ✅ 16 個 rebuild 相關測試通過
- ✅ 20 個 FX 模組測試通過（介面 + Stub + Guardrails）
- ⚠️ **注意**：之前使用 `tests/test_fx/` 目錄路徑會誤報「no tests ran」

**測試分佈**：
- test_rebuild_positions_endpoint.py: 6 passed ✅
- test_rebuild_positions_preview.py: 7 passed ✅
- test_rebuild_positions_write.py: 3 passed ✅

## 架構遵守情況

### 帳務層規範
✅ **不呼叫 FX 模組**
   - 檢查：`grep -r "from app.fx" services/portfolio-service/app/position_rebuilder.py`
   - 結果：無匹配（符合規範）

✅ **不做估值**
   - `u_pnl` 固定填 0
   - 不計算市價、不折算匯率

✅ **使用均價法計算器**
   - 依賴既有的 `avg_cost_calculator.compute_avg_cost()`
   - 計算 `quantity`、`avg_cost`、`realized_pnl`

### 資料庫設計
✅ **冪等性**
   - 使用 `session.merge()` 基於 `user_id + symbol` unique constraint
   - 重複執行不會產生重複記錄

✅ **事務管理**
   - 錯誤時自動 rollback
   - 成功時 commit

## API 契約驗證

### 端點：POST /portfolio/rebuild_positions
✅ **請求格式**
```json
{
  "user_id": "tony"
}
```

✅ **回應格式（成功）**
```json
{
  "status": "succeeded",
  "symbols": ["AAPL", "TSLA"],
  "affected_count": 2
}
```

✅ **回應格式（失敗）**
```json
{
  "status": "failed",
  "symbols": [],
  "affected_count": 0,
  "error": "錯誤訊息"
}
```

✅ **錯誤處理**
- user_id 空字串 → HTTP 422 ✅
- 資料庫錯誤 → 自動 rollback + 回傳 `{status: "failed"}` ✅

## 檔案異動清單

### 修改的檔案
1. `services/portfolio-service/app/position_rebuilder.py`
   - 實作 `PositionRebuilder.rebuild_positions()` 寫入邏輯
   - 使用 `preview_rebuild()` + `session.merge()` + `commit()`

2. `services/portfolio-service/app/schemas.py`
   - 更新 `RebuildPositionsResponse`：`rebuilt_symbols_count` → `affected_count` + `symbols`

3. `services/portfolio-service/tests/test_rebuild_positions_endpoint.py`
   - 更新測試驗證邏輯以符合新 schema

### 新增的檔案
4. `services/portfolio-service/tests/test_rebuild_positions_write.py`
   - 新增 3 個測試：資料庫寫入、冪等性、無 trades

## 技術債務與未來工作

⏸ **valuation_ccy 欄位** (**已驗證：當前不存在**)
   - **證據**：執行 `docker compose exec postgres psql -U investment -d investment_db -c "\d positions"`  
   結果僅有 9 個欄位：`id, user_id, symbol, asset_ccy, quantity, avg_cost, realized_pnl, u_pnl, last_updated_at`
   - **現狀**：Position 表只有 `asset_ccy`（標的資產幣別），無 `valuation_ccy`（報表幣別）
   - **原因**：帳務層只負責累積交易，不涉及幣別轉換或估值
   - **硬禁止規則**：
     - ❌ Sprint 1-4.A/1-4.3 階段禁止新增 `valuation_ccy` / `market_value` / `valuation_date` 欄位
     - ❌ 禁止在帳務層（`position_rebuilder.py`）呼叫 FX 模組
   - ❌ 禁止 `u_pnl` 填入非零值
     - ✅ **唯一例外**：Sprint 1-4.B（估值層）可透過 Alembic migration 新增欄位
   - **建議**：未來 Sprint 1-4.B（估值層）實作時，透過 Alembic migration 新增此欄位

⏸ **估值層（未來 Sprint 1-4.B）**
   - 當前 `u_pnl` 固定為 0（帳務層不計算市價損益）
   - 未來 Sprint 1-4.B 將實作估值層（呼叫 FX 模組折算）

⏸ **Guardrail Tests**
   - 建議新增自動化檢查：掃描 `from app.fx` imports，確保帳務層不呼叫 FX
   - 參考命令：`grep -rn 'from app.fx' services/portfolio-service/app --include='*.py' --exclude-dir=fx`

---

## 🚫 硬禁止規則（Sprint 1-4.A/1-4.3 階段）

### 1. 帳務層禁止呼叫 FX 模組

**禁止清單**：
```python
# ❌ 以下任何一行出現在 position_rebuilder.py 或 avg_cost_calculator.py，視為違規
from app.fx import get_fx_provider
from app.fx import FxProvider
fx_provider.get_rate(...)
fx_provider.convert(...)
```

**檢查命令**：
```bash
grep -n "from app.fx\|import.*fx\|get_rate\|\.convert(" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/avg_cost_calculator.py
# 必須無任何輸出
```

**驗證結果**：✅ 無任何輸出（已驗證）

---

### 2. 禁止新增估值欄位（當前階段）

**禁止新增的欄位**：
- ❌ `valuation_ccy`（估值幣別）
- ❌ `market_value`（市值）
- ❌ `valuation_date`（估值日期）

**檢查命令**：
```bash
docker compose exec postgres psql -U investment -d investment_db -c \
  "SELECT column_name FROM information_schema.columns \
   WHERE table_name='positions' \
   AND column_name ~ '(valuation|market_value)';"
# 必須回傳 (0 rows)
```

**驗證結果**：✅ (0 rows)（已驗證）

---

### 3. 估值欄位只能透過 Alembic Migration 新增

**禁止方式**：
- ❌ 直接執行 SQL ALTER TABLE
- ❌ 在 `models.py` 新增欄位後直接重啟服務

**正確方式**（僅限 Sprint 1-4.B）：
```bash
cd services/portfolio-service
alembic revision -m "sprint_1_4_b_add_valuation_fields"
# 編輯 migration 檔案
alembic upgrade head
```

**Migration 必須包含**：
- ✅ `# Sprint 1-4.B: Valuation Layer` 註解
- ✅ rollback 機制（downgrade 函數）

## 驗收標準達成情況
| 標準 | 狀態 | 證據 |
|------|------|------|
| rebuild_positions 寫入 positions 表 | ✅ | test_rebuild_positions_writes_to_database |
| 使用 avg_cost_calculator | ✅ | position_rebuilder.py 依賴 compute_avg_cost |
| asset_ccy 來自 trade | ✅ | 測試驗證 `position.asset_ccy == "USD"` |
| u_pnl 填 0 | ✅ | 測試驗證 `position.u_pnl == Decimal("0")` |
| 不呼叫 FX 模組 | ✅ | grep 驗證無 `from app.fx` |
| 冪等性 | ✅ | test_rebuild_positions_idempotency |
| user_id 空字串 → 422 | ✅ | test_rebuild_positions_empty_user_id |
| 回傳 symbols + affected_count | ✅ | schema 更新 + 測試驗證 |
| 所有既有測試通過 | ✅ | 16/16 passed |

## 結論
✅ **Sprint 1-4.3 驗收通過**

所有核心需求已實作並通過測試：
- ✅ 帳務重算邏輯完整
- ✅ 資料庫寫入正確（冪等性）
- ✅ 架構邊界明確（不呼叫 FX）
- ✅ 測試覆蓋充分（16 個測試通過）

可進入下一個 Sprint（估值層實作）。
