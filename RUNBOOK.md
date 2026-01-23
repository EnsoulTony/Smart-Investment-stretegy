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

