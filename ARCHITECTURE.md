# ARCHITECTURE.md｜系統架構（MVP）

## 總覽

Smart-Investment-Strategy 採微服務架構，分為前端、API Gateway、四個領域服務與 Postgres 資料庫。所有服務透過 Docker Compose 編排，並在生產環境由 Ubuntu VM + systemd timer + GitHub Actions 自動部署。

```
[Browser]
   |
[Frontend (Vue/Vite)] -- REST --> [api-gateway]
                                      |
    -------------------------------------------------------------------------
    |             |               |                 |              |
 [portfolio]  [radar]         [news]          [research]    [valuation]
    |             |               |                 |              |
    |        [Strategy Engine]    |                 |        (HTTP→portfolio)
    |             |               |                 |              |
    |      [indicator-service]    |                 |              |
    |             |               |                 |              |
    +-------------+---------------+-----------------+              ✗
                  |                                           (禁止 DB 連線)
            [Postgres]

註：只有 portfolio / radar / news / research 連接 Postgres；valuation-service 禁止 DB 連線。
```

**Sprint 邊界標註**
- Sprint 1：portfolio-service + valuation-service guardrails（估值層 HTTP-only）
- Sprint 2：radar-service Strategy Engine + indicator-service（指標讀取）
- Sprint 3：news-service N1/N3 signals（可回歸）+ portfolio-service core_holdings（本地 DB 設定）
- Sprint 4：radar-service Decision Fusion + decision_snapshots（news_signals 融合 + 快照落地）

**服務埠號對照**

| 服務 | 埠號 | 備註 |
| --- | --- | --- |
| api-gateway | 8000 | BFF |
| portfolio-service | 8001 | 帳務層 |
| radar-service | 8002 | 策略引擎 |
| news-service | 8003 | 新聞訊號 |
| research-service | 8004 | 研究訊號 |
| valuation-service | 8005 | 估值層（禁止 DB） |
| indicator-service | 8006 | 市場指標 |

## 服務邊界

- **Frontend**：RWD 戰情室 UI，透過 `api-gateway` 取得資料。
- **api-gateway**：
  - 反向代理（BFF），將請求轉發至後端服務。
  - 目前提供：
    - `POST /portfolio/sync` → portfolio-service
    - `GET /portfolio/health` → portfolio-service
    - `GET /news/signals` → news-service（戰情室首頁使用）
  - JWT 驗證（簡易登入）（TODO）。
  - 聚合 portfolio/radar/news/research 的資料，對前端提供單一 API（TODO）。
- **portfolio-service**：
  - 管理 `trades`、`positions`、均價法計算。
  - 與 Google Sheets 同步資料。
  - 管理使用者設定（例如：`core_holdings` 核心持股清單），做為其他服務的唯一真相來源（DB 持久化）。
- **radar-service**：
  - 執行 Strategy Engine（可插拔架構）。
  - 內含 v1.4 Plugin（EDS 最小可行）。
  - 透過 HTTP 呼叫 `portfolio-service` 取得持倉、`indicator-service` 取得指標。
  - 透過 DB 讀取 `news_signals` 並融合風險分數，輸出單一決策包。
  - 決策結果落地到 `decision_snapshots`（idempotent upsert）。
  - 端點：`GET /radar/decision?user_id=X&base_ccy=TWD`
- **indicator-service**（Sprint 2 新增）：
  - 提供 XLU/XLK sector rotation 指標。
  - 支援 stub provider（CI 離線測試）。
  - 端點：`GET /indicators/sector-rotation?symbols=XLU,XLK`
  - **不得**將指標寫入 `trades` / `positions` 表。
- **valuation-service**：
  - 估值層，**嚴格禁止 DB 連線**（guardrails 鎖死）。
  - 只能透過 HTTP 呼叫 `portfolio-service` 取數。
  - 不得新增 `DATABASE_URL`、不得出現 `postgresql://` 字串。
- **news-service**：
  - 產出新聞訊號 `GET /news/signals`（N1/N3 以固定打分規則決定 tier，可回歸）。
  - 透過 HTTP 向 `portfolio-service` 取得 `core_holdings`（核心持股清單），避免寫死 holdings 與重複邏輯。
  - Sprint 3 先提供 deterministic stub provider，避免外部資料源造成測試漂移（後續可替換真 provider）。
  - signals 會落地到 `public.news_signals`（供後續分析與 UI 查詢）。
  - 落地規則：同來源同標題同日期去重；每來源每日最多 30 筆（依 EDS 權重排序）。
