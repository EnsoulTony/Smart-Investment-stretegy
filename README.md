# Smart-Investment-Strategy｜Radar 戰情室 MVP

以微服務為核心的智慧投資戰情室骨架，支援 Vue（Vite）前端、FastAPI 後端、Postgres 資料庫與 Docker Compose 一鍵啟動。此專案目標為：自動同步持倉與交易 → 套用 Radar v1.4 分析曝險與趨勢 → 整合新聞與研究報告 → 保存每次建議與策略紀錄，並以 RWD 戰情室介面呈現。

---

## MVP 範圍

### In Scope（MVP 必含）
- ✅ 簡易登入（JWT，MVP 先不做 OAuth）
- ✅ 持倉/交易同步：啟動時讀取 Google Sheets（持倉表單 + 流水帳交易紀錄）
- ✅ 資料落庫（Postgres）：
	- 交易紀錄 `trades`
	- 持倉快照 `positions`
	- 指標值 `indicator_values`（例如 `RS_XLU_XLK`）
	- 新聞訊號 `news_signals`
	- 研究訊號 `research_signals`
	- 每次分析與建議紀錄 `analysis_runs` / `recommendations`
- ✅ 均價法盈虧計算（依交易流水帳推導平均成本）
- ✅ Radar v1.4 策略引擎（可抽換）：
	- 策略邏輯封裝於 Strategy Engine + 插件
	- 趨勢過熱 + 回撤 >10% + 核心持股仍盈利 → 獲利減碼 30%
	- 趨勢反轉 → 獲利減碼 70%
- ✅ `RS_XLU_XLK` 指標（日線）作為市場風格/風險偏好參考
- ✅ 新聞（N1 + N3）：GDELT + RSS 白名單，輸出中文解讀並標註重要性
- ✅ 研究報告：
	- 國泰研究報告頁面自動抓取（每日/週報 PDF）→ 文字抽取 → 本地摘要（中文）
	- 券商研究手動匯入（國泰證券 + 凱基證券）
- ✅ 戰情室 UI（RWD）：
	- 持倉比例/分類/曝險
	- 今日訊號（新聞/研究）
	- 策略建議與歷史建議對照
- ✅ VM 部署（D1）：
	- Ubuntu VM + Docker Compose
	- GitHub Actions（push → SSH → VM 自動更新部署）
	- systemd timer 保底（每 15 分鐘檢查更新）

### Out of Scope（MVP 不做）
- ❌ 掃描型 PDF OCR（僅標記 `needs_ocr`，下一版再做）
- ❌ 研究報告全文公開轉載/對外分享（僅存連結、摘要與解讀，需遵守來源條款）
- ❌ 高頻/即時 tick 資料
- ❌ Kubernetes（MVP 以 VM + Docker Compose 為主）

---

## 系統組成

| 服務 | 說明 | 預設內部埠口 |
| --- | --- | --- |
| Frontend | Vite + Vue 戰情室介面雛型，含 Vitest | 4173（對外 8080） |
| api-gateway | FastAPI，統一前端入口、Auth、聚合資料 | 8000 |
| portfolio-service | FastAPI，交易/持倉/均價法/快照 | 8001 |
| radar-service | FastAPI，Strategy Engine + v1.4 Plugin（決策建議） | 8002 |
| news-service | FastAPI，新聞抓取/去重/中文摘要/重要性分數 | 8003 |
| research-service | FastAPI，研究報告抓取（PDF）/抽字/本地摘要/手動匯入 | 8004 |
| valuation-service | FastAPI，估值層（HTTP-only，禁止直連 DB） | 8005 |
| indicator-service | FastAPI，市場指標（XLU/XLK sector rotation） | 8006 |
| postgres | Postgres 16，持久化儲存 | 5432 |

更完整架構、資料契約與邊界請見 [ARCHITECTURE.md](ARCHITECTURE.md)、[API_CONTRACTS.md](API_CONTRACTS.md)、[Strategy.md](Strategy.md)。

---

## 目錄結構

```
.
├── docker-compose.yml
├── Makefile
├── .env.example
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── src/
│   │   ├── App.vue
│   │   ├── lib/health.js
│   │   └── main.js
│   └── tests/health.test.js
└── services/
		├── base-requirements.txt
		├── api-gateway/
		│   ├── Dockerfile
		│   ├── app/main.py
		│   └── tests/test_health.py
		└── …（portfolio、radar、news、research 結構相同）
```

---

## 環境需求
- Docker / Docker Compose
- Node.js 20（本機開發前端時使用）
- Python 3.12（如需在本機直接執行 FastAPI 測試）
- Claude 與 Aider：請閱讀 [RUNBOOK-AI-GUARDRAILS](RUNBOOK-AI-GUARDRAILS)，遵守協作守則（列出修改檔案、保持最小差異、務必附測試）

---

## 快速開始（Codespaces / 本機）
1. 複製環境變數範本並視需求調整：
	 ```bash
	 cp .env.example .env
	 ```
2. 安裝前端依賴（開發模式需要）：
	 ```bash
	 make install-frontend
	 ```
3. 透過 Docker Compose 啟動所有服務：
	 ```bash
	 make docker-up
	 ```
4. 驗證健康檢查：
	 - 前端：http://localhost:8080
	 - API Gateway：http://localhost:8000/health
	 - 其他服務：8001～8004 皆有 `/health`

停止並清除資源：
```bash
make docker-down
```

---

## 常用 Makefile 指令

