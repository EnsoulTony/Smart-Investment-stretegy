好，1 + 2 = BOTH。
下面我直接給你 兩份「可直接 commit」的 RUNBOOK 附錄，等級是「交接即用、出事可救援」，不是說明文。

你可以選擇：
	•	🔹 分別存成兩個檔案（推薦，乾淨）
	•	🔹 或附加在既有 RUNBOOK.md 後面

我會用 「附錄」格式，方便你整合。

⸻

📎 RUNBOOK-DOCTOR.md

系統環境自我診斷（One-Command Doctor）

目的：
用 30 秒判斷 Claude Code + Repo + 環境是否可用
新 Codespace、換電腦、換人接手時必跑。

⸻

使用方式（標準）

在 repo 根目錄執行：

make doctor

或（尚未做 Makefile 前）手動執行下列檢查。

⸻

檢查項目一覽

1️⃣ Repo 與工作目錄

pwd
git status --porcelain

預期：
	•	在 /workspaces/<repo>
	•	工作目錄乾淨（或你知道自己在改什麼）

⸻

2️⃣ Node / nvm / claude CLI

node -v
npm -v
which -a claude
claude --version

預期：
	•	Node / npm 有版本
	•	claude 位於 nvm 路徑
	•	Claude Code 版本顯示

⸻

3️⃣ API Key 存在（不顯示內容）

test -n "$ANTHROPIC_API_KEY" && echo "ANTHROPIC_API_KEY OK" || echo "ANTHROPIC_API_KEY MISSING"

❌ 若 missing → 禁止使用 Claude Code

⸻

4️⃣ Python / 測試工具

python --version
pytest --version

預期：
	•	Python 可用
	•	pytest 可用

⸻

5️⃣ Repo 關鍵檔案存在

test -d prompts && echo "prompts/ OK" || echo "prompts/ missing"
test -f RUNBOOK.md && echo "RUNBOOK OK" || echo "RUNBOOK missing"


⸻

建議：加入 Makefile（可選但強烈推薦）

Makefile

doctor:
	@echo "== Repo =="
	pwd
	git status --porcelain || true
	@echo ""

	@echo "== Node / Claude =="
	node -v
	npm -v
	which -a claude || true
	claude --version || true
	@echo ""

	@echo "== API Key =="
	test -n "$$ANTHROPIC_API_KEY" && echo "ANTHROPIC_API_KEY OK" || echo "ANTHROPIC_API_KEY MISSING"
	@echo ""

	@echo "== Python / Tests =="
	python --version
	pytest --version || true


⸻

什麼時候一定要跑 doctor
	•	新開 Codespace
	•	Claude 行為異常
	•	CI / test 突然壞
	•	交接給別人前

⸻

建議 Commit Message

docs: add RUNBOOK doctor for environment verification


⸻

