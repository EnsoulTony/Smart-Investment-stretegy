# Development.md｜開發指南（MVP）

本文件說明 Smart-Investment-Strategy 的開發流程、提示（prompt）模板與一鍵建置命令。所有說明以繁體中文撰寫，確保各階段與 Claude/Aider 協作一致。

## 開發階段與典型工作流

1. **環境初始化**：設定 `.env`、安裝前後端依賴、啟動 Docker Compose。
2. **服務開發**：依據微服務邊界，在對應目錄新增邏輯、測試與文件。
3. **策略模組**：遵循 `Strategy.md` 規則開發或調整 Radar v1.4 插件。
4. **資料契約與 API**：所有輸入輸出需檢查 `API_CONTRACTS.md`。
5. **測試與驗證**：執行 `TESTING.md` 列出的指令，確保健康檢查與單元測試通過。
6. **部署準備**：更新 `CHANGELOG.md`、確認 `DEPLOYMENT.md` 流程、觸發 GitHub Actions。

## 硬隔離規則（必遵守）

- **服務容器不得持有超出職責範圍的敏感連線設定**。
   - 例如：valuation-service **不得**持有 `DATABASE_URL` / `POSTGRES_*` 等 DB 連線資訊。
   - 估值層只能透過 portfolio-service 的 HTTP API 取數。

## 資料庫設定口徑（唯一真相來源）

**設計決策**：portfolio-service **只讀 `DATABASE_URL`**。其他變數僅保留向後相容（不使用）。

**為什麼這樣做**：
- 避免多套 DB 變數造成 VM/容器口徑不一致。
- 避免 `PORTFOLIO_DATABASE_URL` 與 `DATABASE_URL` 指向不同資料庫而難以排查。

**反證 / 推翻條件**（符合任一條才可調整）：
- 未來需要多 DB（例如分庫或讀寫分離）。
- 需要 per-service DB URL（每個服務連不同 DB）。
- 導入 secrets manager 統一管理，並有明確的變數規範文件。

**收斂策略**：
- 保留 `DATABASE_URL` 作為唯一使用來源。
- `PORTFOLIO_DATABASE_URL` 若存在，視為向後相容但**不使用**。
- `POSTGRES_*` 僅供 `postgres` 容器使用，不應被 app 直接讀取。

## PR 自動檢查清單（可複製執行）

**一鍵腳本（fail-fast）**：
```bash
chmod +x tools/pr_check.sh
./tools/pr_check.sh
```

**失敗訊息解讀（rule_id）**：
- `VAL-FT-*`：valuation-service forbidden tokens 命中
- `PORT-FT-*`：portfolio-service 帳務層 forbidden tokens 命中
- `COMPOSE-VAL-*`：valuation-service env allow-list 違規
- `COMPOSE-PORT-*`：portfolio-service env/secret 規則違規
- `PRECHECK-*`：環境前置條件不足（服務未啟動 / 缺工具）

**為何能避免 VM 才爆**：
- `docker compose config` 是展開後「真相來源」，可在本機/CI 提前發現 env 注入錯誤。

**CI / 本機 secrets 覆蓋檔策略**：
- 主檔 [docker-compose.yml](docker-compose.yml) 不引用任何 secrets 來源，避免 CI 缺 env 直接爆。
- 需要 Service Account 時使用覆蓋檔：`-f docker-compose.secrets.yml`。
- 覆蓋檔僅存本機或 CI runtime 生成，不提交到 repo。

### 1) Forbidden tokens 靜態掃描（rg）
```bash
# valuation-service 禁止 DB 直連 tokens
rg -n "sqlalchemy|psycopg2|asyncpg|postgresql://" services/valuation-service

# portfolio-service 帳務層禁止估值/FX tokens
rg -n "valuation|market_value|convert|get_rate" \
   services/portfolio-service/app/position_rebuilder.py \
   services/portfolio-service/app/avg_cost_calculator.py
```

### 2) docker compose config 展開後檢查 env
```bash
# valuation-service：不得出現 DATABASE_URL / POSTGRES_*
docker compose config | sed -n '/valuation-service:/,/^[^ ]/p' | grep -E "DATABASE_URL|POSTGRES_" && exit 1 || echo "valuation-service OK"

# portfolio-service：只允許 DATABASE_URL
docker compose config | sed -n '/portfolio-service:/,/^[^ ]/p' | grep -E "PORTFOLIO_DATABASE_URL|POSTGRES_" && exit 1 || echo "portfolio-service OK"
docker compose config | sed -n '/portfolio-service:/,/^[^ ]/p' | grep -E "DATABASE_URL" && echo "portfolio-service DATABASE_URL OK"
```

### 3) 服務內 pytest（容器內口徑）
```bash
# portfolio-service
docker compose exec -T portfolio-service pytest -q
docker compose exec -T portfolio-service pytest -q --collect-only | tail -n 10

# valuation-service
docker compose exec -T valuation-service pytest -q
docker compose exec -T valuation-service pytest -q --collect-only | tail -n 10
```

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

