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

### Sprint 1-2: Google Sheets Client 與交易標準化
```markdown
Task: 建立 Google Sheets 客戶端與交易資料標準化模組
Repo / Files:
- services/portfolio-service/app/sheets_client.py
- services/portfolio-service/app/schemas.py
- services/portfolio-service/app/trade_normalizer.py
- services/portfolio-service/tests/test_trade_normalizer.py
- services/portfolio-service/requirements.txt
- .env.example
- SECURITY.md
Constraints:
- 使用 Service Account 認證（從 env 讀取 GOOGLE_SA_JSON）
- 支援欄位 mapping（透過環境變數自訂欄位名稱）
- 交易方向支援中文（買/賣）並轉換為 BUY/SELL
- 計算 source_hash（SHA-256）用於去重
- 所有金鑰不得寫入 repo
Tests:
- pytest services/portfolio-service/tests/test_trade_normalizer.py -v
- 驗證方式：
  1. 重建映像（包含新依賴）:
     docker compose build portfolio-service
  2. 啟動服務:
     docker compose up -d portfolio-service
  3. 執行測試（不需連 Google，使用 fixture 假資料）:
     docker compose exec portfolio-service pytest tests/test_trade_normalizer.py -v
  4. 驗證測試結果：
     - 所有測試通過（約 10 個測試）
     - 測試包含：欄位 mapping、side 轉換、日期解析、hash 穩定性
Before coding:
- services/portfolio-service/app/sheets_client.py (Google Sheets API 客戶端，約 100 行)
- services/portfolio-service/app/schemas.py (TradeRecord Pydantic 模型，約 120 行)
- services/portfolio-service/app/trade_normalizer.py (資料標準化與 hash 計算，約 180 行)
- services/portfolio-service/tests/test_trade_normalizer.py (單元測試，約 300 行)
- services/portfolio-service/requirements.txt (新增 gspread, google-auth, pydantic)
- .env.example (新增 GOOGLE_SA_JSON, GOOGLE_SHEET_ID 等環境變數)
- SECURITY.md (新增 Service Account 金鑰管理說明)
```

### Sprint 1-3: 完成 POST /portfolio/sync 串接與去重邏輯 ✅
```markdown
Task: 實作 portfolio-service 的 POST /portfolio/sync 端點（Repository/Service 架構）
Repo / Files:
- services/portfolio-service/app/main.py (POST /portfolio/sync 端點)
- services/portfolio-service/app/sync_service.py (協調器：orchestrate sync 流程)
- services/portfolio-service/app/repositories/trades_repo.py (TradesRepository: bulk_insert_trades)
- services/portfolio-service/app/repositories/sync_runs_repo.py (SyncRunsRepository: create_run, finish_run)
- services/portfolio-service/tests/test_sync_endpoint.py (monkeypatch SheetsClient 測試)

實作要點：
1. Repository 層：
   - TradesRepository.bulk_insert_trades() 使用 PostgreSQL INSERT...ON CONFLICT (source_hash) DO NOTHING
   - 回傳 (inserted_count, skipped_count) tuple
   - 處理 timezone：naive datetime → add UTC tzinfo for DB

2. Service 層：
   - SyncService.run_sync() 協調完整流程：
     * create_run → fetch_sheets → normalize_rows → bulk_insert → finish_run
   - SyncResult data class 包含 run_id, inserted/skipped/errors_count, status
   - 例外處理：標記 sync_run status="failed" 後重新拋出

3. API 層：
   - POST /portfolio/sync 不需 body（從環境變數讀取 Google Sheets 資訊）
   - 回傳 JSON: {run_id, inserted_count, skipped_count, errors_count, status, synced_at}
   - 整合錯誤處理：回傳 500 + 錯誤訊息

4. 測試策略（monkeypatch SheetsClient）：
   - test_first_sync_inserts_all_records: 3 筆全插入
   - test_second_sync_skips_duplicates: 相同資料全跳過（source_hash 去重）
   - test_sync_with_invalid_data: errors_count > 0 但 status=succeeded
   - test_sync_google_sheets_connection_failure: 回傳 500
   - test_sync_creates_sync_run_record: 驗證 sync_runs 表記錄

Tests:
- pytest services/portfolio-service/tests/test_sync_endpoint.py -v
- 驗證方式：
  1. 啟動服務: docker compose up -d --build postgres portfolio-service
  2. 執行 migration: docker compose exec portfolio-service alembic upgrade head
  3. 執行測試: docker compose exec portfolio-service pytest tests/test_sync_endpoint.py -v
  4. 手動驗證（需設定 GOOGLE_SA_JSON）:
     curl -X POST http://localhost:8001/portfolio/sync
  5. 一鍵驗證腳本:
     bash services/portfolio-service/verify_sprint_1-3.sh

Before coding:
- services/portfolio-service/app/repositories/__init__.py (module exports)
- services/portfolio-service/app/repositories/trades_repo.py (118 lines, ON CONFLICT logic)
- services/portfolio-service/app/repositories/sync_runs_repo.py (120 lines, status tracking)
- services/portfolio-service/app/sync_service.py (153 lines, orchestration flow)
- services/portfolio-service/app/main.py (更新：新增 POST /portfolio/sync 端點)
- services/portfolio-service/tests/test_sync_endpoint.py (5 個測試案例，約 280 lines)
- API_CONTRACTS.md (更新：errors_count 欄位說明)
```

### Sprint 1-4: Portfolio 資料庫 Schema 與 Migration
```markdown
Task: 建立 portfolio-service 的資料庫 schema 與 migration 腳本
Repo / Files:
- services/portfolio-service/alembic/versions/001_initial_schema.py
- services/portfolio-service/app/db.py
- services/portfolio-service/app/models.py
- services/portfolio-service/tests/test_db_schema.py
Constraints:
- 使用 Alembic 管理 migration
- 建立 trades 表（參考 API_CONTRACTS.md schema）
- 建立 positions 表（參考 API_CONTRACTS.md schema）
- 建立 sync_runs 表（記錄同步執行）
- 建立必要的 index（user_id, symbol, trade_date）
- 建立 unique constraint 避免重複交易記錄（source_hash）
Tests:
- pytest services/portfolio-service/tests/test_db_schema.py
- 驗證方式：
  1. 啟動 postgres 與 portfolio-service:
     docker compose up -d --build postgres portfolio-service
  2. 執行 migration（必須先執行！）:
     docker compose exec portfolio-service alembic upgrade head
  3. 若遇到 "relation already exists" 錯誤，執行:
     docker compose exec portfolio-service alembic stamp head
  4. 執行測試:
     docker compose exec portfolio-service pytest tests/test_db_schema.py -v
  5. 檢查資料表是否建立:
     docker compose exec postgres psql -U investment -d investment_db -c "\dt"
  6. 或使用一鍵驗證腳本:
     bash services/portfolio-service/verify_setup.sh
Before coding:
- services/portfolio-service/alembic.ini (Alembic 設定)
- services/portfolio-service/alembic/env.py (環境設定)
- services/portfolio-service/alembic/versions/001_initial_schema.py (初始 schema)
- services/portfolio-service/app/db.py (SQLAlchemy engine/session)
- services/portfolio-service/app/models.py (ORM models)
- services/portfolio-service/tests/test_db_schema.py (schema 測試)
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