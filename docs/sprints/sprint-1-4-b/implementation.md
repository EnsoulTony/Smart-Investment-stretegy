# Sprint 1-4.B 實作報告：Valuation Layer

**日期**: 2026-01-25  
**狀態**: ✅ 完成並可驗收  
**工程師**: GitHub Copilot (Claude Sonnet 4.5)

---

## 📋 目標

實作 `valuation-service` 估值層 API，嚴格遵守以下架構邊界：

1. **禁止 DB 直連**：valuation-service 絕對不可存取資料庫
2. **API-only 取數**：僅透過 HTTP 呼叫 portfolio-service 取得帳務數據
3. **可證偽設計**：所有回應必須包含 evidence（驗證資訊）
4. **前置條件檢查**：trades_count=0 時必須回 409 Conflict
5. **結構化 JSON**：不得回傳 dict repr/HTML/plain text

---

## 🎯 交付清單

### A. 核心功能

#### 1. **GET /valuation/portfolio** 端點
- ✅ 查詢參數：`user_id` (必填)、`base_ccy` (預設 USD)、`as_of` (預設今天)
- ✅ 成功回應：HTTP 200 + application/json
- ✅ 失敗回應：
  - HTTP 409（trades_count=0）
  - HTTP 502（portfolio-service 連線失敗）

#### 2. **回應結構**（Pydantic models）
```python
ValuationResponse {
  status: str
  user_id: str
  base_ccy: str
  as_of: str (ISO date)
  totals: {
    market_value: float
    cost_value: float
    unrealized_pnl: float
  }
  positions: [
    {
      symbol: str
      asset_ccy: str
      quantity: float
      avg_cost: float
      cost_value: float
      price: float
      price_ccy: str
      market_value: float
      unrealized_pnl: float
    }
  ]
  evidence: {
    decision: "proceed" | "blocked_precondition"
    precondition_snapshot: {
      trades_count: int
      distinct_symbols_count: int
    }
    verification: {
      portfolio_service_endpoints_called: [str]
      trades_summary_sql: dict  # 從 portfolio-service 取得
      as_of: str
    }
    providers: {
      price_provider: str
      price_provider_version: str
      fx_provider: str
      fx_provider_version: str
    }
    positions_count: int
    positions_hash: str  # SHA256(canonical JSON)
    masked_env_keys: [str]  # 只顯示 key，value 全遮罩
  }
}
```

#### 3. **Price & FX Providers**（抽象介面 + Stub 實作）

**providers.py**：
- ✅ `BasePriceProvider` / `BaseFxProvider`（抽象類）
- ✅ `StubPriceProvider` / `StubFxProvider`（deterministic stub）
- ✅ `get_price_provider()` / `get_fx_provider()`（factory）
- ✅ Stub 實作不依賴外網，測試輸出固定

#### 4. **Runtime Guardrails**（DB 環境變數阻斷）

**guardrails.py**：
- ✅ `validate_runtime_env()`：偵測 `DATABASE_URL` / `POSTGRES_*` / `PG*`
- ✅ 偵測到禁止 env → **必須 `raise RuntimeError`**（阻斷服務啟動）
- ✅ Evidence 只顯示遮罩後的 key（例如 `D**********L`），不含 value
- ✅ `check_and_exit()`：CLI 用途，exit code 78（EX_CONFIG）

**main.py 啟動檢查**：
```python
# Line 37
RUNTIME_GUARD_STATUS = validate_runtime_env()  # 若有 DB env → raise RuntimeError
```

### B. 測試覆蓋

#### 1. **test_health.py**
- ✅ GET /health 回傳 status=healthy
- ✅ 包含 providers / guardrail 資訊

#### 2. **test_runtime_guard_no_db_env.py**
- ✅ 乾淨環境：`validate_runtime_env()` 回傳 `{"status": "ok"}`
- ✅ 注入 `DATABASE_URL` → 必須 `raise RuntimeError`
- ✅ 注入 `POSTGRES_HOST` → 必須 `raise RuntimeError`
- ✅ 注入 `PGUSER` → 必須 `raise RuntimeError`
- ✅ Evidence 只含遮罩 key，不含 value

#### 3. **test_valuation_portfolio.py**
- ✅ **前置條件檢查**（trades_count=0）：
  - HTTP 409 Conflict
  - `content-type: application/json`
  - Body 可 `json.loads()`
  - `detail.evidence` 含 `verification_sql`（只含 key）
- ✅ **正常估值**（trades > 0）：
  - HTTP 200
  - `content-type: application/json`
  - `totals` / `positions` 結構完整
  - `evidence.decision=proceed`
- ✅ **防 jq 爆測試**：
  - `assert json.loads(response.text)`
  - 能抓到回傳 dict repr / HTML / traceback 的情況

