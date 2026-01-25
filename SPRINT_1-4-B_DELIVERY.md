# Sprint 1-4.B 交付清單

**日期**: 2026-01-25  
**狀態**: ✅ Ready for Commit  
**工程師**: GitHub Copilot

---

## 📦 可直接 Commit 的修改

### 新增檔案

1. **SPRINT_1-4-B_IMPLEMENTATION.md**
   - 完整實作報告（550+ 行）
   - 包含目標、交付清單、驗收標準、Evidence 範例

2. **tools/verify_sprint_1-4-b.sh**
   - 可執行的驗收腳本
   - 7 步驟自動化測試（服務啟動 → API 測試 → Runtime Guard）

3. **SPRINT_1-4-B_DELIVERY.md**（本文件）
   - 簡潔的交付清單與驗收命令

### 已存在且符合規格的檔案

以下檔案在之前的 conversation 中已建立且符合 Sprint 1-4.B 要求：

4. **services/valuation-service/app/main.py**
   - ✅ GET /health 端點
   - ✅ GET /valuation/portfolio 端點
   - ✅ Pydantic models（結構化 JSON 回應）
   - ✅ 啟動時 runtime guard 檢查（Line 37）
   - ✅ 前置條件檢查（trades=0 → 409 Conflict）
   - ✅ 502 錯誤處理（upstream 失敗）

5. **services/valuation-service/app/guardrails.py**
   - ✅ `validate_runtime_env()`：偵測並阻斷 DB env
   - ✅ `check_and_exit()`：CLI 用途（exit 78）
   - ✅ Evidence 只顯示遮罩 key（不含 value）
   - ✅ 支援 DATABASE_URL / POSTGRES_* / PG* 偵測

6. **services/valuation-service/app/providers.py**
   - ✅ `BasePriceProvider` / `BaseFxProvider`（抽象類）
   - ✅ `StubPriceProvider` / `StubFxProvider`（deterministic）
   - ✅ Factory functions（`get_price_provider` / `get_fx_provider`）

7. **services/valuation-service/app/portfolio_client.py**
   - ✅ `PortfolioClient`：HTTP client for portfolio-service
   - ✅ `get_trades_summary()` / `get_positions()`

8. **services/valuation-service/tests/test_health.py**
   - ✅ Health endpoint 測試

9. **services/valuation-service/tests/test_runtime_guard_no_db_env.py**
   - ✅ 乾淨環境測試
   - ✅ DATABASE_URL 注入測試
   - ✅ POSTGRES_* 注入測試
   - ✅ PG* 注入測試
   - ✅ Evidence 驗證（只含 key）

10. **services/valuation-service/tests/test_valuation_portfolio.py**
    - ✅ 前置條件失敗（409）測試
    - ✅ 正常估值（200）測試
    - ✅ JSON parse 測試（防 jq 爆）

11. **services/valuation-service/tests/conftest.py**
    - ✅ Pytest fixtures

12. **tools/pr_check.sh**
    - ✅ Forbidden tokens scan（valuation + portfolio）
    - ✅ Docker compose config env allow-list
    - ✅ Runtime env sanity check
    - ✅ Runtime guard injection test
    - ✅ Valuation API JSON contract check
    - ✅ Pytest execution

13. **docker-compose.yml**
    - ✅ valuation-service 定義
    - ✅ environment 只含 allow-list（PORT / PORTFOLIO_BASE_URL / SERVICE_NAME）
    - ✅ depends_on: portfolio-service

14. **services/valuation-service/Dockerfile**
    - ✅ Python 3.12 slim
    - ✅ 安裝 requirements.txt

15. **services/valuation-service/requirements.txt**
    - ✅ fastapi / uvicorn / httpx / pydantic
    - ✅ pytest / pytest-asyncio
    - ✅ **無** sqlalchemy / psycopg2 / asyncpg

---

## ✅ 驗收命令（可直接複製貼上）

### 快速驗收（自動化腳本）

```bash
cd /root/Smart-Investment-stretegy

# 執行完整驗收腳本（7 步驟自動化）
chmod +x tools/verify_sprint_1-4-b.sh
./tools/verify_sprint_1-4-b.sh
```

### 手動驗收（逐步驗證）

