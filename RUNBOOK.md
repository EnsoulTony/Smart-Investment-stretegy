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