### Sprint 1-2: 實作 GET /portfolio/positions
```markdown
Task: 實作 portfolio-service 的 GET /portfolio/positions 端點
Repo / Files:
- services/portfolio-service/app/main.py
- services/portfolio-service/app/position_calculator.py
- services/portfolio-service/tests/test_positions.py
Constraints:
- 遵循 API_CONTRACTS.md 定義的 Response schema
- 實作均價法計算邏輯（參考 Strategy.md）
- 計算公式：avg_cost = Σ(buy_price × quantity) / total_quantity
- `u_pnl` 固定為 0（帳務層不做估值）
- 支援 user_id 篩選
Tests:
- pytest services/portfolio-service/tests/test_positions.py
- 驗證方式：
  1. 準備測試資料（trades 表插入多筆買賣記錄）
   2. 呼叫 GET /portfolio/positions?user_id=test-user
  3. 驗證 avg_cost 計算正確
   4. 驗證 u_pnl 固定為 0
Before coding:
- services/portfolio-service/app/main.py (新增 /portfolio/positions 端點)
- services/portfolio-service/app/position_calculator.py (均價法計算邏輯，約 60-100 行)
- services/portfolio-service/app/db.py (新增 positions 查詢與寫入)
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
  - **Hash 版本控制**：CANONICAL_VERSION = "v1" 前綴避免未來規則變動造成衝突
  - compute_source_hash() 包含版本：sha256(f"{version}|{canonical_string}")
- services/portfolio-service/tests/test_trade_normalizer.py (單元測試，約 300 行)
- services/portfolio-service/tests/test_hash_versioning.py (版本控制測試)
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
   - **可觀測性欄位**（v0.2.3+）：
     * sheet_rows_count: 從 Sheets 讀取的總列數
     * normalized_valid_count: 成功轉換為 TradeRecord 的筆數
     * normalized_invalid_count: 格式錯誤筆數（= errors_count）
     * duplicates_count: DB 重複跳過筆數（source_hash 去重）
   - 整合錯誤處理：回傳 500 + 錯誤訊息
   - 日誌輸出：使用 logger.info/warning/exception 記錄關鍵步驟，不記錄敏感資料

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

### Sprint 1-4: 持倉重算端點（Positions Rebuilder）

#### Sprint 1-4.0: 建立重算骨架與最小測試

```markdown
Task: 建立 POST /portfolio/rebuild_positions 端點骨架與測試
Repo / Files:
- services/portfolio-service/app/position_rebuilder.py（新增）
- services/portfolio-service/app/main.py（新增端點）
- services/portfolio-service/app/schemas.py（新增 Request/Response schema）
- services/portfolio-service/tests/test_rebuild_positions_endpoint.py（新增）
- Development.md（更新：新增 Sprint 1-4.0 說明）

Constraints:
- 本階段只建立骨架，不實作均價法計算邏輯
- 端點須能正常回應，回傳固定結構：{"status": "succeeded", "rebuilt_symbols_count": 0, "warnings": []}
- 架構分層：Router → Service → Calculator（下階段） → Repository
- 保留 DB session 依賴注入介面（即使本階段不使用）
- 繁體中文註解，說明下階段會加入的邏輯點

Tests:
- pytest services/portfolio-service/tests/test_rebuild_positions_endpoint.py -v
- 驗證方式：
  1. 啟動服務（若需要）: docker compose up -d portfolio-service
  2. 執行測試: docker compose exec portfolio-service pytest tests/test_rebuild_positions_endpoint.py -v
  3. 或執行完整測試套件: docker compose exec portfolio-service pytest -q
  4. 預期結果：
     - test_rebuild_positions_endpoint_exists: ✓ 端點存在並回應 200
     - test_rebuild_positions_response_structure: ✓ 回應包含 status, rebuilt_symbols_count, warnings
     - test_rebuild_positions_status_succeeded: ✓ status=succeeded, count=0, warnings=[]
     - test_rebuild_positions_missing_user_id: ✓ 缺少 user_id 回傳 422
     - test_rebuild_positions_empty_user_id: ✓ 空 user_id 回傳 500
     - test_rebuild_positions_with_different_user_ids: ✓ 不同 user_id 都能正常回應

Before coding:
- services/portfolio-service/app/position_rebuilder.py (新增 150+ 行，包含完整註解與 TODO 標記)
- services/portfolio-service/app/main.py (新增 POST /portfolio/rebuild_positions 端點，約 30 行)
- services/portfolio-service/app/schemas.py (新增 RebuildPositionsRequest/Response，約 15 行)
- services/portfolio-service/tests/test_rebuild_positions_endpoint.py (新增 6 個測試，約 100 行)
- Development.md (新增 Sprint 1-4.0 段落)
```

**下階段預告（Sprint 1-4.1）**：
- 實作均價法純函數 `calculate_avg_cost()`
- 讀取 trades 表並按 symbol 分組計算
- 寫入 positions 表
- 測試實際計算邏輯的正確性

#### Sprint 1-4.1: 均價法（Weighted Average Cost）純函數計算器與完整單元測試

```markdown
Task: 實作均價法計算器（純函數）與完整單元測試
Repo / Files:
- services/portfolio-service/app/avg_cost_calculator.py（新增）
- services/portfolio-service/app/schemas.py（更新：TradeRecord）
- services/portfolio-service/tests/test_avg_cost_calculator.py（新增）
- Development.md（更新：新增 Sprint 1-4.1 說明）

