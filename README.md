# Smart-Investment-stretegy

以微服務為核心的智慧投資系統骨架，支援 Vue 前端、FastAPI 後端、Postgres 資料庫與 Docker Compose 一鍵啟動。此版本著重於乾淨的基礎設計與健康檢查，方便後續透過 Claude、Aider 或人工同步開發。

## 系統組成

| 服務 | 說明 | 預設內部埠口 |
| --- | --- | --- |
| Frontend | Vite + Vue 空殼，提供介面雛型與 Vitest 測試 | 4173 (對外 8080) |
| api-gateway / web-bff | FastAPI，統一前端進出入口 | 8000 |
| portfolio-service | FastAPI，負責投資組合資料 | 8001 |
| radar-service | FastAPI，未來專注技術指標計算 | 8002 |
| news-service | FastAPI，新聞與訊息彙整 | 8003 |
| research-service | FastAPI，研究報告與洞察 | 8004 |
| postgres | 官方 Postgres 16，持久化儲存 | 5432 |

## 目錄結構

```
.
├── docker-compose.yml
├── Makefile
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
	 └── … (portfolio, radar, news, research 結構相同)
```

## 環境需求

- Docker / Docker Compose
- Node.js 20 (本機開發前端時使用)
- Python 3.12 (如需在本機直接執行 FastAPI 測試)
- Claude 與 Aider：請閱讀 [RUNBOOK-AI-GUARDRAILS](RUNBOOK-AI-GUARDRAILS) 以遵守協作守則

## 快速開始

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
	- API：http://localhost:8000/health (其餘服務依序遞增)

若需停止並清除資源：
```bash
make docker-down
```

## 常用 Makefile 指令

| 指令 | 功能 |
| --- | --- |
| `make install-frontend` | 於 `frontend/` 安裝 Node 依賴 |
| `make test-frontend` | 執行 Vitest |
| `make test-services` | 針對所有 Python 服務執行 pytest |
| `make docker-up` | `docker compose up -d --build` |
| `make docker-down` | `docker compose down -v` |
| `make docker-logs` | 追蹤所有容器日誌 |

## 健康檢查端點

每個 FastAPI 服務都提供 `/health`，回傳 `{ "status": "ok", "service": "<name>" }`，方便雲端部署或監控探活。前端也提供簡單的狀態面板，可在未連線後端時顯示預設訊息。

## 測試策略

- **前端**：使用 Vitest，範例測試位於 `frontend/tests/health.test.js`
- **後端**：每個服務的 `tests/test_health.py` 皆會驗證 `/health` 狀態碼與 JSON 結構
- **CI/CD**：可直接將上述 Makefile 指令串入 pipeline

## 與 AI 協同開發

- 所有註解與手冊以中文撰寫，方便團隊協作
- 以 Claude、Aider 作為受約束的協作工程師，務必遵循 [RUNBOOK-AI-GUARDRAILS](RUNBOOK-AI-GUARDRAILS) 中的規範（列出修改檔案、保持最小差異、務必附測試等）
- 新增服務或功能時，請優先補齊健康檢查與測試確保骨架穩定

## 授權

詳見 [LICENSE](LICENSE)
