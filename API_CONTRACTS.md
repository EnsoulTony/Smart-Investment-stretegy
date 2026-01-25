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

### `GET /dashboard`
```json
{
  "positions": [
    {
      "symbol": "QQQ",
      "quantity": 100,
      "avg_cost": 388.5,
      "market_value": 42000,
      "is_core": true
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
      "cost_basis": 38850.0
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
| source_row_id | TEXT | 原始列識別（可空） |
| source_hash | TEXT | 去重 hash |
| created_at | TIMESTAMP | 建立時間 |

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
| last_updated_at | TIMESTAMP | 最後更新時間 |

## 3. radar-service

### 輸入結構
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

## 4. news-service

### `news_signals`
```json
{
  "id": "uuid",
  "source": "gdelt",
  "headline": "美債殖利率回落",
  "summary": "...",
  "importance": "N1" | "N3",
  "published_at": "2024-01-22T08:00:00Z",
  "tags": ["macro", "inflation"],
  "risk_score": 0.65
}
```

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