- **research-service**：
  - 抓取國泰 PDF、允許手動匯入券商報告，產出 `research_signals`。
- **Postgres**：
  - 單一資料庫，透過 schema 與權限區隔各服務表格。

## 資料流程

1. `portfolio-service` 啟動時同步 Google Sheets → 寫入 `trades`、`positions`。
2. 使用者透過前端介面勾選核心持股 → `portfolio-service` 寫入 `core_holdings`（本地 DB）。
3. `radar-service` 讀取 `indicator_values`（含 `RS_XLU_XLK`）+ 持倉資料 → 產出建議。
4. `news-service` 以請求時點（as_of）產出 news signals，並引用 `core_holdings` 輔助打分/映射（不直接讀 DB）。
5. `news-service` 同步將 signals 落地至 `news_signals` 表。
6. `api-gateway` 聚合上述資料 → 提供戰情室 UI（前端統一走 gateway）。
7. `radar-service` 讀取 `news_signals` + 指標快照 → 融合決策並落地 `decision_snapshots`。

## 部署拓樸

- **開發環境**：`docker compose up -d --build`。
- **生產環境**：
  - Ubuntu VM 安裝 Docker、docker compose plugin。
  - GitHub Actions 使用 SSH 將最新程式碼拉到 VM，執行 `make docker-up`。
  - systemd timer 每 15 分鐘觸發檢查腳本，確保服務存活。

## 監控與日誌

- 所有容器標準輸出由 Docker 管理，可透過 `make docker-logs` 查看。
- 重要指標（health check, radar-job 結果）將在下一版導入集中式日誌。

---

## Strategy Engine 架構（Sprint 2）

```
radar-service/app/strategy_engine/
├── __init__.py          # 模組匯出
├── schemas.py           # 固定 InputSchema / OutputSchema（Pydantic）
├── engine.py            # Plugin loader + executor + canonical hash
└── plugins/
    └── v1_4/
        ├── __init__.py
        ├── plugin.py    # V1_4Plugin 實作
        └── rules.py     # 計分規則、factor groups、exposure
```

**設計原則**

1. **固定 Schema Contract**：`InputSchema` / `OutputSchema` 欄位可增不可刪。
2. **可插拔 Plugin**：每個 plugin 實作 `StrategyPlugin` 介面（`execute(input) -> output`）。
3. **可證偽輸出**：每個 action 必含 `falsifiable_triggers`、`cooldown_days=5`。
4. **可重現 Hash**：`evidence.inputs_hash` 為 canonical JSON 的 SHA256。

---

## 層級邊界與 Guardrails

### Sprint 1 Guardrails（不得破壞）

| 服務 | 規則 |
| --- | --- |
| **valuation-service** | 禁止 DB 連線（guardrails.py runtime check） |
| **valuation-service** | 不得出現 `DATABASE_URL`、`postgresql://` |
| **valuation-service** | 只能透過 HTTP 呼叫 `portfolio-service` |
| **portfolio-service** | 僅管交易/持倉/均價法，不含估值/FX/市價 |

### Sprint 2 新增邊界

| 服務 | 規則 |
| --- | --- |
| **indicator-service** | 提供唯讀指標 API，不寫入任何 DB |
| **radar-service** | 透過 HTTP 組合 portfolio + indicators，不直接存取 indicator DB |
| **Strategy Engine** | 只用 positions + indicators + signals，不引入估值/FX/市價 |

**禁止事項（硬性）**
- valuation-service：禁止任何 DB driver / connection string（`DATABASE_URL`、`postgresql://`）
- portfolio-service：禁止匯率折算與估值欄位（`market_value` / `valuation_ccy`）
- indicator-service：不得寫入 trades/positions 表

---

**Sprint 2 更新日期：2026-01-26**

**變更摘要：**
- 更新架構圖含 indicator-service 與 valuation-service
- 新增 Strategy Engine 架構說明
- 新增層級邊界與 Guardrails 章節
- 明確 Sprint 1 guardrails 不得破壞