| 指令 | 功能 |
| --- | --- |
| `make install-frontend` | 於 `frontend/` 安裝 Node 依賴 |
| `make test-frontend` | 執行 Vitest |
| `make test-services` | 針對所有 Python 服務執行 pytest |
| `make docker-up` | `docker compose up -d --build` |
| `make docker-down` | `docker compose down -v` |
| `make docker-logs` | 追蹤所有容器日誌 |

---

## VM 部署（D1｜Ubuntu + Docker Compose）

MVP 採用 VM 部署並支援 GitHub push 自動更新：
- VM 初次安裝/啟動：`infra/vm/bootstrap.sh`
- 自動部署流水：
	- GitHub Actions：push 觸發 → SSH 到 VM → 執行 `infra/vm/deploy.sh`
	- systemd timer：每 15 分鐘保底檢查更新

詳細步驟請見 [DEPLOYMENT.md](DEPLOYMENT.md) 與 [RUNBOOK.md](RUNBOOK.md)。

---

## 健康檢查端點

每個 FastAPI 服務都提供 `/health`，回傳：

```json
{ "status": "ok", "service": "<name>" }
```

方便雲端部署或監控探活。

---

## 測試策略（MVP）
- 前端：Vitest（範例測試：`frontend/tests/health.test.js`）
- 後端：各服務 `tests/test_health.py` 驗證 `/health` 狀態碼與 JSON 結構
- CI/CD：可直接將 Makefile 指令串入 pipeline，詳見 `TESTING.md`

---

## 與 AI 協同開發（重要）
- 所有註解與文件以繁體中文撰寫
- 使用 Claude / Aider 時必須：
	- 先列出會修改的檔案
	- 保持最小差異，避免無意義大改
	- 每次變更需附對應測試並更新文件
- 詳細規範請見 [RUNBOOK-AI-GUARDRAILS](RUNBOOK-AI-GUARDRAILS)

---

## Sprints 開發進度

| Sprint | 狀態 | 說明 | 驗收腳本 |
| --- | --- | --- | --- |
| Sprint 1 | ✅ 完成 | Portfolio 均價法、rebuild idempotency、preview/write hash 一致、valuation-service（HTTP-only guardrails） | `tools/verify_sprint_1-4-b.sh` |
| Sprint 2 | ✅ 完成 | Strategy Engine（可插拔）+ v1.4 plugin（EDS）+ indicator-service（XLU/XLK） | `tools/verify_sprint_2.sh` |

> 📁 Sprint 規格文件統一放在 `docs/sprints/` 目錄。

### Sprint 2 新增功能

- **Strategy Engine**：可插拔架構，固定 Input/Output Schema（詳見 [docs/sprints/sprint-2.md](docs/sprints/sprint-2.md)）
- **v1.4 Plugin（EDS）**：計分制 mode 判定（RISK_ON/RISK_OFF/TRANSITION）、可證偽 triggers、5 日 cooldown
- **indicator-service**：XLU/XLK 指標服務（port 8006），提供 `GET /indicators/sector-rotation`
- **radar-service**：新增 `GET /radar/decision?user_id=tony&base_ccy=TWD` 決策端點

驗收指令：
```bash
./tools/verify_sprint_2.sh
```

---

## 工具腳本一覽（tools/）

- `./tools/verify_sprint_1-4-a.sh`：Sprint 1-4.A 完整驗收（FX + Guardrails + 全測試）
- `./tools/verify_sprint_1-4-b.sh`：Sprint 1-4.B 驗收（估值 API）
- `./tools/verify_sprint_2.sh`：Sprint 2 驗收（Strategy Engine + indicator-service）
- `./tools/test_preview.sh`：Sprint 1-4.2 preview 驗證（含 rebuild 測試）
- `./tools/test_sprint_1-3.sh`：Sprint 1-3 快速測試（sync endpoint）
- `./tools/test_api_gateway_proxy.sh`：api-gateway 反向代理測試
- `./tools/verify_portfolio_hardening.sh`：portfolio-service 加固驗收（hash/observability）
- `./tools/pr_check.sh`：PR 自動檢查（forbidden tokens / compose env / pytest）
- `./tools/portfolio_refresh.sh`：portfolio refresh 流程（同步 → rebuild）
- `./tools/debug_test.sh`：單測試 debug（sync_endpoint 單例 + TradeNormalizer）
- `./tools/quick_debug.sh`：快速檢查 TradeNormalizer
- `./tools/diagnose_and_fix_tests.sh`：檢查測試版本與重建流程
- `./tools/fix_pr_check.sh`：修補 `tools/pr_check.sh` 的 secrets guard 比較邏輯（僅在需要時執行）

---

## 重要文件
- [Strategy.md](Strategy.md)：Radar v1.4 規則、抽換邊界與指標定義
- [Development.md](Development.md)：分階段 prompts、開發流程、一鍵命令模板
- [ARCHITECTURE.md](ARCHITECTURE.md)：微服務邊界、資料流、部署拓樸
- [RUNBOOK.md](RUNBOOK.md)：維運、監控、回滾、日誌、備份
- [SECURITY.md](SECURITY.md)：金鑰與安全控管原則
- [API_CONTRACTS.md](API_CONTRACTS.md)：`news_signals` / `research_signals` / `analysis_runs` schema
- [TESTING.md](TESTING.md)：前後端測試策略與命令
- [DEPLOYMENT.md](DEPLOYMENT.md)：VM 部署與自動更新
- [CHANGELOG.md](CHANGELOG.md)：版本沿革與 MVP 里程碑
- [docs/sprints/sprint-2.md](docs/sprints/sprint-2.md)：Sprint 2 完整規格與實作紀錄
