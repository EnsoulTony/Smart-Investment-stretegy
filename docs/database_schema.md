# database_schema.md｜資料庫清單與欄位定義（MVP）

本文件整理目前專案中已落地的主要資料表與欄位定義，提供前後端與驗收腳本查核使用。

> 備註
> - 實際欄位以 Alembic migration 為準。
> - `valuation-service` 禁止 DB 連線。
> - 所有時間欄位皆以 UTC 為基準（由 DB 預設 now()）。

---

## 1) portfolio-service

### trades
交易流水帳（Google Sheets 同步來源）

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | BIGSERIAL | 主鍵 |
| user_id | TEXT | 使用者 ID |
| symbol | TEXT | 標的代號 |
| asset_ccy | TEXT | 資產幣別 |
| side | TEXT | BUY/SELL |
| quantity | NUMERIC | 交易數量 |
| price | NUMERIC | 交易價格 |
| fee | NUMERIC | 手續費 |
| trade_date | TIMESTAMP | 交易日期 |
| broker | TEXT | 券商 |
| name_zh | TEXT | 資產中文名稱（查詢後寫入） |
| source_hash | TEXT | 去重 hash（唯一） |
| created_at | TIMESTAMP | 建立時間 |
| updated_at | TIMESTAMP | 更新時間 |

### positions
持倉快照（均價法重建）

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | BIGSERIAL | 主鍵 |
| user_id | TEXT | 使用者 ID |
| symbol | TEXT | 標的代號 |
| asset_ccy | TEXT | 資產幣別 |
| quantity | NUMERIC | 持倉數量 |
| avg_cost | NUMERIC | 均價 |
| realized_pnl | NUMERIC | 已實現損益 |
| cost_basis | NUMERIC | 成本基礎 |
| name_zh | TEXT | 資產中文名稱 |
| created_at | TIMESTAMP | 建立時間 |
| updated_at | TIMESTAMP | 更新時間 |

### sync_runs
同步記錄（portfolio sync）

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | UUID | 主鍵 |
| user_id | TEXT | 使用者 ID |
| status | TEXT | succeeded/failed/partial |
| inserted_count | INTEGER | 新增筆數 |
| updated_count | INTEGER | 更新筆數 |
| skipped_count | INTEGER | 跳過筆數 |
| errors_count | INTEGER | 錯誤筆數 |
| sheet_rows_count | INTEGER | 表單列數 |
| normalized_valid_count | INTEGER | 合法列數 |
| normalized_invalid_count | INTEGER | 不合法列數 |
| duplicates_count | INTEGER | 重複筆數 |
| created_at | TIMESTAMP | 建立時間 |

### core_holdings
使用者核心持股清單（本地 DB 設定）

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | BIGSERIAL | 主鍵 |
| user_id | TEXT | 使用者 ID |
| symbol | TEXT | 標的代號 |
| is_core | BOOLEAN | 是否核心（預設 true） |
| updated_at | TIMESTAMP | 更新時間 |

### symbol_name_mappings
標的中文名稱映射（symbol → name_zh）

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | BIGSERIAL | 主鍵 |
| symbol | TEXT | 標的代號 |
| market | TEXT | 市場（TW/US） |
| name_zh | TEXT | 中文名稱 |
| source | TEXT | 來源（yahoo_tw/yahoo_us/manual） |
| updated_at | TIMESTAMP | 更新時間 |

---

## 2) radar-service

### decision_snapshots
決策快照（Sprint 4）

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | BIGSERIAL | 主鍵 |
| user_id | TEXT | 使用者 ID |
| as_of | DATE | 決策日期 |
| plugin | TEXT | plugin 版本（v1.4） |
| mode | TEXT | RISK_ON / RISK_OFF / TRANSITION |
| decision | TEXT | NO_ACTION / REDUCE_RISK / REBALANCE / WATCHLIST |
| inputs_hash | TEXT | canonical input hash |
| payload | JSONB | 完整決策包 |
| created_at | TIMESTAMP | 建立時間 |
| updated_at | TIMESTAMP | 更新時間 |

索引 / 約束：
- unique (user_id, as_of, plugin)
- index (user_id, as_of desc)

---

## 3) news-service

### news_signals
新聞訊號落地（Sprint 3）

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| id | BIGSERIAL | 主鍵 |
| user_id | TEXT | 使用者 ID |
| item_id | TEXT | 原始新聞 id |
| title | TEXT | 標題 |
| summary_zh | TEXT | 中文摘要 |
| published_at | TIMESTAMP | 發布時間 |
| published_date | DATE | 發布日期 |
| tier | TEXT | N1 / N3 |
| source_url | TEXT | 原文連結 |
| source | TEXT | 來源 |
| as_of | DATE | 產出日期 |
| weight | INTEGER | EDS 權重 |
| payload | JSONB | 原始訊號內容 |
| created_at | TIMESTAMP | 建立時間 |

索引 / 約束：
- unique (source, title, published_date)
- index (source, published_date)
- index (user_id)
- index (published_at)

---

## 4) research-service

### research_signals
研究報告訊號（未完整展開，依實際 migration 為準）

---

## 5) indicator-service

### indicator_values
市場指標（XLU/XLK 等）

---

## 6) other / legacy

### analysis_runs / recommendations
歷史分析紀錄（早期結構，依 API_CONTRACTS.md）
