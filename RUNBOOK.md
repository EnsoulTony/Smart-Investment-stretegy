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
GOOGLE_SA_JSON={"type":"service_account",...}

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
test -n "$GOOGLE_SA_JSON" && echo "GOOGLE_SA_JSON is set" || echo "Missing GOOGLE_SA_JSON"
test -n "$GOOGLE_SHEET_ID" && echo "GOOGLE_SHEET_ID is set" || echo "Missing GOOGLE_SHEET_ID"

# 驗證 JSON 格式是否正確
echo "$GOOGLE_SA_JSON" | python3 -m json.tool > /dev/null && echo "Valid JSON" || echo "Invalid JSON"
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
| **1-4.3** | 帳務重算（positions 表寫入，`unrealized_pnl=0`） | 估值計算、匯率折算、FX 模組呼叫 |
| **1-4.B** | 估值層實作（匯率來源、cache、valuation 欄位） | 估值邏輯散落到非 valuation_service.py |

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

# 確認 unrealized_pnl 預設值為 0
docker compose exec postgres psql -U investment -d investment_db -c   "SELECT column_default FROM information_schema.columns    WHERE table_name='positions' AND column_name='unrealized_pnl';"
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

#### Sprint 1-4.B 驗收：valuation-service 骨架

**目的**：建立估值層服務，嚴格遵守「API-only 取數邊界」。

**檢查命令**：

```bash
# 1. 啟動 valuation-service
docker compose up -d --build valuation-service

# 2. 健康檢查
curl -s http://localhost:8005/health | jq
# 期望：{"status": "healthy", "portfolio_base_url": "http://portfolio-service:8001"}

# 3. 確認環境變數
docker compose exec -T valuation-service python -c "import os; print(os.getenv('PORTFOLIO_BASE_URL'))"
# 期望：http://portfolio-service:8001

# 4. 驗證 Guardrails（禁止 DB driver）
docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
# 期望：4 passed（4 個禁止規則 + 1 個正向檢查）

# 5. 驗證 portfolio-service Guardrails（禁止估值邏輯）
docker compose exec -T portfolio-service pytest -q tests/test_guardrails_accounting_boundary.py
# 期望：4 passed（帳務層禁止 FX 呼叫、估值計算）
```

**架構鐵律**：
- ✅ valuation-service 只能透過 HTTP 從 portfolio-service 取數
- ❌ valuation-service 禁止任何 DB library（sqlalchemy/psycopg2）
- ✅ portfolio-service 只做帳務（avg_cost, realized_pnl），不做估值
- ❌ portfolio-service 禁止匯率折算（fx.convert/fx.get_rate）

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
好，下面這一份是可直接放進 repo、可直接 commit 的正式版 RUNBOOK.md（安裝與驗證篇）。
我用的是「工程交接等級」的寫法，不是教學文，重點是 可重現、可驗證、可排錯。

你可以整份複製，或拆段放進既有 RUNBOOK。

⸻

RUNBOOK.md

Claude Code CLI 安裝與驗證（Codespaces / VS Code / iPad 友善）

⸻

目的（Why）

本專案使用 Claude Code（Node.js CLI 版） 作為 AI 工程師，
用於在 repo 內協助：
	•	修改程式碼
	•	新增 / 調整測試
	•	依 prompt + guardrails 產生最小 diff
	•	輔助 commit（需人工確認）

⚠️ 注意：
本 RUNBOOK 僅涵蓋「Claude Code CLI（Node 版）」
不使用 Python pip 套件（避免同名套件混淆）。

⸻

適用環境（Scope）
	•	GitHub Codespaces（建議）
	•	VS Code（Desktop / Web）
	•	iPad（透過瀏覽器使用 Codespaces）
	•	Node.js 環境（nvm）

⸻

前置條件（Prerequisites）
	•	已建立 GitHub repo
	•	可開啟 Codespaces
	•	已申請 Anthropic API Key
	•	申請位置：https://console.anthropic.com
	•	API Key 已設為環境變數 ANTHROPIC_API_KEY

⸻

Step 1｜確認 Node.js 與 nvm

在 Codespaces Terminal 執行：

node -v
npm -v

預期：
	•	有顯示版本號
	•	若無，請先修復 Codespaces / Node 環境

⸻

Step 2｜全域安裝 Claude Code CLI（Node 版）

npm install -g @anthropic-ai/claude-code

說明
	•	這會透過 nvm 安裝 CLI
	•	可執行檔通常位於：
	•	/home/codespace/nvm/current/bin/claude
	•	或 /usr/local/share/nvm/versions/node/.../bin/claude

⸻

Step 3｜驗證 claude 指令是否可用

which -a claude
claude --version

預期結果
	•	which -a claude 至少顯示一個 nvm 路徑
	•	claude --version 顯示類似：

2.x.x (Claude Code)

✅ 若符合，即表示 CLI 安裝成功

⸻

Step 4｜設定並驗證 API Key（不顯示內容）

設定（範例）

export ANTHROPIC_API_KEY="sk-ant-xxxx"

⚠️ 請勿將 API Key commit 或貼入 Slack / Issue / PR

驗證（安全方式）

test -n "$ANTHROPIC_API_KEY" && echo "ANTHROPIC_API_KEY is set" || echo "ANTHROPIC_API_KEY missing"


⸻

Step 5｜（建議）永久化 API Key

避免重開 terminal 後消失：

nano ~/.bashrc

加入一行：