Constraints:
- 計算器為純函數（無副作用，不讀寫 DB）
- 輸入：List[TradeRecord]（已排序）
- 輸出：AvgCostState（qty, avg_cost, realized_pnl, total_fee）
- 支援 BUY/SELL 邏輯：
  - BUY: 增加持倉，更新均價
  - SELL: 減少持倉，實現損益（avg_cost 不變）
- 防禦性檢查：賣出數量不可超過持倉
- 精確計算：使用 Decimal 避免浮點誤差
- 手續費處理：BUY 增加成本基礎，SELL 減少收益

Tests:
- pytest services/portfolio-service/tests/test_avg_cost_calculator.py -v
- 驗證方式：
  1. docker compose up -d --build portfolio-service
  2. docker compose exec portfolio-service pytest tests/test_avg_cost_calculator.py -v
  3. 預期：12 個測試全部通過（涵蓋基本場景、SELL 邏輯、手續費、防禦性檢查、邊界情況）

Before coding:
- services/portfolio-service/app/avg_cost_calculator.py（約 175 行，包含完整註解與數學公式說明）
- services/portfolio-service/tests/test_avg_cost_calculator.py（12 個測試，約 450 行）
```

#### Sprint 1-4.2: DB 查詢整合、預覽重算端點與測試加固

```markdown
Task: 把均價法計算器接上 DB 查詢與分組排序，並提供「預覽重算」端點與測試
Repo / Files:
- services/portfolio-service/app/trades_repository.py（新增）
- services/portfolio-service/app/position_rebuilder.py（更新：新增 preview_rebuild）
- services/portfolio-service/app/main.py（新增 POST /portfolio/rebuild_positions/preview 端點）
- services/portfolio-service/tests/test_rebuild_positions_preview.py（新增）
- Development.md（更新：新增 Sprint 1-4.2 說明與測試加固指南）

Constraints:
- 本階段只做「讀 DB trades → 分組排序 → 呼叫 compute_avg_cost → 回傳預覽結果」
- 不寫入 positions（upsert 留到 Sprint 1-4.3）
- 不接 Google Sheets、不改 sync、不中斷既有端點
- 計算仍以 (user_id, symbol, asset_ccy) 分組
- trades 必須以 trade_date ASC, created_at ASC 排序（確保穩定性）

Tests:
- pytest services/portfolio-service/tests/test_rebuild_positions_preview.py -v
- 驗證方式：
  1. 重建容器（因為 tests/ 被 COPY 進 image）:
     docker compose up -d --build portfolio-service
  2. 執行預覽端點測試:
     docker compose exec portfolio-service pytest tests/test_rebuild_positions_preview.py -v
  3. 執行完整測試套件:
     docker compose exec portfolio-service pytest -q
  4. 預期：55 個測試全部通過（48 既有 + 7 個預覽測試）

Before coding:
- services/portfolio-service/app/trades_repository.py（約 77 行，二級排序邏輯）
- services/portfolio-service/app/position_rebuilder.py（新增 preview_rebuild 函數，約 150 行）
- services/portfolio-service/app/main.py（新增預覽端點，約 70 行）
- services/portfolio-service/tests/test_rebuild_positions_preview.py（7 個測試，約 330 行）
```

**測試加固指南（Sprint 1-4.2 必讀）**

當測試涉及 FastAPI TestClient + Database Session + Transaction（SAVEPOINT）時，需特別注意以下四點：

**1. 必須 override get_db dependency**

```python
from app.db import get_db
from app.main import app

@pytest.fixture
def client(db_session):
    """讓 API 與測試共用同一個 db_session（避免 SAVEPOINT 隔離）"""
    def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:  # 使用 context manager
        yield c
    app.dependency_overrides.clear()
```

**為什麼需要？**
- conftest.py 的 `db_session` 使用 SAVEPOINT（nested transaction）
- 測試中的 `commit()` 只提交到 SAVEPOINT，不是真正寫入 DB
- 如果 TestClient 用另一個 session（預設行為），會因為 transaction 隔離看不到測試插入的資料
- 症狀：API 查詢回傳空結果（`symbols = []`），但測試插入的資料確實存在

**2. 必須使用 context manager**

```python
with TestClient(app) as c:
    yield c
```

確保 TestClient 的 lifespan 正確啟停，避免狀態殘留。

**3. 插入後必須自我驗證**

```python
# 插入測試資料
trade = Trade(user_id="test_user", symbol="AAPL", ...)
db_session.add(trade)
db_session.commit()

# 自我驗證：確認資料真的插入成功（避免把錯誤歸因到 API）
count = db_session.query(Trade).filter_by(user_id="test_user").count()
assert count == 1, f"插入失敗或 rollback 太早，預期 1 筆，實際：{count}"

