# CHANGELOG.md｜版本沿革

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
- 新增 portfolio-service/README.md（migration 與測試指令說明）
- 更新 Development.md 的 Sprint 1-4 說明（migration 執行方式）

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
