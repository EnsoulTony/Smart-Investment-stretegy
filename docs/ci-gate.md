# CI Gate 說明文件

本文件說明 CI Gate 的設計目的、運作方式、本地測試流程，以及常見問題排除。

## 1. CI Gate 在做什麼（Why）

CI Gate 是本專案的自動化品質關卡，確保每個 PR 在合併前都經過完整驗證：

**核心目標：**
- **可證偽**：所有檢查都有明確的 PASS/FAIL 標準
- **可追溯**：每次 CI 執行都產生 artifacts（logs），方便事後追查
- **可回滾**：PR 需填寫回滾方式，確保出問題能快速復原

**執行的檢查項目（Full Mode）：**
1. **靜態程式碼檢查** - 掃描 forbidden tokens、secrets leak
2. **Docker Compose 建置** - 確保容器能正常建置啟動
3. **verify_sprint_1-4-b.sh** - Sprint 驗收測試
4. **pytest (portfolio-service)** - 後端單元/整合測試
5. **pytest (valuation-service)** - 估值服務測試

## 2. CI Mode 規則（Light/Full）

CI 會根據 PR 變更的檔案自動判定執行模式：

### Full Mode（完整檢查）

觸發條件（符合任一即觸發）：

| 路徑模式 | 說明 |
|---------|------|
| `services/portfolio-service/**` | Portfolio 服務程式碼 |
| `services/valuation-service/**` | Valuation 服務程式碼 |
| `services/api-gateway/**` | API Gateway 程式碼 |
| `tools/**` | 工具腳本 |
| `dc.sh` | Docker Compose wrapper |
| `docker-compose*.yml` | Compose 設定檔 |
| `compose*.yml` | Compose 設定檔 |
| `**/Dockerfile*` | Dockerfile |

**Full Mode 執行項目：**
- Static checks (forbidden tokens, secrets leak)
- Docker Compose build & up
- Health check 等待
- verify_sprint_1-4-b.sh
- pytest (portfolio-service)
- pytest (valuation-service)

### Light Mode（輕量檢查）

觸發條件：
- **僅**變更 `docs/**` 或 `*.md` 檔案
- 不含 `tools/` 目錄下的任何檔案

**Light Mode 執行項目：**
- Static checks only (不啟容器)

### 保守策略

若檔案不符合上述任一模式，CI 會採用 **Full Mode**（保守策略），確保不會遺漏任何可能影響系統的變更。

## 3. 本地如何跑 Full 驗收

在提交 PR 前，建議在本地執行完整驗收：

```bash
# 1. 確保環境乾淨
./dc.sh down -v

# 2. 建置並啟動服務
./dc.sh up -d --build

# 3. 等待 Postgres 就緒
./dc.sh exec -T postgres sh -c 'until pg_isready -U investment; do sleep 1; done'

# 4. 執行資料庫 migration
./dc.sh exec -T portfolio-service alembic upgrade head

# 5. 等待 HTTP 服務就緒
timeout 60 bash -c 'until curl -sf http://localhost:8001/health > /dev/null; do sleep 2; done'
timeout 60 bash -c 'until curl -sf http://localhost:8005/health > /dev/null; do sleep 2; done'

# 6. 執行 pr_check.sh
./tools/pr_check.sh

# 7. 執行 Sprint 驗收
./tools/verify_sprint_1-4-b.sh

# 8. 執行 pytest
./dc.sh exec -T portfolio-service pytest -q
./dc.sh exec -T valuation-service pytest -q

# 9. 清理（可選）
./dc.sh down -v
```

### 一鍵驗收腳本

也可以直接執行：

```bash
./tools/verify_sprint_1-4-b.sh
```

此腳本會自動啟動服務並執行完整驗收。

## 4. 常見失敗原因與排除

### 4.1 Docker Compose 起不來

**症狀：**
```
Error response from daemon: Conflict. The container name "xxx" is already in use
```

**解法：**
```bash
./dc.sh down -v
docker system prune -f  # 清理未使用的資源
./dc.sh up -d --build
```

### 4.2 Health Check 超時

**症狀：**
```
timeout: the monitored command dumped core
```

**排查步驟：**
```bash
# 查看容器狀態
./dc.sh ps

# 查看容器 logs
./dc.sh logs portfolio-service
./dc.sh logs valuation-service
./dc.sh logs postgres

# 檢查 port 是否被佔用
lsof -i :8001
lsof -i :8005
lsof -i :5432
```

### 4.3 Database Migration 失敗