# 才呼叫 API
response = client.post("/portfolio/rebuild_positions/preview", ...)
```

**4. fixture teardown 必須清除 dependency_overrides**

```python
@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()  # 必須清除，避免污染其他測試
```

可選：加上 assert 確保清除成功

```python
app.dependency_overrides.clear()
assert len(app.dependency_overrides) == 0, "dependency_overrides 未清除乾淨"
```

**重建容器的必要性**

因為 Dockerfile COPY 了 `tests/` 目錄，修改測試檔案需要重建容器：

```bash
docker compose up -d --build portfolio-service
```

### Sprint 1-5: Portfolio 資料庫 Schema 與 Migration
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
   - 呼叫 GET /portfolio/positions 確認均價法計算
   - 呼叫 GET /portfolio/trades/summary 確認資料可查詢
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

## Sprint 1-4 系列：FX 模組與估值層邊界（Architecture Guardrails）

### Sprint 邊界總覽

| Sprint | 目標 | 允許範圍 | 硬禁止項目 |
|--------|------|---------|-----------|
| **1-4.A** | FX 模組介面定義 | 介面 + Stub（同幣別可用、跨幣別必炸） | 真實 Provider、HTTP 請求、匯率 cache、估值計算 |
| **1-4.3** | 帳務層重算 | positions 表寫入、均價計算、`u_pnl=0` | 估值計算、匯率折算、呼叫 FX 模組、新增估值欄位 |
| **1-4.B** | 估值層實作 | 匯率 Provider、cache、`valuation_ccy` 欄位、市值計算 | 估值邏輯散落到非 `valuation_service.py` |

---

### Sprint 1-4.A：FX 模組介面（已完成）

**交付物**：
- ✅ `app/fx/interfaces.py`：`FxProvider` 抽象基類
- ✅ `app/fx/stub_provider.py`：Stub 實作（同幣別可用、跨幣別拋例外）
- ✅ `app/fx/types.py`：`Currency`、`ExchangeRate` 型別定義
- ✅ `app/fx/__init__.py`：`get_fx_provider()` factory 唯一入口
- ✅ 20 個測試通過（14 個 Stub 測試 + 6 個 Guardrails 測試）

**驗收命令**：
```bash
# 測試 1：FX 介面與 Stub
docker compose exec -T portfolio-service pytest -q tests/test_fx.py
# 期望：14 passed

# 測試 2：所有 FX 相關測試（含 Guardrails）
docker compose exec -T portfolio-service pytest -q -k fx
# 期望：20 passed, 55 deselected
```

**可證偽證據**（測試收集）：
```bash
docker compose exec -T portfolio-service pytest -q -k fx --collect-only
# 輸出：20/75 tests collected (55 deselected)
# 來源：
# - tests/test_fx.py: 14 tests (Stub/Factory/Integration)
# - tests/test_fx_guardrails.py: 6 tests (架構邊界檢查)
```

**硬禁止項目**（Sprint 1-4.A 階段）：
- ❌ 真實匯率 Provider（Yahoo Finance、央行牌告、Alpha Vantage）
- ❌ HTTP 請求套件（requests、httpx）
- ❌ 匯率 cache（Redis、DB rates 表）
- ❌ 估值計算邏輯

---

### Sprint 1-4.3：帳務層 Positions 寫回（已完成）

**範圍**（Scope）：
- ✅ `POST /portfolio/rebuild_positions`：從 `trades` 表重算並**寫入** `positions` 表
- ✅ 只做帳務：`quantity`（數量）、`avg_cost`（均價）、`realized_pnl`（已實現損益）
- ❌ **不做估值**：不計算 `u_pnl`（未實現損益固定為 0）
- ❌ **不做匯率折算**：不觸碰 `target_ccy`、不呼叫 FX 模組

**依賴**（Dependencies）：
- 📖 只讀：`trades` 表（按 `user_id` + `symbol` + `asset_ccy` 分組）
- ✍️ 只寫：`positions` 表（UPSERT on conflict，刪除零持倉）
- 🚫 不新增 Schema：沿用現有欄位（`quantity`, `avg_cost`, `realized_pnl`, `u_pnl`, `last_updated_at`）
- 🚫 不訪問其他服務：純 portfolio-service 內部運算

**交付物**：
- ✅ `position_rebuilder.py`：從 trades 重算 positions 並寫入 DB
- ✅ `avg_cost_calculator.py`：均價法計算器（純函數）
- ✅ UPSERT 冪等性：重複執行不產生重複紀錄
- ✅ 零持倉刪除：賣完後自動清理 positions 表
- ✅ 測試覆蓋：買入、賣出、賣光、冪等性、空用戶

---

### Sprint: Prevent "Empty Rebuild"（前置條件檢查，已完成）

**背景**（Why）：
在 VM / 新環境常見「rebuild_positions 成功但 symbols_count=0（其實是 trades 尚未 sync）」的問題，使用者誤判「rebuild 成功」但其實沒有實質效果。

**目標**（What）：
把前置條件變成系統合約，而不是操作習慣。前置條件不足就要「可證偽地」失敗，不准靜默成功。

**解決方案**：
1. **新增 `require_trades` 參數**：
   - `POST /portfolio/rebuild_positions?require_trades=true`
   - 當 trades_count=0 時回傳 **409 Conflict**（而非靜默成功）
   - 回傳包含可證偽的 `evidence.verification_sql`

2. **新增輕量探針端點**：
   - `GET /portfolio/trades/summary?user_id=...`
   - 回傳 `trades_count`, `symbols_count`, `min_trade_date`, `max_trade_date`
   - 讓 automation 腳本先確認前置條件

**技術決策**：
- ✅ `require_trades` 預設 `false`（保持向後相容）
- ✅ 前置條件失敗回傳 409 Conflict（而非 422 或 500）
- ✅ Evidence 包含 SQL 語句供人工驗證（可證偽）
- 🚫 rebuild_positions 不得在內部偷偷呼叫 sync（避免副作用）
- 🚫 valuation-service 禁止 DB 直連（microservices 邊界）

**交付物**：
- ✅ `trades_repository.py`：`count_trades_for_user()`, `count_distinct_symbols_for_user()`
- ✅ `schemas.py`：`TradesSummaryResponse`
- ✅ `main.py`：`GET /portfolio/trades/summary`, `rebuild_positions` 增加 `require_trades` 參數
- ✅ `test_trades_summary_and_require_trades.py`：6 個測試用例，全部通過

**驗收證據**：

#### 1. 測試套件通過

```bash
docker compose exec -T portfolio-service \
  pytest tests/test_trades_summary_and_require_trades.py -v
