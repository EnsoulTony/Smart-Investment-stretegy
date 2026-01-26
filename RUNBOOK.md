# RUNBOOK.md｜維運指南（MVP）

本文件提供 VM 上的維運人員、資料與策略工程師在遇到故障時的標準作業流程（SOP），包含日常檢查、異常排查、重啟/回滾、備份與 AI 協作注意事項。

## 1. 日常檢查清單

1. `docker ps --format 'table {{.Names}}\t{{.Status}}'`（所有容器須為 healthy）
2. `curl http://localhost:8000/health`（Gateway 探活）
3. `curl http://localhost:8001/health` ~ `8004/health`（抽樣）
4. `journalctl -u radar-deploy.timer -n 30`
5. `docker compose exec postgres pg_isready`
6. 檢查最新 `recommendations`、`news_signals` 是否更新（可透過 SQL 或 API）

### 1.1. VM 環境變數配置檢查（Portfolio Service 相關）

**必要環境變數**（在 VM 的 `.env` 檔案中）：

```bash
# Postgres 連線
DATABASE_URL=postgresql://investment:${DB_PASSWORD}@postgres:5432/investment_db

# Google Sheets 同步（Service Account JSON）
# ⚠️ 安全要求：不要把 JSON 內容直接放進 env
GOOGLE_SA_JSON_PATH=/secure/keys/google_sa.json

# Google Sheets 識別資訊
GOOGLE_SHEET_ID=<your-sheet-id>
GOOGLE_SHEET_NAME=<sheet-name>

# 欄位 mapping（可選，預設值如下）
SHEET_COL_SYMBOL=代號
SHEET_COL_NAME=名稱
SHEET_COL_QUANTITY=股數
SHEET_COL_PRICE=成本
SHEET_COL_DATE=日期
SHEET_COL_SIDE=買/賣
```

**驗證指令**：
```bash
# 檢查是否設定（不顯示內容）
test -n "$GOOGLE_SA_JSON_PATH" && echo "GOOGLE_SA_JSON_PATH is set" || echo "Missing GOOGLE_SA_JSON_PATH"
test -n "$GOOGLE_SHEET_ID" && echo "GOOGLE_SHEET_ID is set" || echo "Missing GOOGLE_SHEET_ID"

# 驗證 JSON 格式是否正確（從檔案讀取）
python3 -m json.tool < "$GOOGLE_SA_JSON_PATH" > /dev/null && echo "Valid JSON" || echo "Invalid JSON"
```

**證據輸出規範（敏感資訊遮罩）**：
- 任何含 secrets 的指令輸出只能顯示「變數名稱」或「檔案路徑」，不可輸出內容。
- 例如：使用 `env | grep GOOGLE_SA_JSON_PATH`，不得 `cat` 或 `echo` JSON 內容。

**google_sa.json 修改方式（不入 repo）**：
1. 將 Service Account JSON 放在 VM 路徑（例：`/secure/keys/google_sa.json`）。
2. 權限收斂（僅 root 可讀）：
  ```bash
  sudo chown root:root /secure/keys/google_sa.json
  sudo chmod 600 /secure/keys/google_sa.json
  ```
3. 更新 `.env`：
  ```bash
  GOOGLE_SA_JSON_PATH=/secure/keys/google_sa.json
  ```
4. 重建服務讓掛載生效：
  ```bash
  docker compose up -d --build portfolio-service
  ```
5. 驗證（只顯示路徑，不顯示內容）：
  ```bash
  docker compose exec portfolio-service env | grep GOOGLE_SA_JSON_PATH
  ```

### 1.2. 硬隔離規則（服務環境變數）

- **任何服務容器不得持有超出職責範圍的敏感連線設定**。
	- 例如：valuation-service **不得**持有 `DATABASE_URL` / `POSTGRES_*` 等 DB 連線資訊。
	- 估值層只能透過 portfolio-service 的 HTTP API 取數。

## 2. 異常排查對照表

| 症狀 | 可能原因 | 處理步驟 |
| --- | --- | --- |
| 前端空白或 5xx | Gateway 掛掉 / JWT 失效 | `docker logs api-gateway` → `docker restart api-gateway` |
| Radar 無建議輸出 | 指標未更新 / 策略崩潰 | 1. `docker logs radar-service` 2. 確認 `indicator_values` 是否含最新 `RS_XLU_XLK` |
| 新聞/研究訊號缺漏 | GDELT/RSS 限制 | 重啟對應服務並檢查 API 金鑰 |
| Postgres 空間不足 | 快照過多 | `docker compose exec postgres du -sh /var/lib/postgresql/data` → 清理舊備份或擴容 |
| docker compose up 失敗 | `.env` 缺值或埠被占用 | 1. 驗證 `.env` 2. `docker compose config` 3. 釋放埠號 |
| /portfolio/sync 回傳重複大量跳過 | Google Sheets 未更新 / hash 計算正確 | 檢查 `duplicates_count` 與 `sheet_rows_count`：若相等代表全為舊資料（正常）|
| /portfolio/sync 出現 errors_count > 0 | Sheets 資料格式錯誤 | 檢查 `normalized_invalid_count` 並查看日誌中的具體錯誤行 |
| **測試回傳 symbols 為空** | **TestClient 與測試 session 隔離** | **見下方「測試隔離問題」專節** |

### 2.1. 測試隔離問題（Troubleshooting: symbols 為空）

**症狀**：
- 測試插入 Trade 資料到 db_session
- 呼叫 API 端點（例如 POST /portfolio/rebuild_positions/preview）
- API 回傳 `symbols = []`（空陣列），但測試插入的資料確實存在

**根本原因**：

當測試使用 `db_session` fixture（基於 SAVEPOINT / nested transaction）與 FastAPI TestClient 時，會出現兩個獨立的 database session：

1. **測試的 db_session**：使用 SAVEPOINT 機制，`commit()` 只提交到 SAVEPOINT，不是真正寫入 DB
2. **API 的 get_db()**：FastAPI dependency injection 預設會建立新的 session

因為 transaction 隔離，兩個 session 互相看不到對方的資料。

**正確修法（四個關鍵步驟）**：

**步驟 1：override get_db dependency**

在測試檔案中建立 `client` fixture：

```python
from app.db import get_db
from app.main import app

@pytest.fixture
def client(db_session):
    """讓 API 與測試共用同一個 db_session"""
    def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

**步驟 2：使用 context manager**

```python
with TestClient(app) as c:
    yield c
```

確保 lifespan 正確啟停，避免狀態殘留。

**步驟 3：插入後自我驗證**

```python
# 插入測試資料
trade = Trade(user_id="test_user", symbol="AAPL", ...)
db_session.add(trade)
db_session.commit()

# 自我驗證：確認插入成功（避免把錯誤歸因到 API）
count = db_session.query(Trade).filter_by(user_id="test_user").count()
assert count == 1, f"插入失敗，預期 1 筆，實際：{count}"

# 才呼叫 API
response = client.post("/portfolio/rebuild_positions/preview", ...)
```

**步驟 4：清除 dependency_overrides**

```python
app.dependency_overrides.clear()
assert len(app.dependency_overrides) == 0  # 可選：確保清除成功
```

**驗證修正是否成功**：

```bash
# 重建容器（因為 tests/ 被 COPY 進 image）
docker compose up -d --build portfolio-service

# 執行測試，應該看到 symbols 有資料
docker compose exec portfolio-service pytest tests/test_rebuild_positions_preview.py -v

# 自我驗證的 count 檢查應該通過（count > 0）
# API 回傳的 symbols 應該不為空
```

**參考範例**：
- `services/portfolio-service/tests/test_rebuild_positions_preview.py`
- `services/portfolio-service/tests/conftest.py`（db_session fixture 的 SAVEPOINT 機制）

### 2.2. 測試修改後需重建容器

**情況**：
- 修改 `services/portfolio-service/tests/` 目錄下的測試檔案
- 在容器內執行測試，發現測試仍使用舊版本程式碼

**原因**：

Dockerfile 在 build 階段 COPY 了整個 `tests/` 目錄：

```dockerfile
COPY services/portfolio-service/tests /app/tests
```

因此修改測試檔案後，容器內的檔案不會自動更新。

**解決方案**：

```bash
# 重建 portfolio-service 容器
docker compose up -d --build portfolio-service

# 等待容器啟動（約 3-5 秒）
sleep 3

# 執行測試
docker compose exec portfolio-service pytest tests/test_rebuild_positions_preview.py -v
```

**一鍵驗證腳本**：

專案提供了 `test_preview.sh` 腳本自動執行上述流程：

```bash
chmod +x test_preview.sh
./test_preview.sh
```

**注意事項**：
- 如果只修改 `app/` 目錄（非測試），也需要重建容器
- 開發時可考慮使用 volume mount（但正式環境不建議）
- CI/CD pipeline 會自動重建，無需手動處理

### 2.3. 禁止在 host venv 執行跨服務測試

**錯誤做法** ❌：

```bash
# 在 repo root 的 host venv 直接跑 pytest
(.venv) root@host:~/Smart-Investment-stretegy# pytest -q -k fx
```

**問題**：
- pytest 會**跨服務收集測試**（api-gateway, portfolio-service, news-service...）
- host venv 沒有安裝各服務的依賴（fastapi、sqlalchemy 等）
- 導致 `ModuleNotFoundError` 與大量假陰性（false negative）

**正確做法** ✅：

```bash
# 方法 1：在運行中的容器內執行（推薦，適合快速測試）
docker compose exec portfolio-service pytest -q -k fx

# 方法 2：啟動臨時容器執行（適合 CI/CD）
docker compose run --rm portfolio-service pytest -q -k fx

# 方法 3：執行特定檔案
docker compose exec portfolio-service pytest -q tests/test_fx.py

# 方法 4：詳細輸出
docker compose exec portfolio-service pytest -v tests/test_fx.py
```

**原理**：
- 每個 service 有獨立的 `requirements.txt` 與 Python 環境
- Docker 容器確保依賴隔離，避免版本衝突
- 測試必須在對應服務的容器內執行

**驗證結果範例**：

```bash
# ✅ 正確執行（在容器內）
$ docker compose exec portfolio-service pytest -q -k fx
....................                                                     [100%]
20 passed, 58 deselected in 0.71s

# ❌ 錯誤執行（在 host venv）
$ pytest -q -k fx
ERROR services/portfolio-service/tests/test_fx.py
ModuleNotFoundError: No module named 'app'
```

---

## 11. Portfolio Refresh 流程（系統合約）

**工具**：`./tools/portfolio_refresh.sh <user_id>`

**固定流程（不可跳步）**：
1. `GET /portfolio/trades/summary?user_id=...`
   - 若 `trades_count=0`，必須提示「需要 sync」（不得直接 rebuild）
2. `POST /portfolio/sync?user_id=...`
3. 再次 `GET /portfolio/trades/summary`，確認 `trades_count > 0`
4. `POST /portfolio/rebuild_positions?user_id=...&require_trades=1`
5. 輸出 evidence JSON（system contract）：
   - `decision`
   - `trades_count`
   - `distinct_symbols_count`
   - `positions_columns`
   - `verification_sql`（可直接複製執行）

**範例執行**：
```bash
./tools/portfolio_refresh.sh tony
```

**範例輸出（節錄）**：
```json
{
  "decision": "sync_executed",
  "trades_count": 66,
  "distinct_symbols_count": 5,
  "positions_columns": [
    "id",
    "user_id",
    "symbol",
    "asset_ccy",
    "quantity",
    "avg_cost",
    "realized_pnl",
    "u_pnl",
    "last_updated_at"
  ],
  "verification_sql": {
    "trades_count": "select count(*) from trades where user_id='tony';",
    "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';",
    "positions_count": "select count(*) from positions where user_id='tony';"
  }
}
```

**成功判準**：
- `trades_count > 0`
- `distinct_symbols_count > 0`
- `positions_columns` 含 `u_pnl`
- `verification_sql` 可直接複製執行且與 API 回傳一致

## 3. 重啟與回滾

- 重啟單一服務：`docker compose restart <service>`
- 全體重啟：`make docker-down && make docker-up`
- 回滾流程：
	1. `git fetch --all`
	2. `git checkout <previous-tag>`
	3. `make docker-up`
	4. 驗證 `/health` 與前端 UI
	5. 在 Issue/PR 記錄原因與後續行動

## 4. 備份策略

- Postgres：
	- 每日 02:00 `pg_dump` 至 `/var/backups/radar/<date>.sql`
	- 每週同步至物件儲存（S3/GCS）
- `.env`、systemd 服務檔：存於 `/etc/radar/` 並納入私有備份 repo。
- 關鍵表：`recommendations`, `analysis_runs`, `news_signals`, `research_signals` 需月度冷備。

### 4.1. 資料庫清空與重建流程（Portfolio Service）

⚠️ **僅用於開發/測試環境**，正式環境需先備份

```bash
# 1. 停止 portfolio-service
docker compose stop portfolio-service

# 2. 清空 trades 與 sync_runs 表
docker compose exec postgres psql -U investment -d investment_db -c "TRUNCATE TABLE trades, sync_runs RESTART IDENTITY CASCADE;"

# 3. （可選）重新執行 migration
docker compose exec portfolio-service alembic downgrade base
docker compose exec portfolio-service alembic upgrade head

# 4. 重啟服務
docker compose start portfolio-service
```

驗證：`curl http://localhost:8001/health` 應回傳 200。

## 5. systemd timer（保底部署）

- Service：`/etc/systemd/system/radar-deploy.service`
- Timer：`/etc/systemd/system/radar-deploy.timer`
- 功能：每 15 分鐘執行 `/opt/radar-warroom/infra/vm/deploy.sh --auto`，若 GitHub Actions 部署失敗仍可更新。
- 常用指令：
	- `systemctl status radar-deploy.timer`
	- `journalctl -u radar-deploy.service -f`

## 6. AI 協作者（Claude / Aider）守則

1. 修改前列出檔案與區塊。
2. 嚴守最小差異（Minimal Diff）。
3. 每次變更附測試證明（pytest、Vitest 或 curl log）。
4. 不得將金鑰、私密內容貼給 AI；以 placeholder 表示。
5. 完成後請人工檢查 `git diff` 才能合併。

## 7. 緊急聯絡（Placeholder）

| 類型 | 聯絡方式 |
| --- | --- |
| DevOps Oncall | devops@example.com |
| Strategy Owner | strategy@example.com |
| Data Ops | dataops@example.com |

## 7.5. 測試執行硬規範（Test Execution Guardrails）

### ❌ 禁止做法

**1. 禁止在 repo root 的 host venv 直接跑 pytest**

