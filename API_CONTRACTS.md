# API_CONTRACTS.md｜資料契約（MVP）

本文件列出主要微服務之輸入 / 輸出結構，確保前後端與外部整合遵循相同 schema。

## 1. api-gateway / web-bff

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

### `trades` 表（寫入 Postgres）
| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | UUID | 主鍵 |
| symbol | TEXT | 股票代號 |
| trade_date | DATE | 交易日期 |
| side | TEXT | `buy` / `sell` |
| quantity | NUMERIC | 交易數量 |
| price | NUMERIC | 成交價格 |
| fees | NUMERIC | 手續費 |

### `positions_snapshot`
| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | UUID |
| as_of | TIMESTAMP |
| symbol | TEXT |
| quantity | NUMERIC |
| avg_cost | NUMERIC |
| market_price | NUMERIC |
| unrealized_pl | NUMERIC |
| is_core | BOOLEAN |

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