# 期望：6 passed
# - test_trades_summary_empty_returns_zero
# - test_trades_summary_after_insert_returns_counts
# - test_rebuild_positions_require_trades_blocks_when_empty（409 Conflict）
# - test_rebuild_positions_require_trades_proceeds_when_has_trades
# - test_rebuild_positions_default_require_trades_false_allows_empty
# - test_evidence_verification_sql_contains_all_required_fields
```

#### 2. API 行為驗證

```bash
# 情境 A：trades 為空 + require_trades=true（應被擋）
curl -s -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=empty_user&require_trades=1"
# HTTP 409, detail.status="precondition_failed", evidence.trades_count=0

# 情境 B：trades 為空 + require_trades=false（靜默成功，保持相容）
curl -s -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=empty_user&require_trades=0" | jq .status
# "succeeded"（symbols_count=0）

# 情境 C：trades/summary 輕量探針
curl -s "http://localhost:8001/portfolio/trades/summary?user_id=tony" | jq
# 回傳 trades_count, symbols_count, min_trade_date, max_trade_date, evidence
```

#### 3. Evidence 可證偽性

```bash
# 取得 verification_sql
curl -s "http://localhost:8001/portfolio/trades/summary?user_id=tony" | jq .evidence.verification_sql

# 手動執行 SQL 驗證
docker compose exec -T postgres psql -U investment -d investment_db -c \
"select count(*) from trades where user_id='tony';"
# 數量應與 API 回傳的 trades_count 一致

docker compose exec -T postgres psql -U investment -d investment_db -c \
"select count(distinct symbol) from trades where user_id='tony';"
# 數量應與 API 回傳的 symbols_count 一致
```

**禁止事項**（Hard Boundaries）：
- 🚫 rebuild_positions 不得在內部偷偷呼叫 sync（避免副作用、隱性耗時）
- 🚫 require_trades 預設不得為 true（向後相容）
- 🚫 valuation-service 禁止 DB 直連（已有 guardrails 測試確保）

**故障排除**：
1. **require_trades=1 但還是回 succeeded（應該回 409）**：
   - 檢查 trades 是否真的為空：`select count(*) from trades where user_id='...'`
   - 檢查 `count_trades_for_user()` 是否被正確呼叫

2. **trades/summary 回傳 404**：
   - 檢查容器是否重建：`docker compose up -d --build portfolio-service`
   - 檢查啟動日誌：`docker compose logs -f portfolio-service`

3. **evidence.verification_sql 缺失**：
   - 檢查 [schemas.py](services/portfolio-service/app/schemas.py) 的 `TradesSummaryResponse`
   - 檢查端點回傳 dict 是否包含 `evidence` 和 `verification_sql`

---

### Sprint 1-4.3 原始驗收證據（Positions 寫回）

**驗收證據**（Acceptance Evidence）：

#### 1. 測試套件通過

```bash
# 所有測試
docker compose exec -T portfolio-service pytest -q
# 期望：93 passed, 1 skipped（無警告）

# rebuild 相關測試（含寫入、冪等性、邊界）
docker compose exec -T portfolio-service pytest -q -k rebuild
# 期望：16+ passed
```

#### 2. API 回傳欄位驗證

```bash
# 呼叫 rebuild_positions（query 參數）
curl -s -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq

# 預期輸出包含：
# {
#   "status": "succeeded",
#   "user_id": "tony",
#   "symbols_count": <int>,           # 重算的標的數
#   "upserted_count": <int>,          # 寫入/更新筆數
#   "deleted_or_zeroed_count": <int>, # 刪除的零持倉筆數
#   "run_id": "<uuid>",               # 執行追蹤 ID
#   "evidence": {
#     "positions_columns": [           # positions 表欄位清單
#       "user_id", "symbol", "asset_ccy",
#       "quantity", "avg_cost", "realized_pnl",
#       "u_pnl", "last_updated_at"
#     ]
#   }
# }
```

#### 3. 資料庫驗證（psql）

```bash
# 查看 positions 表結構
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "\d positions"

