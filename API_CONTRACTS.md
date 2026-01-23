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
  "skipped_count": 3,
  "errors_count": 0,
  "synced_at": "2026-01-23T10:30:00Z"
}
```

**說明：**
- `status`: "succeeded" | "failed"
- `inserted_count`: 成功插入的交易記錄數量
- `skipped_count`: 因 source_hash 重複跳過的記錄（去重）
- `errors_count`: 驗證失敗的記錄數量（例如：quantity=0、缺少欄位）
- `synced_at`: 同步完成時間（ISO 8601 格式）

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

#### `GET /portfolio/positions/latest`
回傳最新持倉快照（均價法計算結果）。

**Request**
```
GET /portfolio/positions/latest?user_id=user-uuid
```

**Response 200 OK**
```json
{
  "user_id": "user-uuid",
  "as_of": "2026-01-23T10:00:00Z",
  "positions": [
    {
      "symbol": "QQQ",
      "asset_ccy": "USD",
      "quantity": 100,
      "avg_cost": 388.5,
      "realized_pnl": 0,
      "unrealized_pnl": 1150.0,
      "last_updated_at": "2026-01-23T10:00:00Z"
    }
  ]
}
```

**Error 404 Not Found**
```json
{
  "error": "NO_POSITIONS",
  "message": "尚未同步任何持倉資料"
}
```

#### `GET /portfolio/trades`
查詢交易流水帳（支援篩選）。

**Request**
```
GET /portfolio/trades?user_id=user-uuid&symbol=QQQ&since=2026-01-01
```

**Query Parameters**
- `user_id` (required): 使用者 ID
- `symbol` (optional): 股票代號篩選
- `since` (optional): 起始日期（YYYY-MM-DD）

**Response 200 OK**
```json
{
  "user_id": "user-uuid",
  "total_count": 5,
  "trades": [
    {
      "id": "trade-uuid",
      "symbol": "QQQ",
      "trade_date": "2026-01-15",
      "side": "buy",
      "quantity": 50,
      "price": 395.20,
      "fees": 1.5,
      "created_at": "2026-01-15T09:30:00Z"
    }
  ]
}
```

**Error 400 Bad Request**
```json
{
  "error": "INVALID_PARAMETER",
  "message": "since 參數格式錯誤，請使用 YYYY-MM-DD"
}
```

### 資料庫 Schema

#### `trades` 表（寫入 Postgres）
| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | UUID | 主鍵 |
| user_id | UUID | 使用者 ID |
| symbol | TEXT | 股票代號 |
| trade_date | DATE | 交易日期 |
| side | TEXT | `buy` / `sell` |
| quantity | NUMERIC | 交易數量 |
| price | NUMERIC | 成交價格 |
| fees | NUMERIC | 手續費 |
| created_at | TIMESTAMP | 建立時間 |

#### `positions_snapshot`
| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | UUID | 主鍵 |
| user_id | UUID | 使用者 ID |
| as_of | TIMESTAMP | 快照時間 |
| symbol | TEXT | 股票代號 |
| asset_ccy | TEXT | 資產幣別 |
| quantity | NUMERIC | 持有數量 |
| avg_cost | NUMERIC | 平均成本 |
| realized_pnl | NUMERIC | 已實現損益 |
| unrealized_pnl | NUMERIC | 未實現損益 |
| is_core | BOOLEAN | 是否為核心持股 |
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