# CHANGELOG.md｜版本沿革

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