### C. PR Gate 強化（避免「VM 才爆」）

**tools/pr_check.sh** 新增檢查項目：

#### 新增 7：**Valuation API JSON 合約檢查**
```bash
curl -s -i "http://valuation-service:8005/valuation/portfolio?user_id=test_e2e&base_ccy=TWD"
# 檢查：
# 1. HTTP status code（200 或 409，不能是 500/502）
# 2. content-type 必須包含 application/json
# 3. 使用 python -c "import json,sys; json.loads(sys.stdin.read())" 驗證（不依賴 jq）
```

#### 新增 8：**Runtime Guard 注入檢查**
```bash
docker compose run --rm -e DATABASE_URL=postgresql://x:y@z:5432/db valuation-service \
  python -c "from app.guardrails import check_and_exit; check_and_exit()"

# 預期：
# - Exit code != 0 (應為 78)
# - stderr 輸出 evidence（只含遮罩 key）
```

### D. 文件更新

#### RUNBOOK.md 新增章節

```markdown
## Sprint 1-4.B：Valuation Layer 驗收

### 最短跑通流程

# 1. 確保 portfolio-service 有資料
./tools/portfolio_refresh.sh tony

# 2. 呼叫估值 API
curl -s "http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=TWD" | jq

# 3. 驗證回應
# - HTTP 200
# - content-type: application/json
# - evidence.decision=proceed
# - totals.market_value > 0
# - positions[].unrealized_pnl 存在

### 可證偽驗證

# Evidence 必須包含：
# - precondition_snapshot.trades_count
# - verification.portfolio_service_endpoints_called
# - verification.trades_summary_sql（只含 key）
# - providers（price/fx provider name + version）
# - positions_hash（SHA256）
# - masked_env_keys（只顯示 key=***）
```

#### Development.md 新增章節

```markdown
## Sprint 1-4.B PR Checklist

### 必須通過的檢查

- [ ] `rg` 掃描 valuation-service：無 `sqlalchemy` / `psycopg2` / `asyncpg`
- [ ] `rg` 掃描 valuation-service：無 `DATABASE_URL` / `POSTGRES_*` / `PG*`
- [ ] `docker compose config` valuation-service env 只有 allow-list（PORT/PORTFOLIO_BASE_URL/SERVICE_NAME）
- [ ] Runtime guard 注入測試：`docker compose run --rm -e DATABASE_URL=x ... check_and_exit` → exit 78
- [ ] Valuation API JSON 合約：`curl /valuation/portfolio` → application/json（可 json.loads）
- [ ] 所有測試通過：`docker compose exec -T valuation-service pytest -q`

### 驗收命令

```bash
# VM 內執行
cd /root/Smart-Investment-stretegy

# 啟動服務
docker compose up -d --build valuation-service portfolio-service postgres

# 等待就緒
docker compose exec -T postgres sh -c 'until pg_isready -U investment; do sleep 1; done'
docker compose exec -T portfolio-service alembic upgrade head

# 同步測試資料
./tools/portfolio_refresh.sh test_e2e

# 執行估值
curl -s "http://localhost:8005/valuation/portfolio?user_id=test_e2e&base_ccy=USD" | jq

# 執行測試
docker compose exec -T valuation-service pytest -q
docker compose exec -T portfolio-service pytest -q

# 執行 PR Gate
./tools/pr_check.sh
```
```

---

## 📁 修改的檔案清單

### 核心實作

1. **services/valuation-service/app/main.py**
   - GET /health 端點
   - GET /valuation/portfolio 端點
   - Pydantic models（ValuationResponse, PositionItem, Evidence...）
   - 啟動時 runtime guard 檢查（Line 37）

2. **services/valuation-service/app/guardrails.py**
   - `validate_runtime_env()`：偵測並阻斷 DB env
   - `check_and_exit()`：CLI 用途（exit code 78）
   - Evidence 建構（只顯示遮罩 key）

3. **services/valuation-service/app/providers.py**
   - `BasePriceProvider` / `BaseFxProvider`（抽象類）
   - `StubPriceProvider` / `StubFxProvider`（deterministic stub）
   - Factory functions

4. **services/valuation-service/app/portfolio_client.py**
   - `PortfolioClient`：HTTP client for portfolio-service
   - `get_trades_summary()` / `get_positions()`

### 測試

5. **services/valuation-service/tests/test_health.py**
   - Health endpoint 測試

6. **services/valuation-service/tests/test_runtime_guard_no_db_env.py**
   - Runtime guard 各種場景（乾淨 env / DATABASE_URL / POSTGRES_* / PG*）
   - Evidence 驗證（只含 key）