```bash
# ❌ 錯誤：會跨 service 收集測試，導致依賴缺失與假失敗
(.venv) root@host:~/Smart-Investment-stretegy# pytest -q -k fx

ERROR services/api-gateway/tests/test_health.py
ModuleNotFoundError: No module named 'fastapi'
ERROR services/portfolio-service/tests/test_fx.py
ModuleNotFoundError: No module named 'app'
```

**問題**：
- pytest 會**跨所有 service** 收集測試（api-gateway, portfolio-service, news-service...）
- host venv 沒有安裝各 service 的依賴（fastapi、sqlalchemy 等）
- 導致大量 `ModuleNotFoundError` 與假陰性（false negative）

**2. 禁止在非目標 service container 內執行目標 service 測試**

```bash
# ❌ 錯誤：在 api-gateway 容器內執行 portfolio-service 測試
docker compose exec api-gateway pytest services/portfolio-service/tests/

# ❌ 錯誤：在 postgres 容器內執行應用測試
docker compose exec postgres pytest
```

---

### ✅ 正確做法

**方法 1：在運行中的容器內執行（推薦，適合快速迭代）**

```bash
# 執行 portfolio-service 的 FX 相關測試
docker compose exec portfolio-service pytest -q -k fx

# 執行特定檔案
docker compose exec portfolio-service pytest -q tests/test_fx.py

# 詳細輸出
docker compose exec portfolio-service pytest -v tests/test_fx.py
```

**方法 2：啟動臨時容器執行（適合 CI/CD）**

```bash
# 啟動臨時容器，執行完畢後自動刪除
docker compose run --rm portfolio-service pytest -q -k fx

# 在 CI 環境使用 -T 避免 TTY 問題
docker compose exec -T portfolio-service pytest -q tests/test_fx.py
```

**方法 3：執行驗收腳本（推薦，封裝完整流程）**

```bash
# Sprint 1-3 驗收
bash services/portfolio-service/verify_sprint_1-3.sh

# Sprint 1-4.A 驗收
bash verify_sprint_1-4-a.sh
```

---

### 🔬 FX 模組驗收命令（可證偽證據）

**Sprint 1-4.A 階段**：只允許介面 + Stub，無真實 Provider

```bash
# 測試 1：FX 介面與 Stub 實作
docker compose exec -T portfolio-service pytest -q tests/test_fx.py
```
**期望輸出**：
```
..............                                                           [100%]
14 passed in 0.03s
```

**說明**：
- 14 個測試涵蓋：Stub 初始化、同幣別轉換（可用）、跨幣別轉換（必炸）

---

```bash
# 測試 2：所有 FX 相關測試（含 Guardrails）
docker compose exec -T portfolio-service pytest -q -k fx
```
**期望輸出**：
```
....................                                                     [100%]
20 passed, 55 deselected in 0.71s
```

**可證偽證據**（測試收集）：
```bash
docker compose exec -T portfolio-service pytest -q -k fx --collect-only
# 輸出顯示 20 個測試，來源為：
# - tests/test_fx.py (14 tests)
# - tests/test_fx_guardrails.py (6 tests)
# 20/75 tests collected (55 deselected)
```

**說明**：
- `-k fx` 會跨檔案抓到所有 fx 相關測試（test_fx.py + test_fx_guardrails.py）
- 20 = 14 (test_fx.py) + 6 (test_fx_guardrails.py)
- 55 deselected = 其他不相關測試（總共 75 個測試）

---

```bash
# 測試 3：Guardrails（架構邊界檢查）
docker compose exec -T portfolio-service pytest -q tests/test_fx_guardrails.py
```
**期望輸出**：
```
......                                                                   [100%]
6 passed in 0.07s
```

**說明**：
- 檢查帳務層不得呼叫 FX 模組
- 檢查 FX 模組入口唯一性

---

### 🚫 硬禁止規則：FX 模組邊界

**目的**：防止匯率邏輯散落各處，確保未來 Sprint 1-4.B 擴充估值層時不會發散。

#### 規則 1：匯率邏輯只能在 app/fx/* 內

```bash
# 檢查命令：確認無違規 import
grep -rn "from app.fx import" services/portfolio-service/app   --include="*.py"   --exclude-dir=fx   --exclude-dir=__pycache__

# 期望輸出：（空，無任何匹配）
```

**禁止清單**：
- ❌ 除 `app/fx/*` 之外，禁止直接讀取 `FX_*` / `VALUATION_*` 環境變數
- ❌ 除 `app/fx/*` 之外，禁止直接 import provider 實作（`YahooFxProvider`、`CentralBankProvider` 等）
- ❌ 除 `app/fx/*` 之外，禁止直接讀取匯率 cache（Redis、DB）

**允許清單**：
- ✅ **唯一入口**：`from app.fx import get_fx_provider`（或同等 factory）
- ✅ 估值層（未來 Sprint 1-4.B）透過 DI 注入 `FxProvider` 介面

---

#### 規則 2：帳務層硬禁止呼叫 FX 模組

```bash
# 檢查命令：確認帳務層不呼叫 FX
grep -rn "from app.fx\|get_rate\|convert("   services/portfolio-service/app/position_rebuilder.py   services/portfolio-service/app/avg_cost_calculator.py

# 期望輸出：（空，無任何匹配）
```

**原因**：
- 帳務層（Accounting Layer）：只負責累積交易，使用原幣別（asset_ccy）
- 估值層（Valuation Layer）：未來 Sprint 1-4.B 才實作，負責折算與估值

**違規後果**：
- 🚫 PR 審查自動 reject
- 🚫 要求立即回退

---

#### 規則 3：Sprint 邊界明確化

| Sprint | 允許範圍 | 禁止項目 |
|--------|---------|---------|
| **1-4.A** | 介面定義 + Stub（同幣別可用、跨幣別必炸） | 真實 Provider、HTTP 請求、匯率 cache |
| **1-4.3** | 帳務重算（positions 表寫入，`u_pnl=0`） | 估值計算、匯率折算、FX 模組呼叫 |
| **1-4.B** | 估值層實作（匯率來源、cache、valuation 欄位） | 估值邏輯散落到非 valuation_service.py |

---

# Sprint: Prevent "Empty Rebuild" 驗收（前置條件檢查）

**目標**：把「rebuild_positions 成功但 symbols_count=0（其實是 trades 尚未 sync）」的問題變成可被系統強制保證的流程。

**核心原則**：讓前置條件變成系統合約，而不是操作習慣。前置條件不足就要「可證偽地」失敗，不准靜默成功。

---

## 🚨 問題陳述（Why）

**常見情況**（VM / 新環境）：
```bash
curl -X POST http://localhost:8001/portfolio/rebuild_positions?user_id=tony
# 回傳：status="succeeded", symbols_count=0, positions 表空

# 但實際上是 trades 表還沒資料（需要先 sync）
curl -X POST http://localhost:8001/portfolio/sync?user_id=tony
# sync 完才有 66 筆 trades

# 再 rebuild 才有意義
curl -X POST http://localhost:8001/portfolio/rebuild_positions?user_id=tony  
# 現在：status="succeeded", symbols_count=5, positions 表有資料
```

**危害**：
- 使用者誤判「rebuild 成功」但其實沒有實質效果
- automation 腳本無法判斷前置條件是否滿足
- 缺乏可證偽的失敗機制

---

## ✅ 解決方案（What）

### 1. 新增 `require_trades` 參數

**端點**：`POST /portfolio/rebuild_positions`

**新增 query 參數**：
- `require_trades: bool = false`（預設 false 保持相容）

**行為**：
- 當 `require_trades=true` 且 trades_count=0：
  - 回傳 **409 Conflict**
  - `status="precondition_failed"`
  - `symbols_count=0`
  - `evidence` 包含可證偽的 `verification_sql`

**範例（前置條件失敗）**：
```bash
curl -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=tony&require_trades=1"
```

回傳（409 Conflict）：
```json
{
  "detail": {
    "status": "precondition_failed",
    "user_id": "tony",
    "symbols_count": 0,
    "upserted_count": 0,
    "deleted_or_zeroed_count": 0,
    "run_id": "",
    "evidence": {
      "require_trades": true,
      "decision": "blocked_precondition",
      "trades_count": 0,
      "distinct_symbols_count": 0,
      "verification_sql": {
        "trades_count": "select count(*) from trades where user_id='tony';",
        "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';"
      }
    },
    "message": "前置條件不滿足：該用戶在 trades 表無交易記錄，無法執行 rebuild_positions（require_trades=true）"
  }
}
```

**範例（前置條件滿足）**：
```bash
# 先 sync
curl -X POST http://localhost:8001/portfolio/sync?user_id=tony

# 再 rebuild（require_trades=true）
curl -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=tony&require_trades=1"
```

回傳（200 OK）：
```json
{
  "status": "succeeded",
  "user_id": "tony",
  "symbols_count": 5,
  "upserted_count": 5,
  "deleted_or_zeroed_count": 0,
  "run_id": "...",
  "evidence": {
    "require_trades": true,
    "decision": "proceed",
    "trades_count": 66,
    "distinct_symbols_count": 5,
    "verification_sql": {
      "trades_count": "select count(*) from trades where user_id='tony';",
      "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';",
      "positions_count": "select count(*) from positions where user_id='tony';"
    },
    ...
  }
}
```

---

### 2. 新增輕量探針端點

**端點**：`GET /portfolio/trades/summary`

**用途**：
- 讓其他服務或腳本先確認前置條件（不需回傳完整 Trade 物件）
- automation 腳本可先打這個端點判斷是否需要呼叫 sync
- 診斷工具（確認 sync 是否成功）

**範例請求**：
```bash
curl -s "http://localhost:8001/portfolio/trades/summary?user_id=tony" | jq
```

**範例回應**：
```json
{
  "user_id": "tony",
  "trades_count": 66,
  "symbols_count": 5,
  "min_trade_date": "2024-01-01",
  "max_trade_date": "2024-12-31",
  "evidence": {
    "verification_sql": {
      "trades_count": "select count(*) from trades where user_id='tony';",
      "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';"
    }
  }
}
```

---

## 🧪 驗收命令（一鍵驗證）

```bash
# 1) 確認 trades summary
curl -s "http://localhost:8001/portfolio/trades/summary?user_id=tony" | jq

# 2) 嘗試 require_trades=1 的 rebuild（若 trades=0 應該被擋）
curl -s -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=tony&require_trades=1" | jq

# 3) 先 sync 再 rebuild（應該成功）
curl -s -X POST "http://localhost:8001/portfolio/sync?user_id=tony" | jq
curl -s -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=tony&require_trades=1" | jq

# 4) DB 驗證（positions 應該有資料）
docker compose exec -T postgres psql -U investment -d investment_db -c \
"select user_id, count(*) from positions where user_id='tony' group by user_id;"

# 5) 執行完整測試套件
docker compose exec -T portfolio-service \
  pytest tests/test_trades_summary_and_require_trades.py -v
# 期望：6 passed
```

---

## 📋 可證偽檢查清單

✅ **端點存在且回應正確**：
```bash
curl -s "http://localhost:8001/portfolio/trades/summary?user_id=tony" | jq .trades_count
# 應回傳數字（可能是 0 或 >0）

curl -s -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=tony&require_trades=0" | jq .status
# 應回傳 "succeeded"（require_trades=false 允許空 trades）
```

✅ **require_trades=true 能正確擋住空 trades**：
```bash
# 確保 tony 無 trades
docker compose exec -T postgres psql -U investment -d investment_db -c \
"delete from positions where user_id='tony'; delete from trades where user_id='tony';"

curl -s -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=tony&require_trades=1"
# HTTP 409, detail.status="precondition_failed", evidence.trades_count=0
```

✅ **evidence 包含可證偽的 verification_sql**：
```bash
curl -s -X POST "http://localhost:8001/portfolio/rebuild_positions?user_id=tony&require_trades=1" | jq .detail.evidence.verification_sql
# 應包含 trades_count 和 distinct_symbols 的 SQL 語句
```

✅ **測試通過**：
```bash
docker compose exec -T portfolio-service \
  pytest tests/test_trades_summary_and_require_trades.py -v
# 6 passed：
# - test_trades_summary_empty_returns_zero
# - test_trades_summary_after_insert_returns_counts
# - test_rebuild_positions_require_trades_blocks_when_empty
# - test_rebuild_positions_require_trades_proceeds_when_has_trades
# - test_rebuild_positions_default_require_trades_false_allows_empty
# - test_evidence_verification_sql_contains_all_required_fields
```

---

## 🔥 故障排除

### 問題：require_trades=1 但還是回傳 succeeded（應該回 409）

**診斷**：
```bash
# 檢查 trades 是否真的為空
docker compose exec -T postgres psql -U investment -d investment_db -c \
"select count(*) from trades where user_id='tony';"
```

**原因**：
- trades 表其實有資料（檢查是否有其他來源的交易）
- 端點邏輯未正確實作前置檢查

**解決**：
- 檢查 [main.py](services/portfolio-service/app/main.py) 的 `rebuild_positions` 函數
- 確認 `count_trades_for_user(db, user_id)` 被正確呼叫
- 確認 `if require_trades and trades_count == 0:` 邏輯存在

---

### 問題：trades/summary 回傳 404

**診斷**：
```bash
curl -v "http://localhost:8001/portfolio/trades/summary?user_id=tony"
```

**原因**：
- 端點未註冊或路徑錯誤
- portfolio-service 容器未重建（新程式碼未載入）

**解決**：
```bash
docker compose up -d --build portfolio-service
docker compose logs -f portfolio-service
# 檢查啟動日誌，確認端點註冊
```

---

### 問題：evidence.verification_sql 缺失

**診斷**：
```bash
curl -s "http://localhost:8001/portfolio/trades/summary?user_id=tony" | jq .evidence
# 應該有 verification_sql 欄位
```

**原因**：
- schema 未更新或回應未包含 evidence
- 端點邏輯缺少 evidence 組裝

**解決**：
- 檢查 [schemas.py](services/portfolio-service/app/schemas.py) 的 `TradesSummaryResponse`
- 檢查 [main.py](services/portfolio-service/app/main.py) 的 `get_trades_summary` 函數
- 確認回傳 dict 包含 `evidence` 和 `verification_sql` 欄位

---

## 🛡️ 設計邊界（禁止事項）

🚫 **禁止 rebuild_positions 內部偷偷呼叫 sync**：
- 避免副作用（API 應該單一職責）
- 避免隱性耗時（sync 可能很慢）
- 避免「看起來成功但其實做了很多事」

🚫 **禁止 require_trades 預設為 true**：
- 保持向後相容（既有行為不變）
- 使用者可選擇是否啟用嚴格模式

