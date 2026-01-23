# Development.md｜開發指南（MVP）

本文件說明 Smart-Investment-Strategy 的開發流程、提示（prompt）模板與一鍵建置命令。所有說明以繁體中文撰寫，確保各階段與 Claude/Aider 協作一致。

## 開發階段與典型工作流

1. **環境初始化**：設定 `.env`、安裝前後端依賴、啟動 Docker Compose。
2. **服務開發**：依據微服務邊界，在對應目錄新增邏輯、測試與文件。
3. **策略模組**：遵循 `Strategy.md` 規則開發或調整 Radar v1.4 插件。
4. **資料契約與 API**：所有輸入輸出需檢查 `API_CONTRACTS.md`。
5. **測試與驗證**：執行 `TESTING.md` 列出的指令，確保健康檢查與單元測試通過。
6. **部署準備**：更新 `CHANGELOG.md`、確認 `DEPLOYMENT.md` 流程、觸發 GitHub Actions。

## Prompt 模板（依階段區分）

### 1. 架構/雛型設計
```markdown
Task: 定義 / 更新 <模組名稱> 的架構或資料契約
Repo / Files: <列出檔案與行號>
Constraints:
- 僅描述結構，不動現有業務邏輯
- 必須新增或更新對應文件
Tests: 無需執行（文件變更）
Before coding:
- <逐條列出預計修改的檔案與行數>
```

### 2. 服務邏輯開發
```markdown
Task: 實作 <服務名稱> 的新功能/端點
Repo / Files: services/<service>/app/main.py, tests/test_<feature>.py
Constraints:
- 嚴禁修改 Strategy Engine 以外的邏輯
- 所有輸入輸出需符合 API_CONTRACTS.md
Tests:
- pytest
- 若影響前端需補 Vitest
Before coding:
- <列出檔案、模組與大致行數>
```

### 3. 策略/指標更新
```markdown
Task: 更新 Radar v1.4 插件 / 指標
Repo / Files: services/radar-service/*, Strategy.md
Constraints:
- 僅能在 Strategy Engine 插件內改動
- 需描述抽換邊界與回測假設
Tests:
- pytest services/radar-service
Before coding:
- <列出檔案與區塊>
```

### 4. 維運/部署
```markdown
Task: 更新部署腳本或維運流程
Repo / Files: DEPLOYMENT.md, infra/*, RUNBOOK.md
Constraints:
- 不可刪除現有部署步驟
- 需提供回滾方案
Tests:
- 若僅文件，標示 N/A
Before coding:
- <列出檔案與段落>
```

## Sprint 1: Portfolio Service 基礎實作（文件與契約先行）

### Sprint 1-1: 實作 POST /portfolio/sync
```markdown
Task: 實作 portfolio-service 的 POST /portfolio/sync 端點
Repo / Files: 
- services/portfolio-service/app/main.py
- services/portfolio-service/tests/test_sync.py
Constraints:
- 遵循 API_CONTRACTS.md 定義的 Request/Response schema
- 支援 Google Sheets API 讀取（需設定 GOOGLE_SHEETS_CREDENTIALS 環境變數）
- 實作基本錯誤處理（400/401/500）
- 寫入 trades 表時需檢查重複（依 user_id + symbol + trade_date + side 去重）
Tests:
- pytest services/portfolio-service/tests/test_sync.py
- 驗證方式：
  1. 準備測試用 Google Sheets（或 mock）
  2. 呼叫 POST /portfolio/sync
  3. 查詢 Postgres trades 表確認資料正確寫入
  4. 檢查 response 中的 inserted_count/updated_count/skipped_count
Before coding:
- services/portfolio-service/app/main.py (新增 /portfolio/sync 端點，約 50-80 行)
- services/portfolio-service/app/sheets_client.py (新增 Google Sheets 讀取邏輯)
- services/portfolio-service/app/db.py (新增 trades 表 CRUD 操作)
- services/portfolio-service/tests/test_sync.py (新增完整測試案例)
```

### Sprint 1-2: 實作 GET /portfolio/positions/latest
```markdown
Task: 實作 portfolio-service 的 GET /portfolio/positions/latest 端點
Repo / Files:
- services/portfolio-service/app/main.py
- services/portfolio-service/app/position_calculator.py
- services/portfolio-service/tests/test_positions.py
Constraints:
- 遵循 API_CONTRACTS.md 定義的 Response schema
- 實作均價法計算邏輯（參考 Strategy.md）
- 計算公式：avg_cost = Σ(buy_price × quantity) / total_quantity
- 計算 unrealized_pnl（需從外部 API 取得 market_price，或暫用 mock）
- 支援 user_id 篩選
Tests:
- pytest services/portfolio-service/tests/test_positions.py
- 驗證方式：
  1. 準備測試資料（trades 表插入多筆買賣記錄）
  2. 呼叫 GET /portfolio/positions/latest?user_id=test-user
  3. 驗證 avg_cost 計算正確
  4. 驗證 unrealized_pnl 計算正確（market_price 可先 mock）
Before coding:
- services/portfolio-service/app/main.py (新增 /portfolio/positions/latest 端點)
- services/portfolio-service/app/position_calculator.py (均價法計算邏輯，約 60-100 行)
- services/portfolio-service/app/db.py (新增 positions_snapshot 查詢與寫入)
- services/portfolio-service/tests/test_positions.py (測試均價法計算)
```