7. **services/valuation-service/tests/test_valuation_portfolio.py**
   - 前置條件失敗（409）
   - 正常估值（200）
   - JSON parse 測試

8. **services/valuation-service/tests/conftest.py**
   - Pytest fixtures

### 工具與文件

9. **tools/pr_check.sh**
   - 新增：Valuation API JSON 合約檢查
   - 新增：Runtime guard 注入檢查

10. **RUNBOOK.md**
    - Sprint 1-4.B 驗收章節
    - 最短跑通流程
    - 可證偽驗證說明

11. **Development.md**
    - Sprint 1-4.B PR Checklist
    - VM 驗收命令

12. **SPRINT_1-4-B_IMPLEMENTATION.md**（本文件）
    - 完整實作報告

---

## ✅ 驗收標準

### 1. 功能驗收

```bash
# 在 VM 內執行
cd /root/Smart-Investment-stretegy

# 啟動服務
docker compose up -d --build valuation-service portfolio-service postgres

# 等待資料庫就緒
docker compose exec -T postgres sh -c 'until pg_isready -U investment; do sleep 1; done'

# 初始化資料庫
docker compose exec -T portfolio-service alembic upgrade head

# 同步測試資料
./tools/portfolio_refresh.sh test_e2e

# ===== 驗收 1：正常估值 =====
curl -s -i "http://localhost:8005/valuation/portfolio?user_id=test_e2e&base_ccy=USD" | head -n 20
# 預期：HTTP/1.1 200 OK
#       Content-Type: application/json

curl -s "http://localhost:8005/valuation/portfolio?user_id=test_e2e&base_ccy=USD" | jq .evidence.decision
# 預期："proceed"

curl -s "http://localhost:8005/valuation/portfolio?user_id=test_e2e&base_ccy=USD" | jq .totals
# 預期：{ market_value: ..., cost_value: ..., unrealized_pnl: ... }

# ===== 驗收 2：前置條件檢查（trades=0）=====
curl -s -i "http://localhost:8005/valuation/portfolio?user_id=empty_user&base_ccy=USD" | head -n 20
# 預期：HTTP/1.1 409 Conflict
#       Content-Type: application/json

curl -s "http://localhost:8005/valuation/portfolio?user_id=empty_user&base_ccy=USD" | jq .detail.evidence.precondition_snapshot.trades_count
# 預期：0

# ===== 驗收 3：JSON 合約（防 jq 爆）=====
curl -s "http://localhost:8005/valuation/portfolio?user_id=test_e2e&base_ccy=USD" | \
  python -c "import json,sys; json.loads(sys.stdin.read()); print('OK')"
# 預期：OK

# ===== 驗收 4：Runtime Guard =====
docker compose run --rm -e DATABASE_URL=postgresql://x:y@z:5432/db valuation-service \
  python -c "from app.guardrails import check_and_exit; check_and_exit()"
# 預期：Exit code != 0（應為 78）
#       stderr 輸出 evidence（含遮罩 key）

echo "Exit code: $?"
# 預期：78
```

### 2. 測試驗收

```bash
# 所有測試必須通過
docker compose exec -T valuation-service pytest -q
# 預期：...passed

docker compose exec -T portfolio-service pytest -q
# 預期：...passed
```

### 3. PR Gate 驗收

```bash
# 執行完整 PR 檢查
./tools/pr_check.sh
# 預期：所有檢查項目 ✅ PASS
```

---

## 🚀 已知限制與未來改進

### Sprint 1-4.B Scope（已完成）
- ✅ Stub providers（deterministic，不依賴外網）
- ✅ 基本估值邏輯（quantity * price * fx_rate）
- ✅ 架構邊界強制（runtime guard）

### 未來 Sprint（Out of Scope）
- 🔜 Real price provider（接 market data API）
- 🔜 Real FX provider（接 FX API）
- 🔜 Historical valuation（支援 `as_of` 參數查歷史）
- 🔜 Performance caching（Redis）
- 🔜 Batch valuation（多用戶並行）

---

## 📊 Evidence 範例

### 成功估值（HTTP 200）