🚫 **禁止 valuation-service 直連 DB**：
- microservices 邊界：portfolio-service 是唯一能接觸 trades/positions DB 的服務
- valuation-service 只能透過 portfolio-service API 拿資料

---

## 📊 交付清單

✅ **程式碼**：
- [trades_repository.py](services/portfolio-service/app/trades_repository.py)：`count_trades_for_user()`, `count_distinct_symbols_for_user()`
- [schemas.py](services/portfolio-service/app/schemas.py)：`TradesSummaryResponse`
- [main.py](services/portfolio-service/app/main.py)：`GET /portfolio/trades/summary`, `rebuild_positions` 增加 `require_trades` 參數

✅ **測試**：
- [test_trades_summary_and_require_trades.py](services/portfolio-service/tests/test_trades_summary_and_require_trades.py)：6 個測試用例，全部通過

✅ **文件**：
- RUNBOOK.md：本節（操作手冊）
- Development.md：設計文件與技術決策

---

# Sprint 1-4.3 驗收：Positions 寫回（帳務層完成）

**目標**：從 `trades` 表重算並寫入 `positions` 表，只做帳務（qty/avg_cost/realized_pnl），不做估值/匯率。

**驗收命令**（可證偽）：

### 1. 測試套件通過

```bash
# 所有測試（無警告）
docker compose exec -T portfolio-service pytest -q
# 期望：93 passed, 1 skipped, <2s

# rebuild 相關測試
docker compose exec -T portfolio-service pytest -q -k rebuild
# 期望：16+ passed（寫入、冪等性、零持倉刪除）
```

### 2. API 回傳欄位驗證

```bash
# 呼叫 rebuild_positions（query 參數）
curl -s -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq

# 預期輸出：
# {
#   "status": "succeeded",
#   "user_id": "tony",
#   "symbols_count": <int>,
#   "upserted_count": <int>,
#   "deleted_or_zeroed_count": <int>,
#   "run_id": "<uuid>",
#   "evidence": {
#     "positions_columns": [
#       "user_id", "symbol", "asset_ccy", "quantity",
#       "avg_cost", "realized_pnl", "u_pnl", "last_updated_at"
#     ]
#   }
# }

# 驗證點：
# - run_id 為 UUID 格式
# - symbols_count >= 0
# - evidence.positions_columns 包含 8 個欄位
```

### 3. 資料庫寫入驗證（psql）

```bash
# 查看 positions 表結構
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "\d positions"

# 預期欄位：
# - quantity (numeric)
# - avg_cost (numeric)
# - realized_pnl (numeric)
# - u_pnl (numeric) ← 當前固定 0

# 查看實際資料
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "SELECT user_id, symbol, quantity, avg_cost, realized_pnl, u_pnl \
      FROM positions WHERE user_id='tony' LIMIT 5;"

# 驗證點：
# - u_pnl 固定為 0（不做估值）
# - quantity, avg_cost, realized_pnl 有真實數值
```

### 4. 禁止規則驗證（Guardrails）

```bash
# 帳務層禁止 FX 模組
grep -rn "from app.fx" services/portfolio-service/app/position_rebuilder.py
# 期望：（空）

# 帳務層禁止折算邏輯
grep -rn "fx\.convert\|fx\.get_rate\|target_ccy" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py
# 期望：（空）

# 估值層禁止 DB 直連
docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
# 期望：5 passed
```

**可證偽檢查清單**（Sprint 1-4.3 階段）：

- ✅ `rebuild_positions` 回傳包含 `run_id`, `symbols_count`, `evidence`
- ✅ positions 表有 `u_pnl` 欄位（但值固定為 0）
- ✅ 連續執行兩次 rebuild，結果一致（冪等性）
- ✅ 賣光持倉後，positions 表自動刪除該筆記錄
- ❌ positions 表**無**估值欄位（`valuation_ccy`, `market_value`, `market_price`）
- ❌ portfolio-service 不呼叫 FX 模組（grep 無匹配）
- ❌ valuation-service 不直連 DB（pytest guardrails 通過）

**Troubleshooting**（當寫入數量/金額不符時）：

1. **檢查 trades 來源**：
   ```sql
   SELECT user_id, symbol, asset_ccy, COUNT(*), SUM(quantity)
   FROM trades WHERE user_id='<user_id>' GROUP BY 1,2,3;
   ```

2. **檢查分組與排序**：
   ```bash
   grep -A 5 "group_by\|order_by" services/portfolio-service/app/position_rebuilder.py
   # 必須按 (user_id, symbol, asset_ccy) 分組，trade_date ASC 排序
   ```

3. **檢查 UPSERT 衝突鍵**：
   ```sql
   SELECT conname, pg_get_constraintdef(oid)
   FROM pg_constraint
   WHERE conrelid = 'positions'::regclass AND contype = 'u';
   -- 預期：(user_id, symbol, asset_ccy) 唯一索引
   ```

4. **驗證冪等性**（連續執行兩次）：
   ```bash
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   # 兩次結果應相同
   ```

---

**檢查範例**（Sprint 1-4.3 驗收）：

```bash
# 確認 Position 表無估值欄位
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions'    AND column_name ~ '(valuation|market_value)';"
# 期望輸出：(0 rows)

# 確認 u_pnl 欄位存在（帳務層固定填 0）
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions' AND column_name='u_pnl';"
# 期望輸出：'0'::numeric
```

#### 規則 4：帳務層不做折算（最陰險的發散來源）

**目的**：防止帳務邏輯（positions / avg cost / realized pnl）偷偷做匯率折算，確保架構邊界清晰。

**檢查命令**：

```bash
# 檢查帳務層模組是否呼叫 FX API
grep -rn "fx\.convert\|fx\.get_rate" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py \
  services/portfolio-service/app/repositories/trades_repository.py

# 期望輸出：（空，無任何匹配）
```

**禁止清單**：
- ❌ `app/position_rebuilder.py`、`avg_cost_calculator.py`、`trades_repository.py` 等**帳務模組**禁止呼叫 `fx.convert()` 或 `fx.get_rate()`
- ❌ 帳務層禁止匯率折算邏輯（看起來只是乘個匯率，實際上會讓架構崩潰）
- ❌ `rebuild_positions`、`calculate_avg_cost` 等帳務 API 禁止接受 `target_ccy` 參數

**允許清單**：
- ✅ **僅估值層模組**（Sprint 1-4.B 之後的 `valuation_service.py`、`valuation_module.py`）可呼叫 FX API
- ✅ 估值層必須透過 `app.fx.get_fx_provider()` 取得 provider（唯一入口）
- ✅ 帳務層只負責記錄原始幣別（`asset_ccy`）和原始金額，不做任何折算

**違規後果**：
- 架構邊界模糊，未來擴充估值層時會發現匯率邏輯散落各處
- Debug 時無法確定「這個數字是原始金額還是折算後金額」
- 測試時無法隔離帳務邏輯與估值邏輯

#### Sprint 1-4.B 驗收：valuation-service 估值 API

**目的**：落實估值層 API（HTTP-only 取數），並提供可證偽 evidence。

**檢查命令**：

```bash
# 1. 啟動估值服務
docker compose up -d --build valuation-service portfolio-service

# 2. 健康檢查（含 runtime guard 狀態）
curl -s http://localhost:8005/health | jq
# 期望欄位：service_name, portfolio_base_url, providers, runtime_guard_status

# 3. 估值 API（成功案例）
curl -s "http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=USD&as_of=2026-01-24" | jq
# 期望：status=succeeded + evidence.positions_hash + items[].fx_rate_to_base

# 4. 估值 API（失敗案例：trades_count=0）
curl -s -i "http://localhost:8005/valuation/portfolio?user_id=empty_user" | sed -n '1,20p'
# 期望：HTTP 409 + detail.status=precondition_failed + evidence.trades_count=0

# 5. Guardrails 測試（禁止 DB driver / DB env）
docker compose exec -T valuation-service pytest -q
# 期望：全部通過
```

**成功輸出範例（節錄）**：
```json
{
  "status": "succeeded",
  "user_id": "tony",
  "base_ccy": "USD",
  "as_of": "2026-01-24",
  "items": [
    {
      "symbol": "AAPL",
      "asset_ccy": "USD",
      "price": 18.5,
      "fx_rate_to_base": 1.0,
      "market_value": 185.0,
      "unrealized_pnl":  -15.0
    }
  ],
  "evidence": {
    "positions_count": 1,
    "positions_hash": "<sha256>",
    "trades_count": 2,
    "distinct_symbols_count": 1,
    "verification_sql": {
      "trades_count": "select count(*) from trades where user_id='tony';",
      "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';"
    },
    "providers": {
      "price_provider": "stub",
      "fx_provider": "stub",
      "as_of": "2026-01-24"
    }
  }
}
```

**失敗輸出範例（節錄）**：
```json
{
  "detail": {
    "status": "precondition_failed",
    "user_id": "empty_user",
    "evidence": {
      "trades_count": 0,
      "distinct_symbols_count": 0
    }
  }
}
```

---

### 原理說明

**為何禁止在 host venv 執行測試？**

```
Smart-Investment-stretegy/         ← repo root
├── .venv/                          ← host venv（沒有安裝 service 依賴）
├── services/
│   ├── api-gateway/
│   │   ├── requirements.txt        ← fastapi, httpx
│   │   └── tests/
│   └── portfolio-service/
│       ├── requirements.txt        ← fastapi, sqlalchemy, pandas
│       └── tests/
│           ├── test_fx.py          ← 需要 app.fx 模組
│           └── test_rebuild_*.py   ← 需要 app.models
└── pytest.ini                      ← pytest 會掃描所有 services/*/tests/
```

執行流程對比：

| 執行方式 | pytest 收集範圍 | Python 環境 | 結果 |
|---------|---------------|-----------|------|
| `pytest -q -k fx` (host venv) | **所有 services** | host venv（缺少依賴） | ❌ ModuleNotFoundError |
| `docker compose exec portfolio-service pytest -q -k fx` | **只有 portfolio-service** | 容器內（完整依賴） | ✅ 20 passed |

---

## 8. 常用指令速查

```bash
# 查看所有服務日誌
make docker-logs

# 手動重新部署（VM 上）
sudo /opt/radar-warroom/infra/vm/deploy.sh

# 匯出 Postgres 備份
docker compose exec -T postgres pg_dump -U investment investment_db > backups/$(date +%F).sql

# 執行 portfolio-service 驗收腳本
bash services/portfolio-service/verify_sprint_1-3.sh

# 查看最近一次 sync 的可觀測性資料
docker compose exec portfolio-service python -c "
from app.db import get_db_session
from app.models import SyncRun
with get_db_session() as session:
    latest = session.query(SyncRun).order_by(SyncRun.started_at.desc()).first()
    if latest:
        print(f'sheet_rows: {latest.sheet_rows_count}, valid: {latest.normalized_valid_count}, invalid: {latest.normalized_invalid_count}, duplicates: {latest.duplicates_count}')
"
```

## 9. Portfolio Service 可觀測性欄位參考（v0.2.3+）

| 欄位 | 說明 | 正常範圍 | 異常判斷 |
| --- | --- | --- | --- |
| `sheet_rows_count` | Google Sheets 總列數 | > 0 | = 0 代表連線失敗或空表 |
| `normalized_valid_count` | 成功轉換的筆數 | = inserted + duplicates | < sheet_rows 代表有格式錯誤 |
| `normalized_invalid_count` | 格式錯誤筆數 | = 0 | > 0 時檢查日誌找出錯誤行 |
| `duplicates_count` | 重複跳過筆數（hash 去重） | ≥ 0 | 若 = sheet_rows 代表全為舊資料 |
| `inserted_count` | 新插入筆數 | ≥ 0 | = 0 時檢查是否 Sheets 未更新 |

### Hash 版本控制機制（CANONICAL_VERSION="v1"）

- `source_hash` 由 `v1:<SHA-256>` 組成，用於去重
- 若未來欄位標準化規則改變（例如台股代號補零規則），需升級為 `v2`
- 不同版本的 hash 不會衝突，可安全共存於同一資料表
- **操作建議**：若需要重新計算所有交易的 hash，應在低峰時段進行批次更新

---

## Google Service Account 金鑰部署（docker compose secrets）

### 1. 問題症狀
- portfolio_refresh sync 500，常見錯誤：
  - `Is a directory: '/run/secrets/google_sa.json'`
- 需提供 `GOOGLE_SA_JSON_PATH`（推薦）或 `GOOGLE_SA_JSON`（已棄用）

### 2. 根因說明
- 若部署時直接用 `docker compose` 而未併入 `docker-compose.secrets.yml`，容器 runtime 會缺少 `GOOGLE_SA_JSON_PATH` 與金鑰檔案掛載，導致 sync 失敗。
- pr_check 可能只走 409 fallback，未驗出金鑰缺失，導致假過。

### 3. 標準解法
- 新增 repo root `dc.sh`，統一作為 compose 入口：
  ```sh
  docker compose -f docker-compose.yml -f docker-compose.secrets.yml --env-file .env "$@"
  ```
- `tools/pr_check.sh` 內所有 `docker compose ...` 指令一律改呼叫 `./dc.sh ...`（config/ps/exec/run 全部）

### 4. secrets mount 規範
- 金鑰檔案掛載到容器 `/run/keys/google_sa.json:ro`
- portfolio-service env 使用 `GOOGLE_SA_JSON_PATH=/run/keys/google_sa.json`
- 不使用 `/run/secrets`（避免 mount 變成 directory）

### 5. 驗收準則
- pr_check Step 5 env keys 必須出現 `GOOGLE_SA_JSON_PATH`
- pr_check Step 10 portfolio_refresh 顯示 completed 且 valuation API 回 200
- evidence_leak_check 必須 pass

---

# Sprint 1-4.3 驗收：Positions 寫回（帳務層完成）

**目標**：從 `trades` 表重算並寫入 `positions` 表，只做帳務（qty/avg_cost/realized_pnl），不做估值/匯率。

**驗收命令**（可證偽）：

### 1. 測試套件通過

```bash
# 所有測試（無警告）
docker compose exec -T portfolio-service pytest -q
# 期望：93 passed, 1 skipped, <2s

# rebuild 相關測試
docker compose exec -T portfolio-service pytest -q -k rebuild
# 期望：16+ passed（寫入、冪等性、零持倉刪除）
```

### 2. API 回傳欄位驗證