# 預期欄位：
# - user_id (text)
# - symbol (text)
# - asset_ccy (text)
# - quantity (numeric)
# - avg_cost (numeric)
# - realized_pnl (numeric)
# - u_pnl (numeric)         ← 未實現損益，當前固定 0
# - last_updated_at (timestamp)

# 查看實際寫入資料
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "SELECT user_id, symbol, asset_ccy, quantity, avg_cost, realized_pnl, u_pnl FROM positions LIMIT 5;"

# 預期：
# - quantity、avg_cost、realized_pnl 有真實數值
# - u_pnl 固定為 0（不做估值）
```

**禁止規則**（Hard Boundaries）：

1. **帳務層禁止匯率邏輯**：
   ```bash
   # 檢查：帳務層不呼叫 FX 模組
   grep -rn "from app.fx" services/portfolio-service/app/position_rebuilder.py
   # 期望：（空）
   
   # 檢查：不做折算（最陰險的發散來源）
   grep -rn "fx\.convert\|fx\.get_rate\|target_ccy" \
     services/portfolio-service/app/position_rebuilder.py \
     services/portfolio-service/app/domain/avg_cost_calculator.py
   # 期望：（空）
   ```

2. **估值層禁止 DB 直連**：
   ```bash
   # valuation-service 只能透過 HTTP 呼叫 portfolio-service
   docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
   # 期望：5 passed（禁止 DB driver、SQLAlchemy、連線字串）
   ```

3. **Position 表無估值欄位**（Sprint 1-4.3 階段）：
   - ❌ 禁止新增：`valuation_ccy`, `market_value`, `valuation_date`, `market_price`
   - ✅ 允許：`u_pnl`（未實現損益）欄位存在但固定為 0，預留未來擴充

**Troubleshooting**（當 positions 寫入數量/金額不符時）：

1. **檢查 trades 來源筆數**：
   ```bash
   docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
     -c "SELECT user_id, symbol, asset_ccy, COUNT(*), SUM(quantity) \
         FROM trades WHERE user_id='tony' GROUP BY 1,2,3;"
   # 確認來源數據是否正確
   ```

2. **檢查分組鍵與排序**：
   ```bash
   # position_rebuilder.py 必須按 (user_id, symbol, asset_ccy) 分組
   # 並按 trade_date ASC 排序計算均價
   grep -A 5 "group_by\|order_by" services/portfolio-service/app/position_rebuilder.py
   ```

3. **檢查 UPSERT 衝突鍵**：
   ```sql
   -- 確認 positions 表的唯一約束
   SELECT conname, pg_get_constraintdef(oid)
   FROM pg_constraint
   WHERE conrelid = 'positions'::regclass AND contype = 'u';
   -- 預期：(user_id, symbol, asset_ccy) 唯一索引
   ```

4. **檢查零持倉刪除邏輯**：
   ```python
   # position_rebuilder.py 應包含：
   # if final_quantity == 0:
   #     session.query(Position).filter(...).delete()
   ```

5. **驗證冪等性**：
   ```bash
   # 連續執行兩次，結果應相同
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony'
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony'
   # 比對 symbols_count、upserted_count 應一致
   ```

---

### Sprint 1-4.B：估值層實作（未來）

**目標**：實作真實匯率資料源與估值計算

**允許項目**（僅限 Sprint 1-4.B）：
- ✅ 真實匯率 Provider（Yahoo Finance、央行牌告、Alpha Vantage）
- ✅ 匯率 cache 機制（Redis、DB rates 表）
- ✅ 估值服務（`valuation_service.py`）
- ✅ 透過 Alembic migration 新增 `valuation_ccy` / `market_value` 欄位
- ✅ 市值計算邏輯（`quantity * market_price * fx_rate`）

**硬禁止項目**（即使在 Sprint 1-4.B）：
- ❌ 估值邏輯散落到非 `valuation_service.py` 的檔案
- ❌ 直接在 `position_rebuilder.py` 呼叫 FX 模組（維持帳務層純淨）
- ❌ 不經 Alembic migration 直接 ALTER TABLE（SQL injection 風險）

**Migration 範例**（Sprint 1-4.B 實作時使用）：

```python
# alembic/versions/xxxx_sprint_1_4_b_add_valuation_fields.py
"""
Sprint 1-4.B: Add valuation fields to positions table

Revision ID: xxxx
Revises: yyyy
Create Date: 2026-01-xx
"""

def upgrade() -> None:
    # 新增 valuation_ccy 欄位（預設 TWD）
    op.add_column('positions', 
        sa.Column('valuation_ccy', sa.Text(), nullable=False, server_default='TWD'))
    # 新增 market_value 欄位（預設 0）
    op.add_column('positions', 
        sa.Column('market_value', sa.Numeric(), nullable=False, server_default='0'))

def downgrade() -> None:
    # 可回退
    op.drop_column('positions', 'market_value')
    op.drop_column('positions', 'valuation_ccy')
```

**驗收命令（可證偽）**：
```bash
# 估值層健康檢查
curl -s http://localhost:8005/health | jq

# 成功案例（trades 有資料）
curl -s "http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=USD&as_of=2026-01-24" | jq

