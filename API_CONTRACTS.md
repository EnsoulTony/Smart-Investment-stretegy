# API_CONTRACTS.md｜資料契約（MVP）

本文件列出主要微服務之輸入 / 輸出結構，確保前後端與外部整合遵循相同 schema。

## 1. api-gateway

### `GET /health`
```json
{
  "status": "ok",
  "service": "api-gateway"
}
```

### `POST /portfolio/sync`
轉發至 portfolio-service 的同步端點。參見 [2. portfolio-service](#2-portfolio-service) 的 API 規格。

### `GET /portfolio/health`
轉發至 portfolio-service 的健康檢查端點。

**Response 200 OK**
```json
{
  "status": "ok",
  "service": "portfolio-service"
}
```

### `GET /portfolio/positions`
轉發至 portfolio-service 的持倉查詢端點。

### `GET /portfolio/core_holdings`
轉發至 portfolio-service 的核心持股查詢端點。

### `POST /portfolio/core_holdings`
轉發至 portfolio-service 的核心持股設定端點。

### `GET /portfolio/symbol_mappings`
轉發至 portfolio-service 的標的中文名稱映射查詢端點。

### `POST /portfolio/symbol_mappings`
轉發至 portfolio-service 的標的中文名稱映射維護端點。

### `POST /portfolio/symbol_mappings/resolve`
轉發至 portfolio-service 的標的中文名稱自動查詢端點。

### `GET /news/signals`
轉發至 news-service 的 `GET /news/signals` 端點（戰情室 UI 入口）。
（前端統一透過 api-gateway 呼叫，避免跨域與服務直連）

### `GET /radar/decision`
轉發至 radar-service 的 `GET /radar/decision` 端點（決策融合結果）。

### `GET /radar/decisions/history`
轉發至 radar-service 的 `GET /radar/decisions/history` 端點（快照歷史）。

### `GET /dashboard`
```json
{
  "positions": [
    {
      "symbol": "QQQ",
      "quantity": 100,
      "avg_cost": 388.5,
      "market_value": 42000,
      "name_zh": "納斯達克 100 ETF"
    }
  ],
  "news_signals": [...],
  "research_signals": [...],
  "recommendations": [...],
  "indicator_values": {
    "RS_XLU_XLK": {
      "value": 0.83,
      "trend": "overheat"
    }
  }
}
```

## 2. portfolio-service

- 來源：Google Sheets → API or CSV

### API 端點（MVP）

#### `POST /portfolio/sync`
從 Google Sheets 同步交易流水帳到資料庫。

**Request**
```bash
POST /portfolio/sync
# 不需要 body（從環境變數讀取 Google Sheets 資訊）
```

**Response 200 OK**
```json
{
  "status": "succeeded",
  "run_id": "sync-run-uuid",
  "inserted_count": 15,
  "updated_count": 0,
  "skipped_count": 3,
  "errors_count": 0,
  "sheet_rows_count": 20,
  "normalized_valid_count": 18,
  "normalized_invalid_count": 0,
  "duplicates_count": 3
}
```

**說明：**
- `status`: "succeeded" | "failed" | "partial_succeeded"
- `inserted_count`: 成功插入的交易記錄數量
- `updated_count`: 更新的交易記錄數量（目前固定為 0）
- `skipped_count`: 總跳過筆數（= duplicates_count + errors_count）
- `errors_count`: 驗證失敗的記錄數量（格式錯誤、缺少欄位等）
- **可觀測性欄位**（v0.2.3+）：
  - `sheet_rows_count`: 從 Google Sheets 讀取的總列數
  - `normalized_valid_count`: 成功轉換為 TradeRecord 的筆數
  - `normalized_invalid_count`: 格式錯誤無法轉換的筆數（= errors_count）
  - `duplicates_count`: 因 source_hash 重複被資料庫去重的筆數

**Error 400 Bad Request**
```json
{
  "error": "INVALID_SHEET_URL",
  "message": "無法存取 Google Sheets，請檢查權限或連結"
}
```

**Error 401 Unauthorized**
```json
{
  "error": "UNAUTHORIZED",
  "message": "缺少或無效的 JWT token"
}
```

**Error 500 Internal Server Error**
```json
{
  "error": "SYNC_FAILED",
  "message": "同步過程發生錯誤，請稍後再試"
}
```

#### `GET /portfolio/positions`
回傳最新持倉快照（均價法計算結果）。

**Request**
```
GET /portfolio/positions?user_id=user-uuid
```

**Response 200 OK**
```json
{
  "user_id": "user-uuid",
  "asof": null,
  "items": [
        {
          "symbol": "QQQ",
          "asset_ccy": "USD",
          "quantity": 100,
          "avg_cost": 388.5,
          "realized_pnl": 0,
          "cost_basis": 38850.0,
          "name_zh": "納斯達克 100 ETF"
        }
      ],
      "next_cursor": null
    }
```

**Error 404 Not Found**
```json
{
  "error": "NO_POSITIONS",
  "message": "尚未同步任何持倉資料"
}
```

#### `GET /portfolio/trades/summary`
取得指定用戶的交易摘要（輕量探針）。

**Request**
```
GET /portfolio/trades/summary?user_id=user-uuid
```

**Response 200 OK**
```json
{
  "user_id": "user-uuid",
  "trades_count": 5,
  "symbols_count": 3,
  "min_trade_date": "2026-01-01",
  "max_trade_date": "2026-01-20",
  "evidence": {
    "verification_sql": {
      "trades_count": "select count(*) from trades where user_id='user-uuid';",
      "distinct_symbols": "select count(distinct symbol) from trades where user_id='user-uuid';"
    }
  }
}
```

**Error 422 Unprocessable Entity**
```json
{ "detail": { "status": "invalid_request", "message": "missing user_id" } }
```

**Error 502 Bad Gateway**（上游依賴不可用）
```json
{ "detail": { "status": "upstream_error", "service": "postgres", "message": "..." } }
```

**Error 503 Service Unavailable**（必要資料缺失）
```json
{ "detail": { "status": "missing_data", "missing_fields": ["trades"] } }
```

#### `GET /portfolio/core_holdings`
取得使用者目前勾選的核心持股清單（由本地 DB 管理；不依賴 Google Sheet 欄位）。

**Request**
```
GET /portfolio/core_holdings?user_id=user-uuid
```

**Response 200 OK**
```json
{
  "user_id": "user-uuid",
  "symbols": ["TSLA", "OXY"],
  "count": 2
}
```

#### `POST /portfolio/core_holdings`
設定使用者核心持股清單（全量覆寫）。供前端「勾選核心持股」使用。

**Request**
```
POST /portfolio/core_holdings?user_id=user-uuid
```

```json
{
  "symbols": ["TSLA", "OXY", "TSM"]
}
```

**Response 200 OK**
```json
{
  "status": "ok",
  "user_id": "user-uuid",
  "count": 3
}
```

#### `POST /portfolio/core_holdings/rebuild`（Deprecated）
trade is_core 欄位已移除，本端點僅回傳提示訊息，請改用 `/portfolio/core_holdings` 由 UI 設定。

#### `GET /portfolio/symbol_mappings`
取得標的中文名稱映射清單。

**Request**
```
GET /portfolio/symbol_mappings?q=AAPL&limit=200
```

**Response 200 OK**
```json
{
  "items": [
    {
      "symbol": "AAPL",
      "market": "US",
      "name_zh": "蘋果",
      "source": "yahoo_us",
      "updated_at": "2026-01-28T12:30:00Z"
    }
  ]
}
```

#### `POST /portfolio/symbol_mappings`
維護（新增/更新）單筆映射。

**Request**
```json
{
  "symbol": "2330.TW",
  "market": "TW",
  "name_zh": "台積電",
  "source": "manual"
}
```

**Response 200 OK**
```json
{
  "symbol": "2330.TW",
  "market": "TW",
  "name_zh": "台積電",
  "source": "manual",
  "updated_at": "2026-01-28T12:30:00Z"
}
```

#### `POST /portfolio/symbol_mappings/resolve`
用 provider 查詢 symbol，並寫入 mapping table（TW/US）。

**Request**
```json
{
  "symbol": "AAPL",
  "market": "US"
}
```

**Response 200 OK**
```json
{
  "symbol": "AAPL",
  "market": "US",
  "name_zh": "蘋果",
  "source": "yahoo_us",
  "updated_at": "2026-01-28T12:30:00Z"
}
```

### 資料庫 Schema

#### `trades` 表（寫入 Postgres）
| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | INTEGER | 主鍵 |
| user_id | TEXT | 使用者 ID |
| symbol | TEXT | 股票代號 |
| asset_ccy | TEXT | 資產幣別 |
| side | TEXT | `BUY` / `SELL` |
| quantity | NUMERIC | 交易數量 |
| price | NUMERIC | 成交價格 |
| fee | NUMERIC | 手續費 |
| trade_date | TIMESTAMP | 交易日期時間 |
| broker | TEXT | 券商 |
| name_zh | TEXT | 資產中文名稱（由系統查詢寫入） |
| source_row_id | TEXT | 原始列識別（可空） |
| source_hash | TEXT | 去重 hash |
| created_at | TIMESTAMP | 建立時間 |

#### `core_holdings`
| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | INTEGER | 主鍵 |
| user_id | TEXT | 使用者 ID |
| symbol | TEXT | 股票代號 |
| is_core | BOOLEAN | 是否核心（預設 true；該表只存設定結果） |
| updated_at | TIMESTAMP | 更新時間 |

#### `symbol_name_mappings`
| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | INTEGER | 主鍵 |
| symbol | TEXT | 標的代號 |
| market | TEXT | 市場（TW/US） |
| name_zh | TEXT | 中文名稱 |
| source | TEXT | 來源 |
| updated_at | TIMESTAMP | 更新時間 |

#### `positions`
| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | INTEGER | 主鍵 |
| user_id | TEXT | 使用者 ID |
| symbol | TEXT | 股票代號 |
| asset_ccy | TEXT | 資產幣別 |
| quantity | NUMERIC | 持有數量 |
| avg_cost | NUMERIC | 平均成本 |
| realized_pnl | NUMERIC | 已實現損益 |
| u_pnl | NUMERIC | 未實現損益（帳務層固定為 0） |
| name_zh | TEXT | 資產中文名稱 |
| last_updated_at | TIMESTAMP | 最後更新時間 |

## 3. valuation-service（Sprint 1-4.B）

### `GET /valuation/portfolio`

估值層 API（HTTP-only），僅透過 portfolio-service 取數。

**Request**
```
GET /valuation/portfolio?user_id=tony&base_ccy=USD
```

**Response 200 OK**
```json
{
  "status": "succeeded",
  "user_id": "tony",
  "base_ccy": "USD",
  "as_of": "2026-01-27",
  "totals": { "market_value": 120000, "cost_value": 110000, "unrealized_pnl": 10000 },
  "positions": [
    {
      "symbol": "AAPL",
      "asset_ccy": "USD",
      "quantity": 10,
      "avg_cost": 150,
      "cost_value": 1500,
      "price": 190,
      "price_ccy": "USD",
      "market_value": 1900,
      "unrealized_pnl": 400
    }
  ],
  "evidence": {
    "decision": "proceed",
    "precondition_snapshot": { "trades_count": 5, "distinct_symbols_count": 3 },
    "verification": { "portfolio_service_endpoints_called": ["GET /portfolio/trades/summary?user_id=tony"] },
    "providers": { "price_provider": "stub", "fx_provider": "stub" },
    "positions_count": 3,
    "positions_hash": "..."
  }
}
```

**Error 409 Conflict**（前置條件不足）
```json
{ "detail": { "status": "precondition_failed", "message": "trades_count=0;請先執行 sync" } }
```

**Error 422 Unprocessable Entity**
```json
{ "detail": { "status": "invalid_request", "message": "missing user_id" } }
```

**Error 502 Bad Gateway**（上游連線失敗）
```json
{ "detail": { "status": "upstream_error", "service": "portfolio-service", "message": "..." } }
```

**Error 503 Service Unavailable**（必要資料缺失）
```json
{ "detail": { "status": "missing_data", "missing_fields": ["positions"] } }
```

## 4. radar-service

### `GET /radar/decision`（Sprint 4 擴充）

取得策略決策建議。整合 portfolio-service 持倉與 indicator-service 指標，透過 Strategy Engine 產出建議。

**Request**
```
GET /radar/decision?user_id=tony&base_ccy=TWD&plugin=v1.4
```

| 參數 | 必填 | 預設 | 說明 |
| --- | --- | --- | --- |
| user_id | ✓ | - | 使用者 ID |
| base_ccy | - | TWD | 報告幣別 |
| plugin | - | v1.4 | 策略 plugin 名稱 |
| as_of | - | today | 決策日期（YYYY-MM-DD） |

**Response 200 OK（OutputSchema）**
```json
{
  "schema_version": "1.0",
  "as_of": "2025-01-20",
  "user_id": "tony",
  "mode": "RISK_ON",
  "decision": "NO_ACTION",
  "actions": [
    {
      "symbol": "TSLA",
      "action": "HOLD",
      "reason": "mode=RISK_ON, exposure within limits",
      "constraints": { "cooldown_days": 5, "max_position_pct": 0.45 },
      "falsifiable_triggers": [
        { "type": "indicator", "name": "XLK/XLU", "condition": "cross_below_ma50", "value": 3.028 },
        { "type": "indicator", "name": "ratio.slope5", "condition": "sign_flip_to_negative", "value": 0.002 }
      ]
    }
  ],
  "evidence": {
    "engine": "strategy_engine",
    "plugin": "v1.4",
    "inputs_hash": "a1b2c3d4e5f6...",
    "news_context": {
      "tiers_count": { "N1": 2, "N3": 3 },
      "items_used": ["stub-n1", "stub-n3"],
      "score_impact": { "risk_off_score_added": 5.0, "n1_score": 4.0, "n3_score": 1.0 }
    },
    "notes": ["mode=RISK_ON with balanced exposure"],
    "scoring_detail": { "score_on": 5, "score_off": 0, "rules": {...}, "exposure": {...} }
  }
}
```

**必要欄位**

| 欄位 | 說明 |
| --- | --- |
| `mode` | `RISK_ON` / `RISK_OFF` / `TRANSITION` |
| `decision` | `NO_ACTION` / `REDUCE_RISK` / `REBALANCE` / `WATCHLIST` |
| `evidence.inputs_hash` | canonical JSON SHA256（64 字元） |
| `evidence.news_context` | 新聞融合資訊（tiers_count/items_used/score_impact） |
| `actions[].falsifiable_triggers` | 至少 1 個推翻條件 |
| `actions[].constraints.cooldown_days` | 固定 5 天 |

**Error 422 Unprocessable Entity**（radar-service 自身驗證失敗）
```json
{ "detail": { "status": "invalid_request", "message": "Invalid date format" } }
```

**Error 502 Bad Gateway**（radar-service 呼叫上游但連線失敗或上游回傳非 2xx）
```json
{ "detail": { "status": "upstream_error", "service": "portfolio-service", "message": "..." } }
```

**Error 503 Service Unavailable**（radar-service 拿到上游回應但缺少必要欄位）
```json
{ "detail": { "status": "missing_data", "missing_fields": ["indicators.sector_rotation.ratio.slope5"] } }
```

> **責任歸屬**：
> - **indicator-service**：provider 不可用或資料不完整 → 回傳 503（`provider_error`）
> - **radar-service**：上游連線失敗 → 502；上游回應但缺欄位 → 503（`missing_data`）

### `GET /radar/decisions/history`（Sprint 4 新增）

取得決策快照歷史（由 decision_snapshots 落地）。

**Request**
```
GET /radar/decisions/history?user_id=tony&limit=30
```

**Response 200 OK**
```json
[
  {
    "as_of": "2026-01-28",
    "mode": "RISK_ON",
    "decision": "NO_ACTION",
    "inputs_hash": "a1b2c3d4e5f6...",
    "created_at": "2026-01-28T00:00:00Z"
  }
]
```

### Legacy 結構（保留相容）

#### 輸入結構
```json
{
  "positions": [...],
  "indicator_values": {
    "RS_XLU_XLK": {"value": 0.83, "trend": "overheat"},
    "drawdown_pct": 12.4
  }
}
```

### `analysis_runs`
| 欄位 | 型別 |
| --- | --- |
| id | UUID |
| executed_at | TIMESTAMP |
| parameters | JSONB |
| result | JSONB |

### `recommendations`
| 欄位 | 型別 |
| --- | --- |
| id | UUID |
| analysis_run_id | UUID |
| action | TEXT (`reduce_position`, `hold`, `add_position`) |
| confidence | NUMERIC |
| rationale | TEXT |
| impact | JSONB （標記受影響的 symbols） |

---

## 5. indicator-service（Sprint 2 新增）

### `GET /indicators/sector-rotation`

取得 XLU/XLK sector rotation 指標。

**Request**
```
GET /indicators/sector-rotation?symbols=XLU,XLK&as_of=2025-01-20
```

| 參數 | 必填 | 預設 | 說明 |
| --- | --- | --- | --- |
| symbols | - | XLU,XLK | 指標標的（目前僅支援 XLU,XLK） |
| as_of | - | today | 指標日期（YYYY-MM-DD） |

**Response 200 OK**
```json
{
  "as_of": "2025-01-20",
  "version": "0.1",
  "source": "stub",
  "XLU": { "close": 72.0, "ma20": 71.5, "ma50": 71.0 },
  "XLK": { "close": 220.0, "ma20": 218.0, "ma50": 215.0 },
  "ratio": {
    "pair": "XLK/XLU",
    "value": 3.055,
    "ma20": 3.050,
    "ma50": 3.028,
    "slope5": 0.002,
    "value_5d_ago": 3.045
  }
}
```

**Error 422 Unprocessable Entity**
```json
{ "detail": { "status": "invalid_request", "message": "invalid as_of format" } }
```

**Error 502 Bad Gateway**（上游不可用）
```json
{ "detail": { "status": "upstream_error", "service": "data-provider", "message": "..." } }
```

**Error 503 Service Unavailable**（資料不完整）
```json
{ "detail": { "status": "provider_error", "message": "indicator data missing fields" } }
```

**必要欄位**

| 區塊 | 欄位 |
| --- | --- |
| 頂層 | `as_of`, `version`, `source` |
| XLU / XLK | `close`, `ma20`, `ma50` |
| ratio | `pair`, `value`, `ma20`, `ma50`, `slope5` |

**Error 422**
```json
{ "detail": { "status": "invalid_request", "missing_fields": ["symbols.XLU"] } }
```

**Error 503**
```json
{ "detail": { "status": "provider_error", "message": "..." } }
```

---

## 4. news-service

### `GET /news/signals`
以固定規則產出可驗收的新聞訊號（N1/N3），禁止主觀推論。若外部來源關閉或全數失敗，`items` 可能為空。

**Request**
```
GET /news/signals?user_id=user-uuid&as_of=YYYY-MM-DD
```

**Response 200 OK**
```json
{
  "schema_version": "3.0",
  "as_of": "2026-01-27",
  "source": "stub",
  "items": [
    {
      "id": "stub-001",
      "tier": "N1",
      "title": "Fed 利率決議前夕，10年期殖利率飆升至4.7%，TSLA 大跌",
      "published_at": "2026-01-27T09:00:00Z",
      "summary_zh": "市場開始 reprice，交易員認為通膨壓力升溫。",
      "symbols": ["TSLA"],
      "factor_groups": ["growth_tech"],
      "themes": ["rates_central_bank"],
      "falsifiable_triggers": [
        { "type": "market", "name": "US10Y", "condition": "break_above_4.5", "value": 4.5 }
      ],
      "confidence": 0.85
    }
  ]
}
```

**items[] 必要欄位**
- `id`, `tier`(N1|N3), `title`, `published_at`, `summary_zh`
- `symbols[]`, `factor_groups[]`, `themes[]`
- `falsifiable_triggers[]`（>=1）
- `confidence`

**falsifiable_triggers[] 必要欄位**
- `type`, `name`, `condition`, `value`

**環境變數**
- `NEWS_EXTERNAL_ENABLED=1`：啟用外部新聞抓取（RSS/Yahoo）
- `NEWS_EXTERNAL_ENABLED=0`：關閉外部新聞抓取，若無來源則 `items=[]`

**落地說明（Sprint 3）**
- news-service 每次產出 signals 會將 item 落地到 `public.news_signals` 表
- 主要欄位：`title`, `published_at`, `published_date`, `source`, `source_url`, `weight`, `payload`（完整 item JSON）
- **去重規則**：同一來源 + 同一標題 + 同一日期只保留一筆
- **每日上限**：每個來源每天最多 30 筆（依權重排序取前 30）
- **EDS 權重（固定規則）**：
  - N1 = 2；N3 = 1
  - +1：symbols 非空
  - +1：themes 命中 `rates_central_bank` / `credit_event` / `war_energy_supply` / `tariff_sanctions` / `ai_power`
  - +1：falsifiable_triggers 非空

## 5. research-service

### `research_signals`
```json
{
  "id": "uuid",
  "source": "cathay_pdf" | "manual_broker",
  "title": "國泰週報",
  "summary": "...",
  "needs_ocr": false,
  "attachment_url": "https://...",
  "published_at": "2024-01-20",
  "keywords": ["半導體", "AI"],
  "risk_view": "bullish"
}
```

## 6. Frontend expectations

- 所有列表型資料需含 `id` 供 Vue `key` 使用。
- 日期一律 ISO8601。
- 金額使用數字（由前端格式化）。

## 7. 契約變更流程

1. 於 `API_CONTRACTS.md` 更新 schema。
2. 開 Issue / PR 標記「breaking-change」。
3. 更新對應測試與 mock 資料。
4. 通知前端與資料團隊，確認無相依問題。

---

**Sprint 3 更新日期：2026-01-27**

**變更摘要：**
- 新增 `GET /news/signals`（N1/N3 可驗收規則、items contract、triggers schema）
- 新增 `GET/POST /portfolio/core_holdings`（核心持股清單由本地 DB 管理）
- portfolio trades schema 新增 `name_zh` 欄位（中文名稱）