```bash
# 呼叫 rebuild_positions（query 參數）
curl -s -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq

# 預期輸出：
# {
#   "status": "succeeded",
#   "user_id": "tony",
#   "symbols_count": <int>,
#   "upserted_count": <int>,
#   "deleted_or_zeroed_count": <int>,
#   "run_id": "<uuid>",
#   "evidence": {
#     "positions_columns": [
#       "user_id", "symbol", "asset_ccy", "quantity",
#       "avg_cost", "realized_pnl", "u_pnl", "last_updated_at"
#     ]
#   }
# }

# 驗證點：
# - run_id 為 UUID 格式
# - symbols_count >= 0
# - evidence.positions_columns 包含 8 個欄位
```

### 3. 資料庫寫入驗證（psql）

```bash
# 查看 positions 表結構
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "\d positions"

# 預期欄位：
# - quantity (numeric)
# - avg_cost (numeric)
# - realized_pnl (numeric)
# - u_pnl (numeric) ← 當前固定 0

# 查看實際資料
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "SELECT user_id, symbol, quantity, ROUND(avg_cost::numeric, 2) as avg_cost \
      FROM positions WHERE user_id='tony' ORDER BY symbol;"

# 驗證點：
# - u_pnl 固定為 0（不做估值）
# - quantity, avg_cost, realized_pnl 有真實數值
```

### 4. 禁止規則驗證（Guardrails）

```bash
# 帳務層禁止 FX 模組
grep -rn "from app.fx" services/portfolio-service/app/position_rebuilder.py
# 期望：（空）

# 帳務層禁止折算邏輯
grep -rn "fx\.convert\|fx\.get_rate\|target_ccy" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py
# 期望：（空）

# 估值層禁止 DB 直連
docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
# 期望：5 passed
```

**可證偽檢查清單**（Sprint 1-4.3 階段）：

- ✅ `rebuild_positions` 回傳包含 `run_id`, `symbols_count`, `evidence`
- ✅ positions 表有 `u_pnl` 欄位（但值固定為 0）
- ✅ 連續執行兩次 rebuild，結果一致（冪等性）
- ✅ 賣光持倉後，positions 表自動刪除該筆記錄
- ❌ positions 表**無**估值欄位（`valuation_ccy`, `market_value`, `market_price`）
- ❌ portfolio-service 不呼叫 FX 模組（grep 無匹配）
- ❌ valuation-service 不直連 DB（pytest guardrails 通過）

**Troubleshooting**（當寫入數量/金額不符時）：

1. **檢查 trades 來源**：
   ```sql
   SELECT user_id, symbol, asset_ccy, COUNT(*), SUM(quantity)
   FROM trades WHERE user_id='<user_id>' GROUP BY 1,2,3;
   ```

2. **檢查分組與排序**：
   ```bash
   grep -A 5 "group_by\|order_by" services/portfolio-service/app/position_rebuilder.py
   # 必須按 (user_id, symbol, asset_ccy) 分組，trade_date ASC 排序
   ```

3. **檢查 UPSERT 衝突鍵**：
   ```sql
   SELECT conname, pg_get_constraintdef(oid)
   FROM pg_constraint
   WHERE conrelid = 'positions'::regclass AND contype = 'u';
   -- 預期：(user_id, symbol, asset_ccy) 唯一索引
   ```

4. **驗證冪等性**（連續執行兩次）：
   ```bash
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   # 兩次結果應相同
   ```

---

**檢查範例**（Sprint 1-4.3 驗收）：

```bash
# 確認 Position 表無估值欄位
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions'    AND column_name ~ '(valuation|market_value)';"
# 期望輸出：(0 rows)

# 確認 u_pnl 欄位存在（帳務層固定填 0）
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions' AND column_name='u_pnl';"
# 期望輸出：'0'::numeric
```

#### 規則 4：帳務層不做折算（最陰險的發散來源）

**目的**：防止帳務邏輯（positions / avg cost / realized pnl）偷偷做匯率折算，確保架構邊界清晰。

**檢查命令**：

```bash
# 檢查帳務層模組是否呼叫 FX API
grep -rn "fx\.convert\|fx\.get_rate" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py \
  services/portfolio-service/app/repositories/trades_repository.py

# 期望輸出：（空，無任何匹配）
```

**禁止清單**：
- ❌ `app/position_rebuilder.py`、`avg_cost_calculator.py`、`trades_repository.py` 等**帳務模組**禁止呼叫 `fx.convert()` 或 `fx.get_rate()`
- ❌ 帳務層禁止匯率折算邏輯（看起來只是乘個匯率，實際上會讓架構崩潰）
- ❌ `rebuild_positions`、`calculate_avg_cost` 等帳務 API 禁止接受 `target_ccy` 參數

**允許清單**：
- ✅ **僅估值層模組**（Sprint 1-4.B 之後的 `valuation_service.py`、`valuation_module.py`）可呼叫 FX API
- ✅ 估值層必須透過 `app.fx.get_fx_provider()` 取得 provider（唯一入口）
- ✅ 帳務層只負責記錄原始幣別（`asset_ccy`）和原始金額，不做任何折算

**違規後果**：
- 架構邊界模糊，未來擴充估值層時會發現匯率邏輯散落各處
- Debug 時無法確定「這個數字是原始金額還是折算後金額」
- 測試時無法隔離帳務邏輯與估值邏輯

#### Sprint 1-4.B 驗收：valuation-service 估值 API

**目的**：落實估值層 API（HTTP-only 取數），並提供可證偽 evidence。

**檢查命令**：

```bash
# 1. 啟動估值服務
docker compose up -d --build valuation-service portfolio-service

# 2. 健康檢查（含 runtime guard 狀態）
curl -s http://localhost:8005/health | jq
# 期望欄位：service_name, portfolio_base_url, providers, runtime_guard_status

# 3. 估值 API（成功案例）
curl -s "http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=USD&as_of=2026-01-24" | jq
# 期望：status=succeeded + evidence.positions_hash + items[].fx_rate_to_base

# 4. 估值 API（失敗案例：trades_count=0）
curl -s -i "http://localhost:8005/valuation/portfolio?user_id=empty_user" | sed -n '1,20p'
# 期望：HTTP 409 + detail.status=precondition_failed + evidence.trades_count=0

# 5. Guardrails 測試（禁止 DB driver / DB env）
docker compose exec -T valuation-service pytest -q
# 期望：全部通過
```

**成功輸出範例（節錄）**：
```json
{
  "status": "succeeded",
  "user_id": "tony",
  "base_ccy": "USD",
  "as_of": "2026-01-24",
  "items": [
    {
      "symbol": "AAPL",
      "asset_ccy": "USD",
      "price": 18.5,
      "fx_rate_to_base": 1.0,
      "market_value": 185.0,
      "unrealized_pnl":  -15.0
    }
  ],
  "evidence": {
    "positions_count": 1,
    "positions_hash": "<sha256>",
    "trades_count": 2,
    "distinct_symbols_count": 1,
    "verification_sql": {
      "trades_count": "select count(*) from trades where user_id='tony';",
      "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';"
    },
    "providers": {
      "price_provider": "stub",
      "fx_provider": "stub",
      "as_of": "2026-01-24"
    }
  }
}
```

**失敗輸出範例（節錄）**：
```json
{
  "detail": {
    "status": "precondition_failed",
    "user_id": "empty_user",
    "evidence": {
      "trades_count": 0,
      "distinct_symbols_count": 0
    }
  }
}
```

---

### 原理說明

**為何禁止在 host venv 執行測試？**

```
Smart-Investment-stretegy/         ← repo root
├── .venv/                          ← host venv（沒有安裝 service 依賴）
├── services/
│   ├── api-gateway/
│   │   ├── requirements.txt        ← fastapi, httpx
│   │   └── tests/
│   └── portfolio-service/
│       ├── requirements.txt        ← fastapi, sqlalchemy, pandas
│       └── tests/
│           ├── test_fx.py          ← 需要 app.fx 模組
│           └── test_rebuild_*.py   ← 需要 app.models
└── pytest.ini                      ← pytest 會掃描所有 services/*/tests/
```

執行流程對比：

| 執行方式 | pytest 收集範圍 | Python 環境 | 結果 |
|---------|---------------|-----------|------|
| `pytest -q -k fx` (host venv) | **所有 services** | host venv（缺少依賴） | ❌ ModuleNotFoundError |
| `docker compose exec portfolio-service pytest -q -k fx` | **只有 portfolio-service** | 容器內（完整依賴） | ✅ 20 passed |

---

## 8. 常用指令速查

```bash
# 查看所有服務日誌
make docker-logs

# 手動重新部署（VM 上）
sudo /opt/radar-warroom/infra/vm/deploy.sh

# 匯出 Postgres 備份
docker compose exec -T postgres pg_dump -U investment investment_db > backups/$(date +%F).sql

# 執行 portfolio-service 驗收腳本
bash services/portfolio-service/verify_sprint_1-3.sh

# 查看最近一次 sync 的可觀測性資料
docker compose exec portfolio-service python -c "
from app.db import get_db_session
from app.models import SyncRun
with get_db_session() as session:
    latest = session.query(SyncRun).order_by(SyncRun.started_at.desc()).first()
    if latest:
        print(f'sheet_rows: {latest.sheet_rows_count}, valid: {latest.normalized_valid_count}, invalid: {latest.normalized_invalid_count}, duplicates: {latest.duplicates_count}')
"
```

## 9. Portfolio Service 可觀測性欄位參考（v0.2.3+）

| 欄位 | 說明 | 正常範圍 | 異常判斷 |
| --- | --- | --- | --- |
| `sheet_rows_count` | Google Sheets 總列數 | > 0 | = 0 代表連線失敗或空表 |
| `normalized_valid_count` | 成功轉換的筆數 | = inserted + duplicates | < sheet_rows 代表有格式錯誤 |
| `normalized_invalid_count` | 格式錯誤筆數 | = 0 | > 0 時檢查日誌找出錯誤行 |
| `duplicates_count` | 重複跳過筆數（hash 去重） | ≥ 0 | 若 = sheet_rows 代表全為舊資料 |
| `inserted_count` | 新插入筆數 | ≥ 0 | = 0 時檢查是否 Sheets 未更新 |

### Hash 版本控制機制（CANONICAL_VERSION="v1"）

- `source_hash` 由 `v1:<SHA-256>` 組成，用於去重
- 若未來欄位標準化規則改變（例如台股代號補零規則），需升級為 `v2`
- 不同版本的 hash 不會衝突，可安全共存於同一資料表
- **操作建議**：若需要重新計算所有交易的 hash，應在低峰時段進行批次更新

---

## Google Service Account 金鑰部署（docker compose secrets）

### 1. 問題症狀
- portfolio_refresh sync 500，常見錯誤：
  - `Is a directory: '/run/secrets/google_sa.json'`
- 需提供 `GOOGLE_SA_JSON_PATH`（推薦）或 `GOOGLE_SA_JSON`（已棄用）

### 2. 根因說明
- 若部署時直接用 `docker compose` 而未併入 `docker-compose.secrets.yml`，容器 runtime 會缺少 `GOOGLE_SA_JSON_PATH` 與金鑰檔案掛載，導致 sync 失敗。
- pr_check 可能只走 409 fallback，未驗出金鑰缺失，導致假過。

### 3. 標準解法
- 新增 repo root `dc.sh`，統一作為 compose 入口：
  ```sh
  docker compose -f docker-compose.yml -f docker-compose.secrets.yml --env-file .env "$@"
  ```
- `tools/pr_check.sh` 內所有 `docker compose ...` 指令一律改呼叫 `./dc.sh ...`（config/ps/exec/run 全部）

### 4. secrets mount 規範
- 金鑰檔案掛載到容器 `/run/keys/google_sa.json:ro`
- portfolio-service env 使用 `GOOGLE_SA_JSON_PATH=/run/keys/google_sa.json`
- 不使用 `/run/secrets`（避免 mount 變成 directory）

### 5. 驗收準則
- pr_check Step 5 env keys 必須出現 `GOOGLE_SA_JSON_PATH`
- pr_check Step 10 portfolio_refresh 顯示 completed 且 valuation API 回 200
- evidence_leak_check 必須 pass

---

# Sprint 1-4.3 驗收：Positions 寫回（帳務層完成）

**目標**：從 `trades` 表重算並寫入 `positions` 表，只做帳務（qty/avg_cost/realized_pnl），不做估值/匯率。

**驗收命令**（可證偽）：

### 1. 測試套件通過

```bash
# 所有測試（無警告）
docker compose exec -T portfolio-service pytest -q
# 期望：93 passed, 1 skipped, <2s

# rebuild 相關測試
docker compose exec -T portfolio-service pytest -q -k rebuild
# 期望：16+ passed（寫入、冪等性、零持倉刪除）
```

### 2. API 回傳欄位驗證

```bash
# 呼叫 rebuild_positions（query 參數）
curl -s -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq

# 預期輸出：
# {
#   "status": "succeeded",
#   "user_id": "tony",
#   "symbols_count": <int>,
#   "upserted_count": <int>,
#   "deleted_or_zeroed_count": <int>,
#   "run_id": "<uuid>",
#   "evidence": {
#     "positions_columns": [
#       "user_id", "symbol", "asset_ccy", "quantity",
#       "avg_cost", "realized_pnl", "u_pnl", "last_updated_at"
#     ]
#   }
# }

# 驗證點：
# - run_id 為 UUID 格式
# - symbols_count >= 0
# - evidence.positions_columns 包含 8 個欄位
```

### 3. 資料庫寫入驗證（psql）

```bash
# 查看 positions 表結構
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "\d positions"

# 預期欄位：
# - quantity (numeric)
# - avg_cost (numeric)
# - realized_pnl (numeric)
# - u_pnl (numeric) ← 當前固定 0

# 查看實際資料
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "SELECT user_id, symbol, quantity, ROUND(avg_cost::numeric, 2) as avg_cost \
      FROM positions WHERE user_id='tony' ORDER BY symbol;"

# 驗證點：
# - u_pnl 固定為 0（不做估值）
# - quantity, avg_cost, realized_pnl 有真實數值
```

### 4. 禁止規則驗證（Guardrails）

```bash
# 帳務層禁止 FX 模組
grep -rn "from app.fx" services/portfolio-service/app/position_rebuilder.py
# 期望：（空）

# 帳務層禁止折算邏輯
grep -rn "fx\.convert\|fx\.get_rate\|target_ccy" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py
# 期望：（空）

# 估值層禁止 DB 直連
docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
# 期望：5 passed
```

**可證偽檢查清單**（Sprint 1-4.3 階段）：