export ANTHROPIC_API_KEY="sk-ant-xxxx"

套用：

source ~/.bashrc


⸻

Step 6｜啟動 Claude Code（標準方式）

cd /workspaces/<your-repo>
claude

成功狀態
	•	進入 Claude Code 互動模式
	•	無 authentication / API key 錯誤

⸻

標準使用流程（Required Practice）

每一次使用 Claude Code 必須遵守：
	1.	一次只執行 一個 prompt
	2.	Prompt 必須包含：
	•	Task
	•	Files / Repo
	•	Guardrails
	•	Tests
	•	Commit message
	3.	要求 Claude：
	•	Before coding：列出會修改的檔案與行數範圍
	•	跑 pytest -q
	4.	人工確認 git diff
	5.	再允許 commit

⸻

常見錯誤與排查（Troubleshooting）

❌ claude: command not found
	•	原因：
	•	裝到 Python 套件（pip）而非 Node CLI
	•	PATH 未包含 nvm bin
	•	解法：
	•	移除 pip 套件：pip uninstall claude
	•	重新執行 Step 2

⸻

❌ API key missing / authentication error
	•	檢查：

test -n "$ANTHROPIC_API_KEY"

	•	確認 key 來自：
	•	https://console.anthropic.com
	•	不是 chat.claude.ai

⸻

安全規範（Security）
	•	❌ 不得 echo $ANTHROPIC_API_KEY
	•	❌ 不得將 key 寫入程式碼
	•	❌ 不得 commit .env 含 key
	•	若 key 外洩，立即：
	1.	到 Anthropic Console revoke
	2.	重新產生
	3.	更新環境變數

⸻

本 RUNBOOK 的定位
	•	本文件為 基礎設施等級文件
	•	修改需經 code review
	•	所有新成員 / 新 Codespace 必須依此驗證

⸻

最後確認清單（Checklist）
	•	claude --version 正常
	•	ANTHROPIC_API_KEY 已設
	•	可進入 Claude Code REPL
	•	已閱讀並理解使用規範

⸻

建議 Commit Message

docs: add RUNBOOK for Claude Code CLI installation and verification


⸻


## 估值層 API-only 鐵律

### 架構強制規則

**valuation-service（估值層）**：
- ❌ **禁止直連 Postgres 或任何 DB**：不得出現 `sqlalchemy`、`psycopg2`、`postgresql://` 連線字串
- ❌ **禁止 DATABASE_URL 環境變數**：只能使用 `PORTFOLIO_BASE_URL`（HTTP URL）
- ✅ **只能透過 HTTP API 取數**：使用 `PortfolioClient` 呼叫 `portfolio-service` 端點

**portfolio-service（帳務層）**：
- ❌ **禁止匯率折算**：不得呼叫 `fx.get_rate()` 或 `fx.convert()`
- ❌ **禁止估值計算**：不得計算 `market_value`、`market_price`、`unrealized_pnl`（除填 0）
- ❌ **禁止 target_ccy 參數**：帳務 API 不接受目標幣別參數
- ✅ **只做帳務**：`avg_cost`、`realized_pnl`、`quantity`、原始 `asset_ccy`

### 驗收指令（正確跑法）

**✅ 正確：在容器內跑單一 service 的測試**

```bash
# Portfolio Service 全量測試
docker compose exec -T portfolio-service pytest -q
# 期望：82 passed

# Portfolio Service FX 模組測試
docker compose exec -T portfolio-service pytest -q -k fx
# 期望：20 passed, 55 deselected

# Valuation Service 全量測試
docker compose exec -T valuation-service pytest -q
# 期望：7 passed
```

**❌ 禁止：在 host venv 直接 pytest**

```bash
# 會跨服務收集測試，造成假失敗
pytest -q           # ❌ 錯誤
pytest -q -k fx     # ❌ 錯誤
```

**原因**：host venv 的 pytest 會掃描整個 repo，收集到其他 service 的測試（例如 valuation-service 的測試需要 httpx，但 portfolio-service venv 沒有），導致 import 錯誤或測試失敗。

### 最小健康檢查

```bash
# Portfolio Service
curl -s http://localhost:8001/health | jq
# 期望：{"status": "healthy", "service": "portfolio-service"}

# Valuation Service (port 依 docker-compose.yml 設定)
curl -s http://localhost:8005/health | jq
# 期望：{"status": "healthy", "service": "valuation-service"}
```

### Guardrails 測試驗收

**估值層禁止 DB 直連**（5 個測試）：

```bash
docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
# 期望：5 passed
# - test_requirements_no_db_drivers（禁止 requirements.txt 包含 DB driver）
# - test_codebase_no_db_connection_strings（禁止 postgresql:// 連線字串）
# - test_codebase_no_sqlalchemy_usage（禁止使用 SQLAlchemy）
# - test_codebase_no_psycopg2_usage（禁止使用 psycopg2）
# - test_codebase_uses_http_client（正向檢查：使用 httpx）
```

**帳務層禁止估值邏輯**（4 個測試）：

```bash
docker compose exec -T portfolio-service pytest -q tests/test_guardrails_accounting_boundary.py
# 期望：4 passed
# - test_accounting_modules_no_fx_calls（帳務模組禁止呼叫 FX API）
# - test_accounting_modules_no_valuation_logic（帳務模組禁止計算估值）
# - test_accounting_api_no_target_ccy（帳務 API 禁止 target_ccy 參數）
# - test_position_model_accounting_only（Position 表只有帳務欄位）
```

---
