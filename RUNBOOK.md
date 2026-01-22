# RUNBOOK.md｜維運指南（MVP）

本文件提供 VM 上的維運人員、資料與策略工程師在遇到故障時的標準作業流程（SOP），包含日常檢查、異常排查、重啟/回滾、備份與 AI 協作注意事項。

## 1. 日常檢查清單

1. `docker ps --format 'table {{.Names}}\t{{.Status}}'`（所有容器須為 healthy）
2. `curl http://localhost:8000/health`（Gateway 探活）
3. `curl http://localhost:8001/health` ~ `8004/health`（抽樣）
4. `journalctl -u radar-deploy.timer -n 30`
5. `docker exec postgres pg_isready`
6. 檢查最新 `recommendations`、`news_signals` 是否更新（可透過 SQL 或 API）

## 2. 異常排查對照表

| 症狀 | 可能原因 | 處理步驟 |
| --- | --- | --- |
| 前端空白或 5xx | Gateway 掛掉 / JWT 失效 | `docker logs api-gateway` → `docker restart api-gateway` |
| Radar 無建議輸出 | 指標未更新 / 策略崩潰 | 1. `docker logs radar-service` 2. 確認 `indicator_values` 是否含最新 `RS_XLU_XLK` |
| 新聞/研究訊號缺漏 | GDELT/RSS 限制 | 重啟對應服務並檢查 API 金鑰 |
| Postgres 空間不足 | 快照過多 | `docker exec postgres du -sh /var/lib/postgresql/data` → 清理舊備份或擴容 |
| docker compose up 失敗 | `.env` 缺值或埠被占用 | 1. 驗證 `.env` 2. `docker compose config` 3. 釋放埠號 |

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
docker exec postgres pg_dump -U investment investment_db > backups/$(date +%F).sql
```
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