- ✅ `rebuild_positions` 回傳包含 `run_id`, `symbols_count`, `evidence`
- ✅ positions 表有 `u_pnl` 欄位（但值固定為 0）
- ✅ 連續執行兩次 rebuild，結果一致（冪等性）
- ✅ 賣光持倉後，positions 表自動刪除該筆記錄
- ❌ positions 表**無**估值欄位（`valuation_ccy`, `market_value`, `market_price`）
- ❌ portfolio-service 不呼叫 FX 模組（grep 無匹配）
- ❌ valuation-service 不直連 DB（pytest guardrails 通過）

**Troubleshooting**（當寫入數量/金額不符時）：

1. **檢查 trades 來源**：
   ```sql
   SELECT user_id, symbol, asset_ccy, COUNT(*), SUM(quantity)
   FROM trades WHERE user_id='<user_id>' GROUP BY 1,2,3;
   ```

2. **檢查分組與排序**：
   ```bash
   grep -A 5 "group_by\|order_by" services/portfolio-service/app/position_rebuilder.py
   # 必須按 (user_id, symbol, asset_ccy) 分組，trade_date ASC 排序
   ```

3. **檢查 UPSERT 衝突鍵**：
   ```sql
   SELECT conname, pg_get_constraintdef(oid)
   FROM pg_constraint
   WHERE conrelid = 'positions'::regclass AND contype = 'u';
   -- 預期：(user_id, symbol, asset_ccy) 唯一索引
   ```

4. **驗證冪等性**（連續執行兩次）：
   ```bash
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   # 兩次結果應相同
   ```

---

**檢查範例**（Sprint 1-4.3 驗收）：

```bash
# 確認 Position 表無估值欄位
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions'    AND column_name ~ '(valuation|market_value)';"
# 期望輸出：(0 rows)

# 確認 u_pnl 欄位存在（帳務層固定填 0）
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions' AND column_name='u_pnl';"
# 期望輸出：'0'::numeric
```

#### 規則 4：帳務層不做折算（最陰險的發散來源）

**目的**：防止帳務邏輯（positions / avg cost / realized pnl）偷偷做匯率折算，確保架構邊界清晰。

**檢查命令**：

```bash
# 檢查帳務層模組是否呼叫 FX API
grep -rn "fx\.convert\|fx\.get_rate" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py \
  services/portfolio-service/app/repositories/trades_repository.py

# 期望輸出：（空，無任何匹配）
```

**禁止清單**：
- ❌ `app/position_rebuilder.py`、`avg_cost_calculator.py`、`trades_repository.py` 等**帳務模組**禁止呼叫 `fx.convert()` 或 `fx.get_rate()`
- ❌ 帳務層禁止匯率折算邏輯（看起來只是乘個匯率，實際上會讓架構崩潰）
- ❌ `rebuild_positions`、`calculate_avg_cost` 等帳務 API 禁止接受 `target_ccy` 參數

**允許清單**：
- ✅ **僅估值層模組**（Sprint 1-4.B 之後的 `valuation_service.py`、`valuation_module.py`）可呼叫 FX API
- ✅ 估值層必須透過 `app.fx.get_fx_provider()` 取得 provider（唯一入口）
- ✅ 帳務層只負責記錄原始幣別（`asset_ccy`）和原始金額，不做任何折算

**違規後果**：
- 架構邊界模糊，未來擴充估值層時會發現匯率邏輯散落各處
- Debug 時無法確定「這個數字是原始金額還是折算後金額」
- 測試時無法隔離帳務邏輯與估值邏輯

#### Sprint 1-4.B 驗收：valuation-service 估值 API

**目的**：落實估值層 API（HTTP-only 取數），並提供可證偽 evidence。

**檢查命令**：

```bash
# 1. 啟動估值服務
docker compose up -d --build valuation-service portfolio-service

# 2. 健康檢查（含 runtime guard 狀態）
curl -s http://localhost:8005/health | jq
# 期望欄位：service_name, portfolio_base_url, providers, runtime_guard_status

# 3. 估值 API（成功案例）
curl -s "http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=USD&as_of=2026-01-24" | jq
# 期望：status=succeeded + evidence.positions_hash + items[].fx_rate_to_base

# 4. 估值 API（失敗案例：trades_count=0）
curl -s -i "http://localhost:8005/valuation/portfolio?user_id=empty_user" | sed -n '1,20p'
# 期望：HTTP 409 + detail.status=precondition_failed + evidence.trades_count=0

# 5. Guardrails 測試（禁止 DB driver / DB env）
docker compose exec -T valuation-service pytest -q
# 期望：全部通過
```

**成功輸出範例（節錄）**：
```json
{
  "status": "succeeded",
  "user_id": "tony",
  "base_ccy": "USD",
  "as_of": "2026-01-24",
  "items": [
    {
      "symbol": "AAPL",
      "asset_ccy": "USD",
      "price": 18.5,
      "fx_rate_to_base": 1.0,
      "market_value": 185.0,
      "unrealized_pnl":  -15.0
    }
  ],
  "evidence": {
    "positions_count": 1,
    "positions_hash": "<sha256>",
    "trades_count": 2,
    "distinct_symbols_count": 1,
    "verification_sql": {
      "trades_count": "select count(*) from trades where user_id='tony';",
      "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';"
    },
    "providers": {
      "price_provider": "stub",
      "fx_provider": "stub",
      "as_of": "2026-01-24"
    }
  }
}
```

**失敗輸出範例（節錄）**：
```json
{
  "detail": {
    "status": "precondition_failed",
    "user_id": "empty_user",
    "evidence": {
      "trades_count": 0,
      "distinct_symbols_count": 0
    }
  }
}
```

---

### 原理說明

**為何禁止在 host venv 執行測試？**

```
Smart-Investment-stretegy/         ← repo root
├── .venv/                          ← host venv（沒有安裝 service 依賴）
├── services/
│   ├── api-gateway/
│   │   ├── requirements.txt        ← fastapi, httpx
│   │   └── tests/
│   └── portfolio-service/
│       ├── requirements.txt        ← fastapi, sqlalchemy, pandas
│       └── tests/
│           ├── test_fx.py          ← 需要 app.fx 模組
│           └── test_rebuild_*.py   ← 需要 app.models
└── pytest.ini                      ← pytest 會掃描所有 services/*/tests/
```

執行流程對比：

| 執行方式 | pytest 收集範圍 | Python 環境 | 結果 |
|---------|---------------|-----------|------|
| `pytest -q -k fx` (host venv) | **所有 services** | host venv（缺少依賴） | ❌ ModuleNotFoundError |
| `docker compose exec portfolio-service pytest -q -k fx` | **只有 portfolio-service** | 容器內（完整依賴） | ✅ 20 passed |

---

## 8. 常用指令速查

```bash
# 查看所有服務日誌
make docker-logs

# 手動重新部署（VM 上）
sudo /opt/radar-warroom/infra/vm/deploy.sh

# 匯出 Postgres 備份
docker compose exec -T postgres pg_dump -U investment investment_db > backups/$(date +%F).sql

# 執行 portfolio-service 驗收腳本
bash services/portfolio-service/verify_sprint_1-3.sh

# 查看最近一次 sync 的可觀測性資料
docker compose exec portfolio-service python -c "
from app.db import get_db_session
from app.models import SyncRun
with get_db_session() as session:
    latest = session.query(SyncRun).order_by(SyncRun.started_at.desc()).first()
    if latest:
        print(f'sheet_rows: {latest.sheet_rows_count}, valid: {latest.normalized_valid_count}, invalid: {latest.normalized_invalid_count}, duplicates: {latest.duplicates_count}')
"
```

## 9. Portfolio Service 可觀測性欄位參考（v0.2.3+）

| 欄位 | 說明 | 正常範圍 | 異常判斷 |
| --- | --- | --- | --- |
| `sheet_rows_count` | Google Sheets 總列數 | > 0 | = 0 代表連線失敗或空表 |
| `normalized_valid_count` | 成功轉換的筆數 | = inserted + duplicates | < sheet_rows 代表有格式錯誤 |
| `normalized_invalid_count` | 格式錯誤筆數 | = 0 | > 0 時檢查日誌找出錯誤行 |
| `duplicates_count` | 重複跳過筆數（hash 去重） | ≥ 0 | 若 = sheet_rows 代表全為舊資料 |
| `inserted_count` | 新插入筆數 | ≥ 0 | = 0 時檢查是否 Sheets 未更新 |

### Hash 版本控制機制（CANONICAL_VERSION="v1"）

- `source_hash` 由 `v1:<SHA-256>` 組成，用於去重
- 若未來欄位標準化規則改變（例如台股代號補零規則），需升級為 `v2`
- 不同版本的 hash 不會衝突，可安全共存於同一資料表
- **操作建議**：若需要重新計算所有交易的 hash，應在低峰時段進行批次更新

---

## Google Service Account 金鑰部署（docker compose secrets）

### 1. 問題症狀
- portfolio_refresh sync 500，常見錯誤：
  - `Is a directory: '/run/secrets/google_sa.json'`
- 需提供 `GOOGLE_SA_JSON_PATH`（推薦）或 `GOOGLE_SA_JSON`（已棄用）

### 2. 根因說明
- 若部署時直接用 `docker compose` 而未併入 `docker-compose.secrets.yml`，容器 runtime 會缺少 `GOOGLE_SA_JSON_PATH` 與金鑰檔案掛載，導致 sync 失敗。
- pr_check 可能只走 409 fallback，未驗出金鑰缺失，導致假過。

### 3. 標準解法
- 新增 repo root `dc.sh`，統一作為 compose 入口：
  ```sh
  docker compose -f docker-compose.yml -f docker-compose.secrets.yml --env-file .env "$@"
  ```
- `tools/pr_check.sh` 內所有 `docker compose ...` 指令一律改呼叫 `./dc.sh ...`（config/ps/exec/run 全部）

### 4. secrets mount 規範
- 金鑰檔案掛載到容器 `/run/keys/google_sa.json:ro`
- portfolio-service env 使用 `GOOGLE_SA_JSON_PATH=/run/keys/google_sa.json`
- 不使用 `/run/secrets`（避免 mount 變成 directory）

### 5. 驗收準則
- pr_check Step 5 env keys 必須出現 `GOOGLE_SA_JSON_PATH`
- pr_check Step 10 portfolio_refresh 顯示 completed 且 valuation API 回 200
- evidence_leak_check 必須 pass

---

# Sprint 1-4.3 驗收：Positions 寫回（帳務層完成）

**目標**：從 `trades` 表重算並寫入 `positions` 表，只做帳務（qty/avg_cost/realized_pnl），不做估值/匯率。

**驗收命令**（可證偽）：

### 1. 測試套件通過

```bash
# 所有測試（無警告）
docker compose exec -T portfolio-service pytest -q
# 期望：93 passed, 1 skipped, <2s

# rebuild 相關測試
docker compose exec -T portfolio-service pytest -q -k rebuild
# 期望：16+ passed（寫入、冪等性、零持倉刪除）
```

### 2. API 回傳欄位驗證

```bash
# 呼叫 rebuild_positions（query 參數）
curl -s -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq

# 預期輸出：
# {
#   "status": "succeeded",
#   "user_id": "tony",
#   "symbols_count": <int>,
#   "upserted_count": <int>,
#   "deleted_or_zeroed_count": <int>,
#   "run_id": "<uuid>",
#   "evidence": {
#     "positions_columns": [
#       "user_id", "symbol", "asset_ccy", "quantity",
#       "avg_cost", "realized_pnl", "u_pnl", "last_updated_at"
#     ]
#   }
# }

# 驗證點：
# - run_id 為 UUID 格式
# - symbols_count >= 0
# - evidence.positions_columns 包含 8 個欄位
```

### 3. 資料庫寫入驗證（psql）

```bash
# 查看 positions 表結構
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "\d positions"

# 預期欄位：
# - quantity (numeric)
# - avg_cost (numeric)
# - realized_pnl (numeric)
# - u_pnl (numeric) ← 當前固定 0

# 查看實際資料
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "SELECT user_id, symbol, quantity, ROUND(avg_cost::numeric, 2) as avg_cost \
      FROM positions WHERE user_id='tony' ORDER BY symbol;"

# 驗證點：
# - u_pnl 固定為 0（不做估值）
# - quantity, avg_cost, realized_pnl 有真實數值
```

### 4. 禁止規則驗證（Guardrails）

```bash
# 帳務層禁止 FX 模組
grep -rn "from app.fx" services/portfolio-service/app/position_rebuilder.py
# 期望：（空）

# 帳務層禁止折算邏輯
grep -rn "fx\.convert\|fx\.get_rate\|target_ccy" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py
# 期望：（空）

# 估值層禁止 DB 直連
docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
# 期望：5 passed
```

**可證偽檢查清單**（Sprint 1-4.3 階段）：

- ✅ `rebuild_positions` 回傳包含 `run_id`, `symbols_count`, `evidence`
- ✅ positions 表有 `u_pnl` 欄位（但值固定為 0）
- ✅ 連續執行兩次 rebuild，結果一致（冪等性）
- ✅ 賣光持倉後，positions 表自動刪除該筆記錄
- ❌ positions 表**無**估值欄位（`valuation_ccy`, `market_value`, `market_price`）
- ❌ portfolio-service 不呼叫 FX 模組（grep 無匹配）
- ❌ valuation-service 不直連 DB（pytest guardrails 通過）

**Troubleshooting**（當寫入數量/金額不符時）：

1. **檢查 trades 來源**：
   ```sql
   SELECT user_id, symbol, asset_ccy, COUNT(*), SUM(quantity)
   FROM trades WHERE user_id='<user_id>' GROUP BY 1,2,3;
   ```

2. **檢查分組與排序**：
   ```bash
   grep -A 5 "group_by\|order_by" services/portfolio-service/app/position_rebuilder.py
   # 必須按 (user_id, symbol, asset_ccy) 分組，trade_date ASC 排序
   ```

3. **檢查 UPSERT 衝突鍵**：
   ```sql
   SELECT conname, pg_get_constraintdef(oid)
   FROM pg_constraint
   WHERE conrelid = 'positions'::regclass AND contype = 'u';
   -- 預期：(user_id, symbol, asset_ccy) 唯一索引
   ```

4. **驗證冪等性**（連續執行兩次）：
   ```bash
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   # 兩次結果應相同
   ```

---

**檢查範例**（Sprint 1-4.3 驗收）：

```bash
# 確認 Position 表無估值欄位
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions'    AND column_name ~ '(valuation|market_value)';"
# 期望輸出：(0 rows)

# 確認 u_pnl 欄位存在（帳務層固定填 0）
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions' AND column_name='u_pnl';"
# 期望輸出：'0'::numeric
```

#### 規則 4：帳務層不做折算（最陰險的發散來源）

**目的**：防止帳務邏輯（positions / avg cost / realized pnl）偷偷做匯率折算，確保架構邊界清晰。

