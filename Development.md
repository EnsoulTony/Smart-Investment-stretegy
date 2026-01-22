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