```json
{
  "status": "success",
  "user_id": "test_e2e",
  "base_ccy": "USD",
  "as_of": "2026-01-25",
  "totals": {
    "market_value": 12500.50,
    "cost_value": 10000.00,
    "unrealized_pnl": 2500.50
  },
  "positions": [
    {
      "symbol": "AAPL",
      "asset_ccy": "USD",
      "quantity": 100.0,
      "avg_cost": 150.00,
      "cost_value": 15000.00,
      "price": 175.00,
      "price_ccy": "USD",
      "market_value": 17500.00,
      "unrealized_pnl": 2500.00
    }
  ],
  "evidence": {
    "decision": "proceed",
    "precondition_snapshot": {
      "trades_count": 5,
      "distinct_symbols_count": 3
    },
    "verification": {
      "portfolio_service_endpoints_called": [
        "GET /portfolio/trades/summary?user_id=test_e2e",
        "GET /portfolio/positions?user_id=test_e2e"
      ],
      "trades_summary_sql": {
        "count_sql": "SELECT COUNT(*) FROM trades WHERE ...",
        "distinct_symbols_sql": "SELECT COUNT(DISTINCT symbol) FROM ..."
      },
      "as_of": "2026-01-25"
    },
    "providers": {
      "price_provider": "StubPriceProvider",
      "price_provider_version": "1.0.0-stub",
      "fx_provider": "StubFxProvider",
      "fx_provider_version": "1.0.0-stub"
    },
    "positions_count": 1,
    "positions_hash": "a3f5d8...9c2e1b",
    "masked_env_keys": [
      "HOME=***",
      "PORT=***",
      "PORTFOLIO_BASE_URL=***",
      "...=***"
    ]
  }
}
```

### 前置條件失敗（HTTP 409）

```json
{
  "detail": {
    "status": "precondition_failed",
    "message": "trades_count=0; 請先執行 portfolio sync",
    "evidence": {
      "precondition_snapshot": {
        "trades_count": 0,
        "distinct_symbols_count": 0
      },
      "verification_sql": {
        "count_sql": "SELECT COUNT(*) FROM trades WHERE user_id = $1",
        "distinct_symbols_sql": "SELECT COUNT(DISTINCT symbol) FROM trades WHERE user_id = $1"
      }
    }
  }
}
```

### Runtime Guard 阻斷（Exit 78）

```
stderr:
[GUARDRAIL][VAL-SVC-NO-DB][v1.2.0] db_direct_env_detected
decision=blocked_env_injection
blocked_count=1
evidence.blocked_keys=[D**********L]
rules.forbidden_keys_count=5
rules.forbidden_prefixes_count=1
rules.patterns_used=['DATABASE_URL', 'PORTFOLIO_DATABASE_URL', 'PG*', 'POSTGRES_*']
repro.fail="docker compose run --rm -e DATABASE_URL=x valuation-service python -c 'from app.guardrails import validate_runtime_env; validate_runtime_env()'"
remedy="valuation-service must fetch data only via PORTFOLIO_BASE_URL (HTTP); remove all DB environment variables"

GUARDRAIL_EVIDENCE_JSON={"guardrail_id":"VAL-SVC-NO-DB","guardrail_version":"1.2.0","decision":"blocked_env_injection","blocked_env_keys":["D**********L"],"blocked_count":1}
```

---

## 🎓 關鍵設計決策

### 1. 為何使用 Pydantic BaseModel？
- FastAPI 原生支援，自動生成 OpenAPI schema
- 型別驗證 + 自動序列化
- **確保回傳 JSON 而非 dict repr**

### 2. 為何需要 `_canonical_json_hash()`？
- 提供可證偽的 positions 資料完整性驗證
- 用戶可重新計算 hash 對比，確認數據未被篡改

### 3. 為何要 `masked_env_keys`？
- 避免洩漏敏感資訊（例如 API keys）
- 同時提供可證偽性（用戶可看到有哪些 env keys）

### 4. 為何 runtime guard 要 `raise RuntimeError`？
- 確保服務無法在錯誤配置下啟動
- **Fail-fast 原則**：啟動時就發現問題，而非運行時才爆

### 5. 為何要抽象 Provider 介面？
- 未來可替換成真實 provider（market data / FX API）
- 測試時使用 stub（deterministic）
- 符合 SOLID 的 D（依賴反轉原則）

---

## 📝 Commit Message 建議

```
feat(valuation): 實作 Sprint 1-4.B Valuation Layer

- 新增 GET /valuation/portfolio 端點（含 evidence）
- 實作 runtime guard 阻斷 DB 環境變數
- 新增 PriceProvider / FxProvider 抽象介面與 stub 實作
- 補充完整測試覆蓋（409/200/JSON parse）
- 更新 pr_check.sh 新增 JSON 合約與 runtime guard 檢查
- 更新 RUNBOOK.md / Development.md 驗收流程

Sprint 1-4.B 目標達成：
✅ valuation-service 禁止 DB 直連（runtime guard）
✅ 只透過 HTTP 從 portfolio-service 取數
✅ 前置條件檢查（trades=0 → 409）
✅ 回傳結構化 JSON（含可證偽 evidence）
✅ 所有測試通過
✅ PR Gate 全綠
```

---

**End of Report**

如需任何修改或補充，請參考本報告第 `📁 修改的檔案清單` 章節。