**檢查命令**：

```bash
# 檢查帳務層模組是否呼叫 FX API
grep -rn "fx\.convert\|fx\.get_rate" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py \
  services/portfolio-service/app/repositories/trades_repository.py

# 期望輸出：（空，無任何匹配）
```

**禁止清單**：
- ❌ `app/position_rebuilder.py`、`avg_cost_calculator.py`、`trades_repository.py` 等**帳務模組**禁止呼叫 `fx.convert()` 或 `fx.get_rate()`
- ❌ 帳務層禁止匯率折算邏輯（看起來只是乘個匯率，實際上會讓架構崩潰）
- ❌ `rebuild_positions`、`calculate_avg_cost` 等帳務 API 禁止接受 `target_ccy` 參數

**允許清單**：
- ✅ **僅估值層模組**（Sprint 1-4.B 之後的 `valuation_service.py`、`valuation_module.py`）可呼叫 FX API
- ✅ 估值層必須透過 `app.fx.get_fx_provider()` 取得 provider（唯一入口）
- ✅ 帳務層只負責記錄原始幣別（`asset_ccy`）和原始金額，不做任何折算

**違規後果**：
- 架構邊界模糊，未來擴充估值層時會發現匯率邏輯散落各處
- Debug 時無法確定「這個數字是原始金額還是折算後金額」
- 測試時無法隔離帳務邏輯與估值邏輯

#### Sprint 1-4.B 驗收：valuation-service 估值 API

**目的**：落實估值層 API（HTTP-only 取數），並提供可證偽 evidence。

**檢查命令**：

```bash
# 1. 啟動估值服務
docker compose up -d --build valuation-service portfolio-service

# 2. 健康檢查（含 runtime guard 狀態）
curl -s http://localhost:8005/health | jq
# 期望欄位：service_name, portfolio_base_url, providers, runtime_guard_status

# 3. 估值 API（成功案例）
curl -s "http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=USD&as_of=2026-01-24" | jq
# 期望：status=succeeded + evidence.positions_hash + items[].fx_rate_to_base

# 4. 估值 API（失敗案例：trades_count=0）
curl -s -i "http://localhost:8005/valuation/portfolio?user_id=empty_user" | sed -n '1,20p'
# 期望：HTTP 409 + detail.status=precondition_failed + evidence.trades_count=0

# 5. Guardrails 測試（禁止 DB driver / DB env）
docker compose exec -T valuation-service pytest -q
# 期望：全部通過
```

**成功輸出範例（節錄）**：
```json
{
  "status": "succeeded",
  "user_id": "tony",
  "base_ccy": "USD",
  "as_of": "2026-01-24",
  "items": [
    {
      "symbol": "AAPL",
      "asset_ccy": "USD",
      "price": 18.5,
      "fx_rate_to_base": 1.0,
      "market_value": 185.0,
      "unrealized_pnl":  -15.0
    }
  ],
  "evidence": {
    "positions_count": 1,
    "positions_hash": "<sha256>",
    "trades_count": 2,
    "distinct_symbols_count": 1,
    "verification_sql": {
      "trades_count": "select count(*) from trades where user_id='tony';",
      "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';"
    },
    "providers": {
      "price_provider": "stub",
      "fx_provider": "stub",
      "as_of": "2026-01-24"
    }
  }
}
```

**失敗輸出範例（節錄）**：
```json
{
  "detail": {
    "status": "precondition_failed",
    "user_id": "empty_user",
    "evidence": {
      "trades_count": 0,
      "distinct_symbols_count": 0
    }
  }
}
```

---

### 原理說明

**為何禁止在 host venv 執行測試？**

```
Smart-Investment-stretegy/         ← repo root
├── .venv/                          ← host venv（沒有安裝 service 依賴）
├── services/
│   ├── api-gateway/
│   │   ├── requirements.txt        ← fastapi, httpx
│   │   └── tests/
│   └── portfolio-service/
│       ├── requirements.txt        ← fastapi, sqlalchemy, pandas
│       └── tests/
│           ├── test_fx.py          ← 需要 app.fx 模組
│           └── test_rebuild_*.py   ← 需要 app.models
└── pytest.ini                      ← pytest 會掃描所有 services/*/tests/
```

執行流程對比：

| 執行方式 | pytest 收集範圍 | Python 環境 | 結果 |
|---------|---------------|-----------|------|
| `pytest -q -k fx` (host venv) | **所有 services** | host venv（缺少依賴） | ❌ ModuleNotFoundError |
| `docker compose exec portfolio-service pytest -q -k fx` | **只有 portfolio-service** | 容器內（完整依賴） | ✅ 20 passed |

---

## 8. 常用指令速查

```bash
# 查看所有服務日誌
make docker-logs

# 手動重新部署（VM 上）
sudo /opt/radar-warroom/infra/vm/deploy.sh

# 匯出 Postgres 備份
docker compose exec -T postgres pg_dump -U investment investment_db > backups/$(date +%F).sql

# 執行 portfolio-service 驗收腳本
bash services/portfolio-service/verify_sprint_1-3.sh

# 查看最近一次 sync 的可觀測性資料
docker compose exec portfolio-service python -c "
from app.db import get_db_session
from app.models import SyncRun
with get_db_session() as session:
    latest = session.query(SyncRun).order_by(SyncRun.started_at.desc()).first()
    if latest:
        print(f'sheet_rows: {latest.sheet_rows_count}, valid: {latest.normalized_valid_count}, invalid: {latest.normalized_invalid_count}, duplicates: {latest.duplicates_count}')
"
```

## 9. Portfolio Service 可觀測性欄位參考（v0.2.3+）

| 欄位 | 說明 | 正常範圍 | 異常判斷 |
| --- | --- | --- | --- |
| `sheet_rows_count` | Google Sheets 總列數 | > 0 | = 0 代表連線失敗或空表 |
| `normalized_valid_count` | 成功轉換的筆數 | = inserted + duplicates | < sheet_rows 代表有格式錯誤 |
| `normalized_invalid_count` | 格式錯誤筆數 | = 0 | > 0 時檢查日誌找出錯誤行 |
| `duplicates_count` | 重複跳過筆數（hash 去重） | ≥ 0 | 若 = sheet_rows 代表全為舊資料 |
| `inserted_count` | 新插入筆數 | ≥ 0 | = 0 時檢查是否 Sheets 未更新 |

### Hash 版本控制機制（CANONICAL_VERSION="v1"）

- `source_hash` 由 `v1:<SHA-256>` 組成，用於去重
- 若未來欄位標準化規則改變（例如台股代號補零規則），需升級為 `v2`
- 不同版本的 hash 不會衝突，可安全共存於同一資料表
- **操作建議**：若需要重新計算所有交易的 hash，應在低峰時段進行批次更新

---

## Google Service Account 金鑰部署（docker compose secrets）

### 1. 問題症狀
- portfolio_refresh sync 500，常見錯誤：
  - `Is a directory: '/run/secrets/google_sa.json'`
- 需提供 `GOOGLE_SA_JSON_PATH`（推薦）或 `GOOGLE_SA_JSON`（已棄用）

### 2. 根因說明
- 若部署時直接用 `docker compose` 而未併入 `docker-compose.secrets.yml`，容器 runtime 會缺少 `GOOGLE_SA_JSON_PATH` 與金鑰檔案掛載，導致 sync 失敗。
- pr_check 可能只走 409 fallback，未驗出金鑰缺失，導致假過。

### 3. 標準解法
- 新增 repo root `dc.sh`，統一作為 compose 入口：
  ```sh
  docker compose -f docker-compose.yml -f docker-compose.secrets.yml --env-file .env "$@"
  ```
- `tools/pr_check.sh` 內所有 `docker compose ...` 指令一律改呼叫 `./dc.sh ...`（config/ps/exec/run 全部）

### 4. secrets mount 規範
- 金鑰檔案掛載到容器 `/run/keys/google_sa.json:ro`
- portfolio-service env 使用 `GOOGLE_SA_JSON_PATH=/run/keys/google_sa.json`
- 不使用 `/run/secrets`（避免 mount 變成 directory）

### 5. 驗收準則
- pr_check Step 5 env keys 必須出現 `GOOGLE_SA_JSON_PATH`
- pr_check Step 10 portfolio_refresh 顯示 completed 且 valuation API 回 200
- evidence_leak_check 必須 pass

---

# Sprint 1-4.3 驗收：Positions 寫回（帳務層完成）

**目標**：從 `trades` 表重算並寫入 `positions` 表，只做帳務（qty/avg_cost/realized_pnl），不做估值/匯率。

**驗收命令**（可證偽）：

### 1. 測試套件通過

```bash
# 所有測試（無警告）
docker compose exec -T portfolio-service pytest -q
# 期望：93 passed, 1 skipped, <2s

# rebuild 相關測試
docker compose exec -T portfolio-service pytest -q -k rebuild
# 期望：16+ passed（寫入、冪等性、零持倉刪除）
```

### 2. API 回傳欄位驗證

```bash
# 呼叫 rebuild_positions（query 參數）
curl -s -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq

# 預期輸出：
# {
#   "status": "succeeded",
#   "user_id": "tony",
#   "symbols_count": <int>,
#   "upserted_count": <int>,
#   "deleted_or_zeroed_count": <int>,
#   "run_id": "<uuid>",
#   "evidence": {
#     "positions_columns": [
#       "user_id", "symbol", "asset_ccy", "quantity",
#       "avg_cost", "realized_pnl", "u_pnl", "last_updated_at"
#     ]
#   }
# }

# 驗證點：
# - run_id 為 UUID 格式
# - symbols_count >= 0
# - evidence.positions_columns 包含 8 個欄位
```

### 3. 資料庫寫入驗證（psql）

```bash
# 查看 positions 表結構
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "\d positions"

# 預期欄位：
# - quantity (numeric)
# - avg_cost (numeric)
# - realized_pnl (numeric)
# - u_pnl (numeric) ← 當前固定 0

# 查看實際資料
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "SELECT user_id, symbol, quantity, ROUND(avg_cost::numeric, 2) as avg_cost \
      FROM positions WHERE user_id='tony' ORDER BY symbol;"

# 驗證點：
# - u_pnl 固定為 0（不做估值）
# - quantity, avg_cost, realized_pnl 有真實數值
```

### 4. 禁止規則驗證（Guardrails）

```bash
# 帳務層禁止 FX 模組
grep -rn "from app.fx" services/portfolio-service/app/position_rebuilder.py
# 期望：（空）

# 帳務層禁止折算邏輯
grep -rn "fx\.convert\|fx\.get_rate\|target_ccy" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py
# 期望：（空）

# 估值層禁止 DB 直連
docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
# 期望：5 passed
```

**可證偽檢查清單**（Sprint 1-4.3 階段）：

- ✅ `rebuild_positions` 回傳包含 `run_id`, `symbols_count`, `evidence`
- ✅ positions 表有 `u_pnl` 欄位（但值固定為 0）
- ✅ 連續執行兩次 rebuild，結果一致（冪等性）
- ✅ 賣光持倉後，positions 表自動刪除該筆記錄
- ❌ positions 表**無**估值欄位（`valuation_ccy`, `market_value`, `market_price`）
- ❌ portfolio-service 不呼叫 FX 模組（grep 無匹配）
- ❌ valuation-service 不直連 DB（pytest guardrails 通過）

**Troubleshooting**（當寫入數量/金額不符時）：

1. **檢查 trades 來源**：
   ```sql
   SELECT user_id, symbol, asset_ccy, COUNT(*), SUM(quantity)
   FROM trades WHERE user_id='<user_id>' GROUP BY 1,2,3;
   ```

2. **檢查分組與排序**：
   ```bash
   grep -A 5 "group_by\|order_by" services/portfolio-service/app/position_rebuilder.py
   # 必須按 (user_id, symbol, asset_ccy) 分組，trade_date ASC 排序
   ```

3. **檢查 UPSERT 衝突鍵**：
   ```sql
   SELECT conname, pg_get_constraintdef(oid)
   FROM pg_constraint
   WHERE conrelid = 'positions'::regclass AND contype = 'u';
   -- 預期：(user_id, symbol, asset_ccy) 唯一索引
   ```

4. **驗證冪等性**（連續執行兩次）：
   ```bash
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   # 兩次結果應相同
   ```

---

**檢查範例**（Sprint 1-4.3 驗收）：

```bash
# 確認 Position 表無估值欄位
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions'    AND column_name ~ '(valuation|market_value)';"
# 期望輸出：(0 rows)

# 確認 u_pnl 欄位存在（帳務層固定填 0）
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions' AND column_name='u_pnl';"
# 期望輸出：'0'::numeric
```

#### 規則 4：帳務層不做折算（最陰險的發散來源）

**目的**：防止帳務邏輯（positions / avg cost / realized pnl）偷偷做匯率折算，確保架構邊界清晰。

**檢查命令**：

```bash
# 檢查帳務層模組是否呼叫 FX API
grep -rn "fx\.convert\|fx\.get_rate" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py \
  services/portfolio-service/app/repositories/trades_repository.py

# 期望輸出：（空，無任何匹配）
```

**禁止清單**：
- ❌ `app/position_rebuilder.py`、`avg_cost_calculator.py`、`trades_repository.py` 等**帳務模組**禁止呼叫 `fx.convert()` 或 `fx.get_rate()`
- ❌ 帳務層禁止匯率折算邏輯（看起來只是乘個匯率，實際上會讓架構崩潰）
- ❌ `rebuild_positions`、`calculate_avg_cost` 等帳務 API 禁止接受 `target_ccy` 參數

**允許清單**：
- ✅ **僅估值層模組**（Sprint 1-4.B 之後的 `valuation_service.py`、`valuation_module.py`）可呼叫 FX API
- ✅ 估值層必須透過 `app.fx.get_fx_provider()` 取得 provider（唯一入口）
- ✅ 帳務層只負責記錄原始幣別（`asset_ccy`）和原始金額，不做任何折算

**違規後果**：
- 架構邊界模糊，未來擴充估值層時會發現匯率邏輯散落各處
- Debug 時無法確定「這個數字是原始金額還是折算後金額」
- 測試時無法隔離帳務邏輯與估值邏輯

#### Sprint 1-4.B 驗收：valuation-service 估值 API

**目的**：落實估值層 API（HTTP-only 取數），並提供可證偽 evidence。

**檢查命令**：