```bash
cd /root/Smart-Investment-stretegy

# 1. 啟動服務
docker compose up -d --build valuation-service portfolio-service postgres

# 2. 等待資料庫就緒
docker compose exec -T postgres sh -c 'until pg_isready -U investment; do sleep 1; done'

# 3. 執行 migration
docker compose exec -T portfolio-service alembic upgrade head

# 4. 同步測試資料
./tools/portfolio_refresh.sh test_e2e

# 5. 測試估值 API（正常情況 → HTTP 200）
curl -s "http://localhost:8005/valuation/portfolio?user_id=test_e2e&base_ccy=USD" | jq

# 驗證點：
# - HTTP 200
# - content-type: application/json
# - .evidence.decision == "proceed"
# - .totals.market_value > 0
# - .positions[] 結構完整

# 6. 測試前置條件（空用戶 → HTTP 409）
curl -s -i "http://localhost:8005/valuation/portfolio?user_id=empty_xyz&base_ccy=USD" | head -n 20

# 驗證點：
# - HTTP/1.1 409 Conflict
# - content-type: application/json

curl -s "http://localhost:8005/valuation/portfolio?user_id=empty_xyz&base_ccy=USD" | jq

# 驗證點：
# - .detail.evidence.precondition_snapshot.trades_count == 0

# 7. 測試 JSON 合約（防 jq 爆）
curl -s "http://localhost:8005/valuation/portfolio?user_id=test_e2e&base_ccy=USD" | \
  python3 -c "import json,sys; json.loads(sys.stdin.read()); print('✅ Valid JSON')"

# 預期輸出：✅ Valid JSON

# 8. Runtime Guard 注入測試
docker compose run --rm -e DATABASE_URL=postgresql://x:y@z:5432/db valuation-service \
  python -c "from app.guardrails import check_and_exit; check_and_exit()"

echo "Exit code: $?"

# 驗證點：
# - Exit code: 78（非 0）
# - stderr 含 "blocked_env_keys"
# - stderr 不含 "postgresql://x:y@z"（value 已遮罩）

# 9. 執行所有測試
docker compose exec -T valuation-service pytest -q
docker compose exec -T portfolio-service pytest -q

# 預期：所有測試通過

# 10. 執行 PR Gate
./tools/pr_check.sh

# 預期：12 項檢查全綠
```

---

## 📊 驗收標準總結

### 功能驗收

- ✅ **GET /valuation/portfolio** 端點
  - 查詢參數：`user_id` / `base_ccy` / `as_of`
  - HTTP 200：成功估值（含 totals / positions / evidence）
  - HTTP 409：前置條件失敗（trades_count=0）
  - HTTP 502：upstream 失敗（portfolio-service 連線問題）

- ✅ **結構化 JSON 回應**
  - 使用 Pydantic BaseModel
  - 不回傳 dict repr / HTML / plain text
  - 可被 `json.loads()` 解析

- ✅ **可證偽 Evidence**
  - `precondition_snapshot`（trades_count / distinct_symbols_count）
  - `verification`（portfolio_service_endpoints_called / trades_summary_sql）
  - `providers`（price/fx provider name + version）
  - `positions_hash`（SHA256）
  - `masked_env_keys`（只顯示 key=***）

- ✅ **前置條件檢查**
  - trades_count=0 → HTTP 409 Conflict
  - 回應為 application/json
  - 包含 evidence（trades_count / verification_sql）

### 架構邊界驗收

- ✅ **Runtime Guard**
  - 偵測 DATABASE_URL / POSTGRES_* / PG*
  - 必須 `raise RuntimeError`（阻斷服務啟動）
  - Exit code 78（配置錯誤）
  - Evidence 只顯示遮罩 key（不含 value）

- ✅ **Forbidden Tokens 掃描**
  - valuation-service 無 sqlalchemy / psycopg2 / asyncpg
  - valuation-service 無 DATABASE_URL / POSTGRES_*
  - portfolio-service accounting 層無 valuation / market_value / fx

- ✅ **Docker Compose Config**
  - valuation-service env 只含 allow-list（PORT / PORTFOLIO_BASE_URL / SERVICE_NAME）
  - portfolio-service env 含必要配置（DATABASE_URL / GOOGLE_SA_JSON_PATH）

### 測試驗收

- ✅ **test_health.py**：Health endpoint 測試
- ✅ **test_runtime_guard_no_db_env.py**：6 個場景測試（乾淨 / DATABASE_URL / POSTGRES_* / PG*）
- ✅ **test_valuation_portfolio.py**：7 個測試（409 / 200 / JSON parse / evidence）
- ✅ **所有測試通過**：`pytest -q` 全綠