# 失敗案例（trades_count=0）
curl -s -i "http://localhost:8005/valuation/portfolio?user_id=empty_user" | sed -n '1,20p'
```

**成功輸出範例（節錄）**：
```json
{
   "status": "succeeded",
   "evidence": {
      "positions_count": 1,
      "positions_hash": "<sha256>",
      "trades_count": 2,
      "distinct_symbols_count": 1,
      "providers": {"price_provider": "stub", "fx_provider": "stub"}
   }
}
```

**失敗輸出範例（節錄）**：
```json
{
   "detail": {
      "status": "precondition_failed",
      "evidence": {"trades_count": 0}
   }
}
```

---

### FX 模組擴充檢查清單（Sprint 1-4.B 準備）

**開始 Sprint 1-4.B 之前，必須確認**：

```bash
# 1. 確認 Sprint 1-4.3 完成且穩定
docker compose exec -T portfolio-service pytest -q
# 期望：78 passed（或當前總數）

# 2. 確認帳務層不呼叫 FX
grep -rn "from app.fx" services/portfolio-service/app   --include="*.py"   --exclude-dir=fx   --exclude-dir=__pycache__
# 期望：（空）

# 3. 確認 Position 表無估值欄位
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions'    AND column_name ~ '(valuation|market_value)';"
# 期望：(0 rows)

# 4. 確認 u_pnl 欄位存在（帳務層固定填 0）
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions' AND column_name='u_pnl';"
# 期望：'0'::numeric
```

**Sprint 1-4.B 實作步驟**：

1. **建立估值服務骨架**
   ```bash
   touch services/portfolio-service/app/valuation_service.py
   touch services/portfolio-service/tests/test_valuation_service.py
   ```

2. **選擇匯率資料源（優先順序）**
   - Option 1: Yahoo Finance（免費、即時、全球覆蓋）
   - Option 2: 央行牌告（官方、可靠、僅台幣對主要貨幣）
   - Option 3: Alpha Vantage（需 API key、有 rate limit）

3. **實作匯率 Provider**
   ```bash
   touch services/portfolio-service/app/fx/yahoo_provider.py
   touch services/portfolio-service/tests/test_yahoo_provider.py
   ```

4. **新增估值欄位（透過 Alembic migration）**
   ```bash
   cd services/portfolio-service
   alembic revision -m "sprint_1_4_b_add_valuation_fields"
   # 編輯 migration 檔案
   alembic upgrade head
   ```

5. **實作估值計算邏輯**
   - 讀取 positions 表
   - 透過 `get_fx_provider()` 取得匯率
   - 計算 `market_value = quantity * market_price * fx_rate`
   - 更新 positions 表（使用 `valuation_ccy = 'TWD'`）

6. **驗收測試**
   ```bash
   docker compose exec -T portfolio-service pytest -q tests/test_valuation_service.py
   docker compose exec -T portfolio-service pytest -q tests/test_yahoo_provider.py
   ```

---

### 架構圖解

```
┌─────────────────────────────────────────────────────────────┐
│                    Portfolio Service                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐          ┌────────────────────┐       │
│  │ Accounting Layer│          │ Valuation Layer    │       │
│  │ (Sprint 1-4.3)  │          │ (Sprint 1-4.B)     │       │
│  ├─────────────────┤          ├────────────────────┤       │
│  │ ❌ 禁止呼叫 FX  │          │ ✅ 可呼叫 FX       │       │
│  │ - rebuild_*     │          │ - valuation_*      │       │
│  │ ❌ 禁止折算邏輯 │          │ ✅ 可做估值折算     │       │
│  │ - fx.convert()  │          │ - fx.get_rate()    │       │
│  │ - fx.get_rate() │          │ - target_ccy 參數   │       │
│  │ - avg_cost_*    │          │ - market_value_*   │       │
│  └─────────────────┘          └────────┬───────────┘       │
│                                        │                   │
│                    ┌───────────────────▼──────────────┐    │
│                    │   FX Module (Sprint 1-4.A)       │    │
│                    ├──────────────────────────────────┤    │
│                    │ get_fx_provider() ← 唯一入口     │    │
│                    │ ├── StubFxProvider (當前)        │    │
│                    │ └── YahooFxProvider (Sprint 1-4.B)│   │
│                    └──────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Sprint 1-4.B：估值層完整實作（已完成）

### 交付物總覽

| 檔案 | 說明 |
|------|------|
| `services/valuation-service/app/main.py` | 估值 API（含 totals + positions + evidence） |
| `services/valuation-service/app/providers.py` | 抽象介面 + Stub 實作（可替換） |
| `services/valuation-service/app/guardrails.py` | Runtime guard（禁止 DB env 注入） |
| `services/valuation-service/app/portfolio_client.py` | HTTP client（取代 DB 直連） |
| `services/valuation-service/tests/test_valuation_portfolio.py` | API 測試（409/200/JSON 格式） |
| `services/valuation-service/tests/test_runtime_guard_no_db_env.py` | Runtime guard 測試 |
| `tools/pr_check.sh` | PR 自動檢查腳本（12 項檢查） |

### 最短跑通流程

```bash
# 1. 確保服務啟動
docker compose up -d portfolio-service valuation-service

# 2. 同步交易資料（如果需要）
./tools/portfolio_refresh.sh tony

# 3. 呼叫估值 API
curl -s "http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=USD" | python3 -m json.tool
```

