# TESTING.md｜測試策略

本文件描述前端與後端最小測試需求、指令與 CI 建議。

## 1. 前端（Vue + Vitest）

- 測試框架：Vitest + jsdom。
- 主要檔案：`frontend/tests/health.test.js`（可持續擴充）。
- 指令：
  ```bash
  cd frontend
  npm run test
  ```
- 最低要求：
  - 健康檢查函式（`formatHealthStatus`）需涵蓋成功與失敗路徑。
  - UI 元件測試可透過 `@vue/test-utils`（未來擴充）。

## 2. 後端（FastAPI + pytest）

- 每個服務一份 `tests/test_health.py`。
- 指令：
  ```bash
  make test-services
  ```
- 新增業務邏輯時需：
  - 以 pytest + httpx TestClient 模擬 API。
  - 若涉及資料庫，可使用 `pytest fixtures` 建立暫時表。

## 3. 整體流程

| 階段 | 指令 | 說明 |
| --- | --- | --- |
| 開發前 | `make install-frontend` | 確保依賴完整 |
| 功能完成 | `make test-services && make test-frontend` | 本地驗證 |
| Docker 驗證 | `make docker-up` → `curl http://localhost:8000/health` | 確認容器啟動 |

### Sprint 驗收腳本（可回歸）

- Sprint 2：`./tools/verify_sprint_2.sh`
- Sprint 3：`./tools/verify_sprint_3.sh`（含 migrations、news signals contract、tier 分佈、triggers 必備、pytest）

## 4. CI 建議（未來擴充）

1. GitHub Actions Workflow：
   - Step 1：`npm ci` + `npm run test`。
   - Step 2：`pip install -r services/base-requirements.txt` + `make test-services`。
   - Step 3：`docker compose config` 驗證。
2. 若需要整合測試，可在 workflow 中啟動 docker compose，並以 pytest + requests 驗證 `/health`。

## 5. 測試資料

- 測試過程中請勿使用真實 API 金鑰。
- 若需 mock Google Sheets / GDELT，建議使用 JSON fixtures 放於 `tests/fixtures/`。

## 6. 成功判準

- 透過 `make test-services`、`make test-frontend` 皆須返回 0。
- 健康檢查端點在 Docker Compose 啟動後需回傳 `{ "status": "ok" }`。
- PR 需附上上述指令的執行結果或截圖。
