# CHANGELOG.md｜版本沿革

## [0.2.3] - 2026-01-23（Portfolio Service 可觀測性與 Hash 版本控制加固）
- **source_hash 版本控制**：避免未來 canonical 規則變動造成 hash 衝突
  - 在 trade_normalizer.py 加入 `CANONICAL_VERSION = "v1"` 常數
  - compute_source_hash() 改為包含版本前綴：`sha256(f"{version}|{canonical_string}")`
  - 確保未來規則變更時不會與舊資料產生相同 hash
- **/portfolio/sync 可觀測性增強**：新增以下回應欄位（不改 DB schema）
  - `sheet_rows_count`：從 Google Sheets 讀取的總列數
  - `normalized_valid_count`：成功轉換為 TradeRecord 的筆數
  - `normalized_invalid_count`：格式錯誤無法轉換的筆數（= errors_count）
  - `duplicates_count`：因 source_hash 重複跳過的筆數（DB 去重）
  - 新欄位讓開發者清楚區分「格式錯誤」與「DB 重複」
- **日誌增強**：在 sync_service.py 加入結構化 log
  - 記錄同步開始、讀取列數、標準化結果、寫入結果、同步狀態
  - 使用 logger.info/warning/exception，不記錄敏感資料
- **測試覆蓋**：新增測試確保加固有效
  - test_hash_versioning.py：驗證版本前綴、hash 一致性、版本變更時 hash 不同
  - test_sync_observability.py：驗證可觀測性欄位正確性、數學關係（skipped = duplicates + errors）
- 更新 Development.md：說明 hash 版本控制目的與可觀測性欄位用途
- 更新 API_CONTRACTS.md：補充 /portfolio/sync 回應的新欄位說明

## [0.2.2] - 2026-01-23（Sprint 1-2：Google Sheets Client 與交易標準化）
- 建立 Google Sheets 整合與交易資料標準化模組
  - 使用 Service Account 認證存取 Google Sheets
  - 支援欄位 mapping（透過環境變數自訂）
  - 交易方向支援中文（買/賣）自動轉換為 BUY/SELL
  - 計算 source_hash（SHA-256）用於去重
- 新增 portfolio-service/app/sheets_client.py（Google Sheets API 客戶端）
- 新增 portfolio-service/app/schemas.py（TradeRecord Pydantic 模型）
- 新增 portfolio-service/app/trade_normalizer.py（資料標準化與 hash 計算）
- 新增 portfolio-service/tests/test_trade_normalizer.py（單元測試，10 個測試案例）
- 更新 portfolio-service/requirements.txt（加入 gspread、google-auth、pydantic）
- 更新 .env.example（加入 GOOGLE_SA_JSON、GOOGLE_SHEET_ID 等環境變數）
- 更新 SECURITY.md（新增 Service Account 金鑰管理說明，含本機/VM/CI 配置方式）
- 更新 Development.md（新增 Sprint 1-2 驗收指令與檔案清單）
- 新增 portfolio-service/verify_sprint_1-2.sh（Sprint 1-2 驗證腳本）
- 修正 conftest.py 使用 SAVEPOINT 模式（消除 SAWarning: transaction already deassociated）

## [0.2.1] - 2026-01-23（Sprint 1-1：Portfolio Service DB Schema）
- 建立 portfolio-service 資料庫 schema 與 migration
  - 使用 SQLAlchemy 2.x + Alembic 管理資料庫
  - 建立三張表：trades（交易流水帳）、positions（持倉快照）、sync_runs（同步記錄）
  - 實作 source_hash 唯一性約束避免重複匯入
  - 實作 (user_id, symbol) 唯一性約束確保持倉唯一
- 新增 portfolio-service/app/db.py（SQLAlchemy engine/session）
- 新增 portfolio-service/app/models.py（ORM models）
- 新增 portfolio-service/alembic（migration 管理）
- 新增 portfolio-service/tests/test_db_schema.py（schema 測試）
- 更新 portfolio-service/requirements.txt（加入 SQLAlchemy、Alembic、asyncpg、psycopg2-binary）
- 更新 portfolio-service/Dockerfile（複製 alembic.ini 與 alembic/ 目錄）
- 新增 portfolio-service/README.md（migration 與測試指令說明，含常見問題）
- 新增 portfolio-service/verify_setup.sh（一鍵驗證腳本，自動處理表格已存在情況）
- 新增 portfolio-service/reset_db.sh（資料庫重置腳本）
- 更新 Development.md 的 Sprint 1-4 說明（使用 docker compose exec）
- 修正 datetime.utcnow() deprecation warning（改用 datetime.now(timezone.utc)）
- 修正測試流程：移除 Base.metadata.create_all()，改為驗證 migration 正確性
- 所有 Docker 命令改用 `docker compose exec` 取代固定容器名稱
- **Sprint 1-2 前置修復**（2026-01-23 補充）
  - 雷 A：移除 asyncpg 依賴，Sprint 1 使用同步 SQLAlchemy + psycopg2-binary
  - 雷 B：引入 transaction-based test fixtures（conftest.py），每個測試自動 rollback 不污染 DB
  - 雷 C：確認 alembic/env.py 已正確設定 target_metadata = Base.metadata（可正常 autogenerate）
  - 文件校正：RUNBOOK.md 中的 `docker exec` 全部改為 `docker compose exec`（VM/CI 友善）

## [0.2.0] - 2026-01-23（Sprint 1-0：文件與契約先行）
- 新增 portfolio-service 完整 API 契約（API_CONTRACTS.md）
  - POST /portfolio/sync：Google Sheets 同步交易流水帳
  - GET /portfolio/positions/latest：最新持倉快照（均價法）
  - GET /portfolio/trades：交易流水帳查詢（支援篩選）
- 新增 Development.md 的 Sprint 1 分段 prompts（Sprint 1-1 至 1-5）
  - 包含驗收方式、測試指令與預期檔案清單
- 補充 Strategy.md 的 Portfolio Service 與 Radar Service 邊界描述
  - 明確定義 positions_snapshot schema
  - 釐清資料流向與服務解耦原則
- 全 repo 文件路徑校正
  - 移除不存在的 web-bff 服務描述
  - 統一改為 api-gateway（實際存在的服務）
  - 在 ARCHITECTURE.md 標註未來可能的 BFF 規劃 (TODO)
- 更新 README.md、ARCHITECTURE.md、API_CONTRACTS.md 使其與實際目錄結構一致

## [0.1.0] - 2026-01-22
- 建立 Radar 戰情室 MVP 微服務骨架。
- 新增 Vue (Vite) 前端與 Vitest 測試。
- 建立 FastAPI 服務：api-gateway、portfolio、radar、news、research。
- 完成 Docker Compose、Makefile、Postgres 組態。
- 提供健康檢查 `/health` 與最小 pytest。
- 新增文件：README、Development、Strategy、Architecture、Runbook、Security、API Contracts、Testing、Deployment。