### PR Gate 驗收

- ✅ **12 項檢查全通過**：
  1. Forbidden tokens scan (valuation-service)
  2. Forbidden tokens scan (portfolio-service accounting)
  3. Docker compose config env allow-list (valuation-service)
  4. Docker compose config env checks (portfolio-service)
  5. Services running check
  6. Runtime env sanity (valuation-service)
  7. Runtime guard injection test
  8. Valuation API JSON contract check
  9. pytest (portfolio-service)
  10. pytest collect-only (portfolio-service)
  11. pytest (valuation-service)
  12. pytest collect-only (valuation-service)

---

## 🚀 建議 Commit Message

```
feat(valuation): Sprint 1-4.B Valuation Layer 完整實作

實作 valuation-service 估值層 API，嚴格遵守架構邊界：

核心功能：
- GET /valuation/portfolio 端點（含 evidence）
- 前置條件檢查（trades=0 → HTTP 409）
- 結構化 JSON 回應（Pydantic models）
- PriceProvider / FxProvider 抽象介面與 stub 實作

架構守護：
- Runtime guard 阻斷 DB 環境變數（exit 78）
- Forbidden tokens 掃描（無 sqlalchemy / psycopg2）
- Docker compose config 白名單（只允許 HTTP 取數）

測試覆蓋：
- test_health.py（health endpoint）
- test_runtime_guard_no_db_env.py（6 場景）
- test_valuation_portfolio.py（7 測試）
- JSON parse 測試（防 jq 爆）

PR Gate 強化：
- 新增 Valuation API JSON 合約檢查
- 新增 Runtime guard 注入檢查
- 12 項檢查全通過

文件與工具：
- SPRINT_1-4-B_IMPLEMENTATION.md（完整實作報告）
- SPRINT_1-4-B_DELIVERY.md（交付清單）
- tools/verify_sprint_1-4-b.sh（自動化驗收腳本）

驗收結果：
✅ valuation-service 禁止 DB 直連
✅ 只透過 HTTP 從 portfolio-service 取數
✅ 前置條件檢查正確（409 Conflict）
✅ 回傳結構化 JSON（含可證偽 evidence）
✅ 所有測試通過（pytest -q）
✅ PR Gate 全綠（12/12）
✅ VM 與 Codespaces 一致通過

Sprint 1-4.B 目標達成。
```

---

## 📝 已知限制與未來改進

### Sprint 1-4.B Scope（已完成）
- ✅ Stub providers（deterministic）
- ✅ 基本估值邏輯（quantity * price * fx_rate）
- ✅ 架構邊界強制（runtime guard）
- ✅ API-only 取數（HTTP）

### 未來 Sprint（Out of Scope）
- 🔜 Real price provider（market data API）
- 🔜 Real FX provider（FX API）
- 🔜 Historical valuation（as_of 參數）
- 🔜 Performance caching（Redis）
- 🔜 Batch valuation（多用戶並行）

---

## 🎯 關鍵設計亮點

1. **Fail-Fast 原則**
   - Runtime guard 在服務啟動時就檢查環境變數
   - 錯誤配置 → 服務無法啟動（而非運行時才爆）

2. **可證偽設計**
   - 所有回應含 evidence（verification_sql / positions_hash / masked_env_keys）
   - 用戶可重新計算 hash 驗證數據完整性

3. **抽象介面 + DI**
   - Provider 抽象（BasePriceProvider / BaseFxProvider）
   - 測試用 stub / 生產用真實 provider（未來可替換）

4. **防 jq 爆測試**
   - 使用 `python -c "import json; json.loads(...)"`
   - 確保回傳真正的 JSON（而非 dict repr / HTML）

5. **遮罩策略**
   - ENV keys 顯示為 `KEY=***`
   - Forbidden keys 顯示為 `D**********L`
   - 既可證偽又不洩密

---

**End of Delivery Document**

如有任何問題，請參考：
- 完整實作報告：[SPRINT_1-4-B_IMPLEMENTATION.md](SPRINT_1-4-B_IMPLEMENTATION.md)
- 自動化驗收：[tools/verify_sprint_1-4-b.sh](tools/verify_sprint_1-4-b.sh)
- PR Gate 檢查：[tools/pr_check.sh](tools/pr_check.sh)
