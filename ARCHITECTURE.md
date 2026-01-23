# ARCHITECTURE.md｜系統架構（MVP）

## 總覽

Smart-Investment-Strategy 採微服務架構，分為前端、API Gateway、四個領域服務與 Postgres 資料庫。所有服務透過 Docker Compose 編排，並在生產環境由 Ubuntu VM + systemd timer + GitHub Actions 自動部署。

```
[Browser]
   |
[Frontend (Vue/Vite)] -- REST --> [api-gateway]
                                      |
          -------------------------------------------------------------
          |             |               |                 |
 [portfolio-service] [radar-service] [news-service] [research-service]
          |             |               |                 |
                              [Postgres]
```

## 服務邊界

- **Frontend**：RWD 戰情室 UI，透過 `api-gateway` 取得資料。
- **api-gateway**：
  - 反向代理（BFF），將請求轉發至後端服務。
  - 目前提供：
    - `POST /portfolio/sync` → portfolio-service
    - `GET /portfolio/health` → portfolio-service
  - JWT 驗證（簡易登入）（TODO）。
  - 聚合 portfolio/radar/news/research 的資料，對前端提供單一 API（TODO）。
- **portfolio-service**：
  - 管理 `trades`、`positions_snapshot`、均價法計算。
  - 與 Google Sheets 同步資料。
- **radar-service**：
  - 執行 Strategy Engine（Radar v1.4）。
  - 寫入 `analysis_runs` 與 `recommendations`。
- **news-service**：
  - 抓取 GDELT、RSS（N1/N3），產出 `news_signals`。
- **research-service**：
  - 抓取國泰 PDF、允許手動匯入券商報告，產出 `research_signals`。
- **Postgres**：
  - 單一資料庫，透過 schema 與權限區隔各服務表格。

## 資料流程

1. `portfolio-service` 啟動時同步 Google Sheets → 寫入 `trades`、`positions_snapshot`。
2. `radar-service` 讀取 `indicator_values`（含 `RS_XLU_XLK`）+ 持倉資料 → 產出建議。
3. `news-service` / `research-service` 週期性擷取資料，寫入 `news_signals` / `research_signals`。
4. `api-gateway` 聚合上述資料 → 提供前端 UI。

## 部署拓樸

- **開發環境**：`docker compose up -d --build`。
- **生產環境**：
  - Ubuntu VM 安裝 Docker、docker compose plugin。
  - GitHub Actions 使用 SSH 將最新程式碼拉到 VM，執行 `make docker-up`。
  - systemd timer 每 15 分鐘觸發檢查腳本，確保服務存活。

## 監控與日誌

- 所有容器標準輸出由 Docker 管理，可透過 `make docker-logs` 查看。
- 重要指標（health check, radar-job 結果）將在下一版導入集中式日誌。