```bash
# 1. 啟動估值服務
docker compose up -d --build valuation-service portfolio-service

# 2. 健康檢查（含 runtime guard 狀態）
curl -s http://localhost:8005/health | jq
# 期望欄位：service_name, portfolio_base_url, providers, runtime_guard_status

# 3. 估值 API（成功案例）
curl -s "http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=USD&as_of=2026-01-24" | jq
# 期望：status=succeeded + evidence.positions_hash + items[].fx_rate_to_base

# 4. 估值 API（失敗案例：trades_count=0）
curl -s -i "http://localhost:8005/valuation/portfolio?user_id=empty_user" | sed -n '1,20p'
# 期望：HTTP 409 + detail.status=precondition_failed + evidence.trades_count=0

# 5. Guardrails 測試（禁止 DB driver / DB env）
docker compose exec -T valuation-service pytest -q
# 期望：全部通過
```

**成功輸出範例（節錄）**：
```json
{
  "status": "succeeded",
  "user_id": "tony",
  "base_ccy": "USD",
  "as_of": "2026-01-24",
  "items": [
    {
      "symbol": "AAPL",
      "asset_ccy": "USD",
      "price": 18.5,
      "fx_rate_to_base": 1.0,
      "market_value": 185.0,
      "unrealized_pnl":  -15.0
    }
  ],
  "evidence": {
    "positions_count": 1,
    "positions_hash": "<sha256>",
    "trades_count": 2,
    "distinct_symbols_count": 1,
    "verification_sql": {
      "trades_count": "select count(*) from trades where user_id='tony';",
      "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';"
    },
    "providers": {
      "price_provider": "stub",
      "fx_provider": "stub",
      "as_of": "2026-01-24"
    }
  }
}
```

**失敗輸出範例（節錄）**：
```json
{
  "detail": {
    "status": "precondition_failed",
    "user_id": "empty_user",
    "evidence": {
      "trades_count": 0,
      "distinct_symbols_count": 0
    }
  }
}
```

---

### 原理說明

**為何禁止在 host venv 執行測試？**

```
Smart-Investment-stretegy/         ← repo root
├── .venv/                          ← host venv（沒有安裝 service 依賴）
├── services/
│   ├── api-gateway/
│   │   ├── requirements.txt        ← fastapi, httpx
│   │   └── tests/
│   └── portfolio-service/
│       ├── requirements.txt        ← fastapi, sqlalchemy, pandas
│       └── tests/
│           ├── test_fx.py          ← 需要 app.fx 模組
│           └── test_rebuild_*.py   ← 需要 app.models
└── pytest.ini                      ← pytest 會掃描所有 services/*/tests/
```

執行流程對比：

| 執行方式 | pytest 收集範圍 | Python 環境 | 結果 |
|---------|---------------|-----------|------|
| `pytest -q -k fx` (host venv) | **所有 services** | host venv（缺少依賴） | ❌ ModuleNotFoundError |
| `docker compose exec portfolio-service pytest -q -k fx` | **只有 portfolio-service** | 容器內（完整依賴） | ✅ 20 passed |

---

## 8. 常用指令速查

```bash
# 查看所有服務日誌
make docker-logs

# 手動重新部署（VM 上）
sudo /opt/radar-warroom/infra/vm/deploy.sh

# 匯出 Postgres 備份
docker compose exec -T postgres pg_dump -U investment investment_db > backups/$(date +%F).sql

# 執行 portfolio-service 驗收腳本
bash services/portfolio-service/verify_sprint_1-3.sh

# 查看最近一次 sync 的可觀測性資料
docker compose exec portfolio-service python -c "
from app.db import get_db_session
from app.models import SyncRun
with get_db_session() as session:
    latest = session.query(SyncRun).order_by(SyncRun.started_at.desc()).first()
    if latest:
        print(f'sheet_rows: {latest.sheet_rows_count}, valid: {latest.normalized_valid_count}, invalid: {latest.normalized_invalid_count}, duplicates: {latest.duplicates_count}')
"
```

## 9. Portfolio Service 可觀測性欄位參考（v0.2.3+）

| 欄位 | 說明 | 正常範圍 | 異常判斷 |
| --- | --- | --- | --- |
| `sheet_rows_count` | Google Sheets 總列數 | > 0 | = 0 代表連線失敗或空表 |
| `normalized_valid_count` | 成功轉換的筆數 | = inserted + duplicates | < sheet_rows 代表有格式錯誤 |
| `normalized_invalid_count` | 格式錯誤筆數 | = 0 | > 0 時檢查日誌找出錯誤行 |
| `duplicates_count` | 重複跳過筆數（hash 去重） | ≥ 0 | 若 = sheet_rows 代表全為舊資料 |
| `inserted_count` | 新插入筆數 | ≥ 0 | = 0 時檢查是否 Sheets 未更新 |

### Hash 版本控制機制（CANONICAL_VERSION="v1"）

- `source_hash` 由 `v1:<SHA-256>` 組成，用於去重
- 若未來欄位標準化規則改變（例如台股代號補零規則），需升級為 `v2`
- 不同版本的 hash 不會衝突，可安全共存於同一資料表
- **操作建議**：若需要重新計算所有交易的 hash，應在低峰時段進行批次更新

---

## Google Service Account 金鑰部署（docker compose secrets）

### 1. 問題症狀
- portfolio_refresh sync 500，常見錯誤：
  - `Is a directory: '/run/secrets/google_sa.json'`
- 需提供 `GOOGLE_SA_JSON_PATH`（推薦）或 `GOOGLE_SA_JSON`（已棄用）

### 2. 根因說明
- 若部署時直接用 `docker compose` 而未併入 `docker-compose.secrets.yml`，容器 runtime 會缺少 `GOOGLE_SA_JSON_PATH` 與金鑰檔案掛載，導致 sync 失敗。
- pr_check 可能只走 409 fallback，未驗出金鑰缺失，導致假過。

### 3. 標準解法
- 新增 repo root `dc.sh`，統一作為 compose 入口：
  ```sh
  docker compose -f docker-compose.yml -f docker-compose.secrets.yml --env-file .env "$@"
  ```
- `tools/pr_check.sh` 內所有 `docker compose ...` 指令一律改呼叫 `./dc.sh ...`（config/ps/exec/run 全部）

### 4. secrets mount 規範
- 金鑰檔案掛載到容器 `/run/keys/google_sa.json:ro`
- portfolio-service env 使用 `GOOGLE_SA_JSON_PATH=/run/keys/google_sa.json`
- 不使用 `/run/secrets`（避免 mount 變成 directory）

### 5. 驗收準則
- pr_check Step 5 env keys 必須出現 `GOOGLE_SA_JSON_PATH`
- pr_check Step 10 portfolio_refresh 顯示 completed 且 valuation API 回 200
- evidence_leak_check 必須 pass

---

# Sprint 1-4.3 驗收：Positions 寫回（帳務層完成）

**目標**：從 `trades` 表重算並寫入 `positions` 表，只做帳務（qty/avg_cost/realized_pnl），不做估值/匯率。

**驗收命令**（可證偽）：

### 1. 測試套件通過

```bash
# 所有測試（無警告）
docker compose exec -T portfolio-service pytest -q
# 期望：93 passed, 1 skipped, <2s

# rebuild 相關測試
docker compose exec -T portfolio-service pytest -q -k rebuild
# 期望：16+ passed（寫入、冪等性、零持倉刪除）
```

### 2. API 回傳欄位驗證

```bash
# 呼叫 rebuild_positions（query 參數）
curl -s -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq

# 預期輸出：
# {
#   "status": "succeeded",
#   "user_id": "tony",
#   "symbols_count": <int>,
#   "upserted_count": <int>,
#   "deleted_or_zeroed_count": <int>,
#   "run_id": "<uuid>",
#   "evidence": {
#     "positions_columns": [
#       "user_id", "symbol", "asset_ccy", "quantity",
#       "avg_cost", "realized_pnl", "u_pnl", "last_updated_at"
#     ]
#   }
# }

# 驗證點：
# - run_id 為 UUID 格式
# - symbols_count >= 0
# - evidence.positions_columns 包含 8 個欄位
```

### 3. 資料庫寫入驗證（psql）

```bash
# 查看 positions 表結構
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "\d positions"

# 預期欄位：
# - quantity (numeric)
# - avg_cost (numeric)
# - realized_pnl (numeric)
# - u_pnl (numeric) ← 當前固定 0

# 查看實際資料
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "SELECT user_id, symbol, quantity, ROUND(avg_cost::numeric, 2) as avg_cost \
      FROM positions WHERE user_id='tony' ORDER BY symbol;"

# 驗證點：
# - u_pnl 固定為 0（不做估值）
# - quantity, avg_cost, realized_pnl 有真實數值
```

### 4. 禁止規則驗證（Guardrails）

```bash
# 帳務層禁止 FX 模組
grep -rn "from app.fx" services/portfolio-service/app/position_rebuilder.py
# 期望：（空）

# 帳務層禁止折算邏輯
grep -rn "fx\.convert\|fx\.get_rate\|target_ccy" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py
# 期望：（空）

# 估值層禁止 DB 直連
docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
# 期望：5 passed
```

**可證偽檢查清單**（Sprint 1-4.3 階段）：

- ✅ `rebuild_positions` 回傳包含 `run_id`, `symbols_count`, `evidence`
- ✅ positions 表有 `u_pnl` 欄位（但值固定為 0）
- ✅ 連續執行兩次 rebuild，結果一致（冪等性）
- ✅ 賣光持倉後，positions 表自動刪除該筆記錄
- ❌ positions 表**無**估值欄位（`valuation_ccy`, `market_value`, `market_price`）
- ❌ portfolio-service 不呼叫 FX 模組（grep 無匹配）
- ❌ valuation-service 不直連 DB（pytest guardrails 通過）

**Troubleshooting**（當寫入數量/金額不符時）：

1. **檢查 trades 來源**：
   ```sql
   SELECT user_id, symbol, asset_ccy, COUNT(*), SUM(quantity)
   FROM trades WHERE user_id='<user_id>' GROUP BY 1,2,3;
   ```

2. **檢查分組與排序**：
   ```bash
   grep -A 5 "group_by\|order_by" services/portfolio-service/app/position_rebuilder.py
   # 必須按 (user_id, symbol, asset_ccy) 分組，trade_date ASC 排序
   ```

3. **檢查 UPSERT 衝突鍵**：
   ```sql
   SELECT conname, pg_get_constraintdef(oid)
   FROM pg_constraint
   WHERE conrelid = 'positions'::regclass AND contype = 'u';
   -- 預期：(user_id, symbol, asset_ccy) 唯一索引
   ```

4. **驗證冪等性**（連續執行兩次）：
   ```bash
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   # 兩次結果應相同
   ```

---

**檢查範例**（Sprint 1-4.3 驗收）：

```bash
# 確認 Position 表無估值欄位
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions'    AND column_name ~ '(valuation|market_value)';"
# 期望輸出：(0 rows)

# 確認 u_pnl 欄位存在（帳務層固定填 0）
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions' AND column_name='u_pnl';"
# 期望輸出：'0'::numeric
```

#### 規則 4：帳務層不做折算（最陰險的發散來源）

**目的**：防止帳務邏輯（positions / avg cost / realized pnl）偷偷做匯率折算，確保架構邊界清晰。

**檢查命令**：

```bash
# 檢查帳務層模組是否呼叫 FX API
grep -rn "fx\.convert\|fx\.get_rate" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py \
  services/portfolio-service/app/repositories/trades_repository.py

# 期望輸出：（空，無任何匹配）
```

**禁止清單**：
- ❌ `app/position_rebuilder.py`、`avg_cost_calculator.py`、`trades_repository.py` 等**帳務模組**禁止呼叫 `fx.convert()` 或 `fx.get_rate()`
- ❌ 帳務層禁止匯率折算邏輯（看起來只是乘個匯率，實際上會讓架構崩潰）
- ❌ `rebuild_positions`、`calculate_avg_cost` 等帳務 API 禁止接受 `target_ccy` 參數

**允許清單**：
- ✅ **僅估值層模組**（Sprint 1-4.B 之後的 `valuation_service.py`、`valuation_module.py`）可呼叫 FX API
- ✅ 估值層必須透過 `app.fx.get_fx_provider()` 取得 provider（唯一入口）
- ✅ 帳務層只負責記錄原始幣別（`asset_ccy`）和原始金額，不做任何折算

**違規後果**：
- 架構邊界模糊，未來擴充估值層時會發現匯率邏輯散落各處
- Debug 時無法確定「這個數字是原始金額還是折算後金額」
- 測試時無法隔離帳務邏輯與估值邏輯

#### Sprint 1-4.B 驗收：valuation-service 估值 API

**目的**：落實估值層 API（HTTP-only 取數），並提供可證偽 evidence。

**檢查命令**：

```bash
# 1. 啟動估值服務
docker compose up -d --build valuation-service portfolio-service

# 2. 健康檢查（含 runtime guard 狀態）
curl -s http://localhost:8005/health | jq
# 期望欄位：service_name, portfolio_base_url, providers, runtime_guard_status

# 3. 估值 API（成功案例）
curl -s "http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=USD&as_of=2026-01-24" | jq
# 期望：status=succeeded + evidence.positions_hash + items[].fx_rate_to_base

# 4. 估值 API（失敗案例：trades_count=0）
curl -s -i "http://localhost:8005/valuation/portfolio?user_id=empty_user" | sed -n '1,20p'
# 期望：HTTP 409 + detail.status=precondition_failed + evidence.trades_count=0

# 5. Guardrails 測試（禁止 DB driver / DB env）
docker compose exec -T valuation-service pytest -q
# 期望：全部通過
```

**成功輸出範例（節錄）**：
```json
{
  "status": "succeeded",
  "user_id": "tony",
  "base_ccy": "USD",
  "as_of": "2026-01-24",
  "items": [
    {
      "symbol": "AAPL",
      "asset_ccy": "USD",
      "price": 18.5,
      "fx_rate_to_base": 1.0,
      "market_value": 185.0,
      "unrealized_pnl":  -15.0
    }
  ],
  "evidence": {
    "positions_count": 1,
    "positions_hash": "<sha256>",
    "trades_count": 2,
    "distinct_symbols_count": 1,
    "verification_sql": {
      "trades_count": "select count(*) from trades where user_id='tony';",
      "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';"
    },
    "providers": {
      "price_provider": "stub",
      "fx_provider": "stub",
      "as_of": "2026-01-24"
    }
  }
}
```

**失敗輸出範例（節錄）**：
```json
{
  "detail": {
    "status": "precondition_failed",
    "user_id": "empty_user",
    "evidence": {
      "trades_count": 0,
      "distinct_symbols_count": 0
    }
  }
}
```

---

### 原理說明

**為何禁止在 host venv 執行測試？**