### API 回應結構（Sprint 1-4.B）

**成功回應（HTTP 200）**：
```json
{
  "status": "succeeded",
  "user_id": "tony",
  "base_ccy": "USD",
  "as_of": "2026-01-25",
  "totals": {
    "market_value": 1500.0,
    "cost_value": 1000.0,
    "unrealized_pnl": 500.0
  },
  "positions": [
    {
      "symbol": "AAPL",
      "asset_ccy": "USD",
      "quantity": 10.0,
      "avg_cost": 100.0,
      "cost_value": 1000.0,
      "price": 150.0,
      "price_ccy": "USD",
      "market_value": 1500.0,
      "unrealized_pnl": 500.0
    }
  ],
  "evidence": {
    "decision": "proceed",
    "precondition_snapshot": {
      "trades_count": 2,
      "distinct_symbols_count": 1
    },
    "verification": {
      "portfolio_service_endpoints_called": [
        "GET /portfolio/trades/summary?user_id=tony",
        "GET /portfolio/positions?user_id=tony"
      ],
      "trades_summary_sql": {...},
      "as_of": "2026-01-25"
    },
    "providers": {
      "price_provider": "stub",
      "price_provider_version": "1.4.B",
      "fx_provider": "stub",
      "fx_provider_version": "1.4.B"
    },
    "positions_count": 1,
    "positions_hash": "<sha256>",
    "masked_env_keys": ["HOME=***", "PATH=***", ...]
  }
}
```

**前置條件失敗（HTTP 409）**：
```json
{
  "detail": {
    "status": "precondition_failed",
    "user_id": "empty_user",
    "message": "trades_count=0;請先執行 sync",
    "evidence": {
      "decision": "blocked_precondition",
      "trades_count": 0,
      "distinct_symbols_count": 0,
      "verification_sql": {...},
      "portfolio_service_endpoints_called": [...],
      "masked_env_keys": [...]
    }
  }
}
```

### 驗收命令（可證偽）

```bash
# 1. 健康檢查
curl -s http://localhost:8005/health | python3 -m json.tool

# 2. 估值 API（成功案例）
curl -s "http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=USD" | python3 -m json.tool

# 3. 估值 API（失敗案例 - 409）
curl -s -w "\nHTTP_CODE=%{http_code}\n" "http://localhost:8005/valuation/portfolio?user_id=empty_user"

# 4. 測試套件
docker compose exec -T valuation-service pytest -q

# 5. Runtime guard 注入測試
docker compose run --rm -e DATABASE_URL=x valuation-service python -c "from app.guardrails import check_and_exit; check_and_exit()"
# 預期：non-zero exit，輸出不含 DATABASE_URL 的 value

# 6. PR 自動檢查（一鍵）
./tools/pr_check.sh
```

### PR 自動檢查清單

執行 `./tools/pr_check.sh` 會依序檢查：

| # | 檢查項目 | rule_id |
|---|---------|---------|
| 1 | valuation-service forbidden tokens | VAL-FT-1 |
| 2 | portfolio-service accounting forbidden tokens | PORT-FT-1 |
| 3 | valuation-service env allow-list | COMPOSE-VAL-ALLOWLIST |
| 4 | portfolio-service env checks | COMPOSE-PORT-* |
| 5 | Services running | PRECHECK-SVC-RUNNING |
| 6 | Runtime env sanity | RUNTIME-VAL-DBENV |
| 7 | Runtime guard injection test | RUNTIME-GUARD-* |
| 8 | API JSON contract | API-JSON-* |
| 9-12 | pytest (portfolio/valuation) | - |

**失敗訊息解讀**：
- `VAL-FT-*`：valuation-service 出現禁止的 DB token
- `PORT-FT-*`：portfolio-service 帳務層出現禁止的估值 token
- `COMPOSE-VAL-*`：valuation-service env 配置違規
- `COMPOSE-PORT-*`：portfolio-service env/secret 違規
- `RUNTIME-*`：運行時 guardrail 違規
- `API-JSON-*`：API 回應不是有效 JSON
- `PRECHECK-*`：前置條件不足

### 為何能避免 VM 才爆

1. **docker compose config 是展開後真相來源**
   - 本機 `.env` 可能包含所有變數，但 `docker-compose.yml` 選擇性注入
   - `docker compose config` 顯示的是 VM 實際收到的配置
   - pr_check.sh 會驗證 valuation-service 只收到 allow-list 內的 env

2. **Runtime guard 在啟動時檢查**
   - 即使 compose config 正確，若有人手動注入 DB env，guardrails 會阻斷
   - evidence 只顯示遮罩後的 key，不洩漏 value

3. **API JSON 合約檢查**
   - 使用 `python3 -c "import json; json.loads(...)"` 而非 jq
   - 能抓到回傳 dict repr / traceback / HTML 的情況

---

## 注意事項

- 所有程式碼與文件須維持繁體中文描述。
- 每次修改必須更新 `CHANGELOG.md`，並在 PR 中附測試結果。
- 與 AI 協作者（Claude、Aider）合作時，務必遵守 `RUNBOOK-AI-GUARDRAILS`。