**症狀：**
```
alembic.util.exc.CommandError: Can't locate revision identified by 'xxx'
```

**解法：**
```bash
# 重建資料庫
./dc.sh down -v
./dc.sh up -d postgres
./dc.sh exec -T postgres sh -c 'until pg_isready -U investment; do sleep 1; done'
./dc.sh up -d portfolio-service
./dc.sh exec -T portfolio-service alembic upgrade head
```

### 4.4 Port 被佔用

**症狀：**
```
Bind for 0.0.0.0:8001 failed: port is already allocated
```

**解法：**
```bash
# 找出佔用 port 的程序
lsof -i :8001
# 或
netstat -tulpn | grep 8001

# 終止該程序或更換 port
kill <PID>
```

### 4.5 PR Checkbox 檢查失敗

**症狀：**
```
CI GATE FAILED: Missing Required Checkboxes
```

**解法：**
1. 確認已在本地執行所有驗收
2. 更新 PR description，將所有 `- [ ]` 改為 `- [x]`
3. 重新 push 或編輯 PR 觸發 CI

### 4.6 Forbidden Token 掃描失敗

**症狀：**
```
decision=fail rule_id=VAL-FT-1
evidence=services/valuation-service/app/xxx.py:10:sqlalchemy
```

**說明：**
valuation-service 不允許直接存取資料庫。請確保：
- 不引用 sqlalchemy、psycopg2 等 DB 相關套件
- 不使用 DATABASE_URL 等環境變數
- 透過 portfolio-service API 取得資料

## 5. 如何取得 Logs

### GitHub Actions Artifacts

每次 CI 執行後會上傳以下 artifacts：
- `verify_sprint_1-4-b.log` - Sprint 驗收完整輸出
- `pytest_portfolio.log` - portfolio-service pytest 輸出
- `pytest_valuation.log` - valuation-service pytest 輸出
- `compose_logs_tail.log` - Docker Compose 容器 logs（最後 2000 行）
- `ci_mode_light.log` - Light mode 時的說明（如適用）

下載方式：
1. 進入 PR 的 Checks 頁面
2. 點擊 "CI Gate" workflow
3. 在 Summary 頁面下方找到 "Artifacts"
4. 下載 `ci-gate-artifacts`

### 本地 Logs

```bash
# 即時查看所有服務 logs
./dc.sh logs -f

# 查看特定服務
./dc.sh logs -f portfolio-service
./dc.sh logs -f valuation-service
./dc.sh logs -f postgres

# 只看最後 100 行
./dc.sh logs --tail 100 portfolio-service
```

## 6. Branch Protection 設定

為確保 PR 必須通過 CI Gate 才能合併，需設定 Branch Protection：

1. 進入 GitHub Repository Settings
2. 選擇 Branches → Add branch protection rule
3. Branch name pattern: `main`
4. 勾選 "Require status checks to pass before merging"
5. 搜尋並選擇 `CI Gate` 作為 required status check
6. 儲存規則

## 7. 安全注意事項

CI Gate 包含以下安全措施：

1. **Secrets 不會被印出**
   - 所有 env values 都會被 mask
   - Logs 不包含 GOOGLE_SA_JSON、DATABASE_URL 等敏感值

2. **Compose config 檢查**
   - 掃描是否有 `GOOGLE_SA_JSON:` 直接設定（應使用 `GOOGLE_SA_JSON_PATH`）
   - 掃描是否有 `BEGIN PRIVATE KEY` 洩漏

3. **Artifacts 安全**
   - Container logs 限制在 2000 行內
   - 不包含敏感檔案內容

## 8. 常見問題 FAQ

**Q: 為什麼我的 docs-only PR 還是跑 full mode？**

A: 檢查是否有變更到 `tools/` 目錄下的檔案。即使是 `.md` 檔案，若在 `tools/` 下也會觸發 full mode。

**Q: 如何跳過 CI？**

A: 本專案不支援跳過 CI。所有 PR 都必須通過 CI Gate。

**Q: CI 跑很慢怎麼辦？**

A: Full mode 需要建置 Docker images 和執行測試，預期需要數分鐘。如果只變更文件，確保只修改 `docs/` 或 `*.md` 以觸發 light mode。

**Q: 本地通過但 CI 失敗？**

A: 可能原因：
- 本地有 cached images，CI 是全新建置
- 本地有 `.env` 或 secrets 檔案，CI 沒有
- 時序問題（race condition）

建議：
```bash
# 模擬 CI 環境
./dc.sh down -v
docker system prune -f
./dc.sh up -d --build
# 然後執行完整驗收
```