```
Smart-Investment-stretegy/         ← repo root
├── .venv/                          ← host venv（沒有安裝 service 依賴）
├── services/
│   ├── api-gateway/
│   │   ├── requirements.txt        ← fastapi, httpx
│   │   └── tests/
│   └── portfolio-service/
│       ├── requirements.txt        ← fastapi, sqlalchemy, pandas
│       └── tests/
│           ├── test_fx.py          ← 需要 app.fx 模組
│           └── test_rebuild_*.py   ← 需要 app.models
└── pytest.ini                      ← pytest 會掃描所有 services/*/tests/
```

執行流程對比：

| 執行方式 | pytest 收集範圍 | Python 環境 | 結果 |
|---------|---------------|-----------|------|
| `pytest -q -k fx` (host venv) | **所有 services** | host venv（缺少依賴） | ❌ ModuleNotFoundError |
| `docker compose exec portfolio-service pytest -q -k fx` | **只有 portfolio-service** | 容器內（完整依賴） | ✅ 20 passed |

---

## 8. 常用指令速查

```bash
# 查看所有服務日誌
make docker-logs

# 手動重新部署（VM 上）
sudo /opt/radar-warroom/infra/vm/deploy.sh

# 匯出 Postgres 備份
docker compose exec -T postgres pg_dump -U investment investment_db > backups/$(date +%F).sql

# 執行 portfolio-service 驗收腳本
bash services/portfolio-service/verify_sprint_1-3.sh

# 查看最近一次 sync 的可觀測性資料
docker compose exec portfolio-service python -c "
from app.db import get_db_session
from app.models import SyncRun
with get_db_session() as session:
    latest = session.query(SyncRun).order_by(SyncRun.started_at.desc()).first()
    if latest:
        print(f'sheet_rows: {latest.sheet_rows_count}, valid: {latest.normalized_valid_count}, invalid: {latest.normalized_invalid_count}, duplicates: {latest.duplicates_count}')
"
```

## 9. Portfolio Service 可觀測性欄位參考（v0.2.3+）

| 欄位 | 說明 | 正常範圍 | 異常判斷 |
| --- | --- | --- | --- |
| `sheet_rows_count` | Google Sheets 總列數 | > 0 | = 0 代表連線失敗或空表 |
| `normalized_valid_count` | 成功轉換的筆數 | = inserted + duplicates | < sheet_rows 代表有格式錯誤 |
| `normalized_invalid_count` | 格式錯誤筆數 | = 0 | > 0 時檢查日誌找出錯誤行 |
| `duplicates_count` | 重複跳過筆數（hash 去重） | ≥ 0 | 若 = sheet_rows 代表全為舊資料 |
| `inserted_count` | 新插入筆數 | ≥ 0 | = 0 時檢查是否 Sheets 未更新 |

### Hash 版本控制機制（CANONICAL_VERSION="v1"）

- `source_hash` 由 `v1:<SHA-256>` 組成，用於去重
- 若未來欄位標準化規則改變（例如台股代號補零規則），需升級為 `v2`
- 不同版本的 hash 不會衝突，可安全共存於同一資料表
- **操作建議**：若需要重新計算所有交易的 hash，應在低峰時段進行批次更新

---

## Google Service Account 金鑰部署（docker compose secrets）

### 1. 問題症狀
- portfolio_refresh sync 500，常見錯誤：
  - `Is a directory: '/run/secrets/google_sa.json'`
- 需提供 `GOOGLE_SA_JSON_PATH`（推薦）或 `GOOGLE_SA_JSON`（已棄用）

### 2. 根因說明
- 若部署時直接用 `docker compose` 而未併入 `docker-compose.secrets.yml`，容器 runtime 會缺少 `GOOGLE_SA_JSON_PATH` 與金鑰檔案掛載，導致 sync 失敗。
- pr_check 可能只走 409 fallback，未驗出金鑰缺失，導致假過。

### 3. 標準解法
- 新增 repo root `dc.sh`，統一作為 compose 入口：
  ```sh
  docker compose -f docker-compose.yml -f docker-compose.secrets.yml --env-file .env "$@"
  ```
- `tools/pr_check.sh` 內所有 `docker compose ...` 指令一律改呼叫 `./dc.sh ...`（config/ps/exec/run 全部）

### 4. secrets mount 規範
- 金鑰檔案掛載到容器 `/run/keys/google_sa.json:ro`
- portfolio-service env 使用 `GOOGLE_SA_JSON_PATH=/run/keys/google_sa.json`
- 不使用 `/run/secrets`（避免 mount 變成 directory）

### 5. 驗收準則
- pr_check Step 5 env keys 必須出現 `GOOGLE_SA_JSON_PATH`
- pr_check Step 10 portfolio_refresh 顯示 completed 且 valuation API 回 200
- evidence_leak_check 必須 pass

---

# Sprint 1-4.3 驗收：Positions 寫回（帳務層完成）

**目標**：從 `trades` 表重算並寫入 `positions` 表，只做帳務（qty/avg_cost/realized_pnl），不做估值/匯率。

**驗收命令**（可證偽）：

### 1. 測試套件通過

```bash
# 所有測試（無警告）
docker compose exec -T portfolio-service pytest -q
# 期望：93 passed, 1 skipped, <2s

# rebuild 相關測試
docker compose exec -T portfolio-service pytest -q -k rebuild
# 期望：16+ passed（寫入、冪等性、零持倉刪除）
```

### 2. API 回傳欄位驗證

```bash
# 呼叫 rebuild_positions（query 參數）
curl -s -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq

# 預期輸出：
# {
#   "status": "succeeded",
#   "user_id": "tony",
#   "symbols_count": <int>,
#   "upserted_count": <int>,
#   "deleted_or_zeroed_count": <int>,
#   "run_id": "<uuid>",
#   "evidence": {
#     "positions_columns": [
#       "user_id", "symbol", "asset_ccy", "quantity",
#       "avg_cost", "realized_pnl", "u_pnl", "last_updated_at"
#     ]
#   }
# }

# 驗證點：
# - run_id 為 UUID 格式
# - symbols_count >= 0
# - evidence.positions_columns 包含 8 個欄位
```

### 3. 資料庫寫入驗證（psql）

```bash
# 查看 positions 表結構
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "\d positions"

# 預期欄位：
# - quantity (numeric)
# - avg_cost (numeric)
# - realized_pnl (numeric)
# - u_pnl (numeric) ← 當前固定 0

# 查看實際資料
docker compose exec -T postgres psql -U portfolio_user -d portfolio_db \
  -c "SELECT user_id, symbol, quantity, ROUND(avg_cost::numeric, 2) as avg_cost \
      FROM positions WHERE user_id='tony' ORDER BY symbol;"

# 驗證點：
# - u_pnl 固定為 0（不做估值）
# - quantity, avg_cost, realized_pnl 有真實數值
```

### 4. 禁止規則驗證（Guardrails）

```bash
# 帳務層禁止 FX 模組
grep -rn "from app.fx" services/portfolio-service/app/position_rebuilder.py
# 期望：（空）

# 帳務層禁止折算邏輯
grep -rn "fx\.convert\|fx\.get_rate\|target_ccy" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py
# 期望：（空）

# 估值層禁止 DB 直連
docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
# 期望：5 passed
```

**可證偽檢查清單**（Sprint 1-4.3 階段）：

- ✅ `rebuild_positions` 回傳包含 `run_id`, `symbols_count`, `evidence`
- ✅ positions 表有 `u_pnl` 欄位（但值固定為 0）
- ✅ 連續執行兩次 rebuild，結果一致（冪等性）
- ✅ 賣光持倉後，positions 表自動刪除該筆記錄
- ❌ positions 表**無**估值欄位（`valuation_ccy`, `market_value`, `market_price`）
- ❌ portfolio-service 不呼叫 FX 模組（grep 無匹配）
- ❌ valuation-service 不直連 DB（pytest guardrails 通過）

**Troubleshooting**（當寫入數量/金額不符時）：

1. **檢查 trades 來源**：
   ```sql
   SELECT user_id, symbol, asset_ccy, COUNT(*), SUM(quantity)
   FROM trades WHERE user_id='<user_id>' GROUP BY 1,2,3;
   ```

2. **檢查分組與排序**：
   ```bash
   grep -A 5 "group_by\|order_by" services/portfolio-service/app/position_rebuilder.py
   # 必須按 (user_id, symbol, asset_ccy) 分組，trade_date ASC 排序
   ```

3. **檢查 UPSERT 衝突鍵**：
   ```sql
   SELECT conname, pg_get_constraintdef(oid)
   FROM pg_constraint
   WHERE conrelid = 'positions'::regclass AND contype = 'u';
   -- 預期：(user_id, symbol, asset_ccy) 唯一索引
   ```

4. **驗證冪等性**（連續執行兩次）：
   ```bash
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   curl -X POST 'http://localhost:8001/portfolio/rebuild_positions?user_id=tony' | jq .symbols_count
   # 兩次結果應相同
   ```

---

**檢查範例**（Sprint 1-4.3 驗收）：

```bash
# 確認 Position 表無估值欄位
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions'    AND column_name ~ '(valuation|market_value)';"
# 期望輸出：(0 rows)

# 確認 u_pnl 欄位存在（帳務層固定填 0）
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_name FROM information_schema.columns    WHERE table_name='positions' AND column_name='u_pnl';"
# 期望輸出：'0'::numeric
```

#### 規則 4：帳務層不做折算（最陰險的發散來源）

**目的**：防止帳務邏輯（positions / avg cost / realized pnl）偷偷做匯率折算，確保架構邊界清晰。

**檢查命令**：

```bash
# 檢查帳務層模組是否呼叫 FX API
grep -rn "fx\.convert\|fx\.get_rate" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/domain/avg_cost_calculator.py \
  services/portfolio-service/app/repositories/trades_repository.py

# 期望輸出：（空，無任何匹配）
```

**禁止清單**：
- ❌ `app/position_rebuilder.py`、`avg_cost_calculator.py`、`trades_repository.py` 等**帳務模組**禁止呼叫 `fx.convert()` 或 `fx.get_rate()`
- ❌ 帳務層禁止匯率折算邏輯（看起來只是乘個匯率，實際上會讓架構崩潰）
- ❌ `rebuild_positions`、`calculate_avg_cost` 等帳務 API 禁止接受 `target_ccy` 參數

**允許清單**：
- ✅ **僅估值層模組**（Sprint 1-4.B 之後的 `valuation_service.py`、`valuation_module.py`）可呼叫 FX API
- ✅ 估值層必須透過 `app.fx.get_fx_provider()` 取得 provider（唯一入口）
- ✅ 帳務層只負責記錄原始幣別（`asset_ccy`）和原始金額，不做任何折算

**違規後果**：
- 架構邊界模糊，未來擴充估值層時會發現匯率邏輯散落各處
- Debug 時無法確定「這個數字是原始金額還是折算後金額」
- 測試時無法隔離帳務邏輯與估值邏輯

#### Sprint 1-4.B 驗收：valuation-service 估值 API

**目的**：落實估值層 API（HTTP-only 取數），並提供可證偽 evidence。

**檢查命令**：

```bash
# 1. 啟動估值服務
docker compose up -d --build valuation-service portfolio-service

# 2. 健康檢查（含 runtime guard 狀態）
curl -s http://localhost:8005/health | jq
# 期望欄位：service_name, portfolio_base_url, providers, runtime_guard_status

# 3. 估值 API（成功案例）
curl -s "http://localhost:8005/valuation/portfolio?user_id=tony&base_ccy=USD&as_of=2026-01-24" | jq
# 期望：status=succeeded + evidence.positions_hash + items[].fx_rate_to_base

# 4. 估值 API（失敗案例：trades_count=0）
curl -s -i "http://localhost:8005/valuation/portfolio?user_id=empty_user" | sed -n '1,20p'
# 期望：HTTP 409 + detail.status=precondition_failed + evidence.trades_count=0

# 5. Guardrails 測試（禁止 DB driver / DB env）
docker compose exec -T valuation-service pytest -q
# 期望：全部通過
```

**成功輸出範例（節錄）**：
```json
{
  "status": "succeeded",
  "user_id": "tony",
  "base_ccy": "USD",
  "as_of": "2026-01-24",
  "items": [
    {
      "symbol": "AAPL",
      "asset_ccy": "USD",
      "price": 18.5,
      "fx_rate_to_base": 1.0,
      "market_value": 185.0,
      "unrealized_pnl":  -15.0
    }
  ],
  "evidence": {
    "positions_count": 1,
    "positions_hash": "<sha256>",
    "trades_count": 2,
    "distinct_symbols_count": 1,
    "verification_sql": {
      "trades_count": "select count(*) from trades where user_id='tony';",
      "distinct_symbols": "select count(distinct symbol) from trades where user_id='tony';"
    },
    "providers": {
      "price_provider": "stub",
      "fx_provider": "stub",
      "as_of": "2026-01-24"
    }
  }
}
```

**失敗輸出範例（節錄）**：
```json
{
  "detail": {
    "status": "precondition_failed",
    "user_id": "empty_user",
    "evidence": {
      "trades_count": 0,
      "distinct_symbols_count": 0
    }
  }
}
```

---

### 原理說明

**為何禁止在 host venv 執行測試？**

```
Smart-Investment-stretegy/         ← repo root
├── .venv/                          ← host venv（沒有安裝 service 依賴）
├── services/
│   ├── api-gateway/
│   │   ├── requirements.txt        ← fastapi, httpx
│   │   └── tests/
│   └── portfolio-service/
│       ├── requirements.txt        ← fastapi, sqlalchemy, pandas
│       └── tests/
│           ├── test_fx.py          ← 需要 app.fx 模組
│           └── test_rebuild_*.py   ← 需要 app.models
└── pytest.ini                      ← pytest 會掃描所有 services/*/tests/
```

執行流程對比：

| 執行方式 | pytest 收集範圍 | Python 環境 | 結果 |
|---------|---------------|-----------|------|
| `pytest -q -k fx` (host venv) | **所有 services** | host venv（缺少依賴） | ❌ ModuleNotFoundError |
| `docker compose exec portfolio-service pytest -q -k fx` | **只有 portfolio-service** | 容器內（完整依賴） | ✅ 20 passed |

---

## 8. 常用指令速查

```bash
# 查看所有服務日誌
make docker-logs

# 手動重新部署（VM 上）
sudo /opt/radar-warroom/infra/vm/deploy.sh

# 匯出 Postgres 備份
docker compose exec -T postgres pg_dump -U investment investment_db > backups/$(date +%F).sql

# 執行 portfolio-service 驗收腳本
bash services/portfolio-service/verify_sprint_1-3.sh