### Sprint 1-3: 實作 GET /portfolio/trades
```markdown
Task: 實作 portfolio-service 的 GET /portfolio/trades 端點
Repo / Files:
- services/portfolio-service/app/main.py
- services/portfolio-service/tests/test_trades.py
Constraints:
- 遵循 API_CONTRACTS.md 定義的 Response schema
- 支援 query parameters 篩選：user_id (必填)、symbol (選填)、since (選填)
- since 參數需驗證格式（YYYY-MM-DD）
- 回傳結果依 trade_date 降冪排序
Tests:
- pytest services/portfolio-service/tests/test_trades.py
- 驗證方式：
  1. 準備測試資料（trades 表插入多筆記錄）
  2. 測試無篩選條件查詢
  3. 測試 symbol 篩選
  4. 測試 since 篩選
  5. 測試組合篩選
  6. 測試無效 since 格式回傳 400
Before coding:
- services/portfolio-service/app/main.py (新增 /portfolio/trades 端點，約 30-50 行)
- services/portfolio-service/app/db.py (新增 trades 查詢邏輯，支援篩選條件)
- services/portfolio-service/tests/test_trades.py (完整測試各種篩選組合)
```

### Sprint 1-4: Portfolio 資料庫 Schema 與 Migration
```markdown
Task: 建立 portfolio-service 的資料庫 schema 與 migration 腳本
Repo / Files:
- services/portfolio-service/migrations/001_init_schema.sql
- services/portfolio-service/app/db.py
Constraints:
- 建立 trades 表（參考 API_CONTRACTS.md schema）
- 建立 positions_snapshot 表（參考 API_CONTRACTS.md schema）
- 建立必要的 index（user_id, symbol, trade_date）
- 建立 unique constraint 避免重複交易記錄
Tests:
- 手動執行 migration 腳本
- 驗證方式：
  1. 連線到 Postgres: docker exec -it <postgres-container> psql -U postgres
  2. 執行 migration: \i /migrations/001_init_schema.sql
  3. 檢查表格建立: \dt
  4. 檢查欄位定義: \d trades, \d positions_snapshot
  5. 檢查 index 與 constraint: \di
Before coding:
- services/portfolio-service/migrations/001_init_schema.sql (完整 schema 定義)
- services/portfolio-service/app/db.py (新增 DB 連線與基礎操作)
```

### Sprint 1-5: 整合測試與文件驗證
```markdown
Task: 執行 portfolio-service 完整整合測試並驗證文件一致性
Repo / Files:
- services/portfolio-service/tests/test_integration.py
- API_CONTRACTS.md
- Development.md
Constraints:
- 測試完整流程：sync → positions → trades
- 驗證 API_CONTRACTS.md 定義與實作一致
- 確認錯誤處理（400/401/404/500）正確回傳
- 確認回應格式完全符合契約
Tests:
- pytest services/portfolio-service/tests/test_integration.py
- 驗證方式：
  1. 啟動完整環境: make docker-up
  2. 執行整合測試: pytest services/portfolio-service/tests/test_integration.py -v
  3. 測試完整流程：
     - 呼叫 POST /portfolio/sync（mock Google Sheets）
     - 呼叫 GET /portfolio/positions/latest 確認均價法計算
     - 呼叫 GET /portfolio/trades 確認資料可查詢
     - 測試各種錯誤情境
  4. 使用 curl 或 Postman 手動驗證端點
Before coding:
- services/portfolio-service/tests/test_integration.py (完整整合測試)
- 檢查 API_CONTRACTS.md 與實作的一致性
- 更新 CHANGELOG.md 記錄 Sprint 1 完成項目
```

## 一鍵環境建置命令

```bash
# 1. 下載專案並切換目錄
 git clone git@github.com:horstcheng/Smart-Investment-stretegy.git
 cd Smart-Investment-stretegy

# 2. 複製環境變數設定
 cp .env.example .env

# 3. 安裝前端依賴（可在 Codespaces 直接執行）
 make install-frontend

# 4. 建立並啟動所有服務
 make docker-up

# 5. 驗證健康檢查（可用 curl / 瀏覽器）
 curl http://localhost:8000/health
```

## 注意事項

- 所有程式碼與文件須維持繁體中文描述。
- 每次修改必須更新 `CHANGELOG.md`，並在 PR 中附測試結果。
- 與 AI 協作者（Claude、Aider）合作時，務必遵守 `RUNBOOK-AI-GUARDRAILS`。