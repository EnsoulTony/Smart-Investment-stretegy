# Strategy.md｜Radar v1.4 策略說明（MVP）

本文件定義 Radar v1.4 的策略邊界、抽換規則、因子群組與指標計算方式，適用於 services/radar-service 及任何引用 Strategy Engine 的服務。

## Portfolio Service 與 Radar Service 邊界

### Portfolio Service 職責
- 管理交易流水帳（`trades` 表）。
- 計算均價法持倉（`positions_snapshot` 表）。
- 產出持倉快照，包含以下欄位：
  - `user_id`: 使用者 ID
  - `symbol`: 股票代號
  - `asset_ccy`: 資產幣別
  - `quantity`: 持有數量
  - `avg_cost`: 平均成本
  - `realized_pnl`: 已實現損益
  - `unrealized_pnl`: 未實現損益（需搭配市價計算）
  - `last_updated_at`: 最後更新時間

### Radar Service 職責
- **只讀取** `positions_snapshot` 表，取得最新持倉快照。
- **不直接接觸** `trades` 表，避免與 portfolio-service 耦合。
- 讀取 `indicator_values` 表（例如 `RS_XLU_XLK`、`drawdown_pct`）。
- 執行策略引擎分析，產出 `analysis_runs` 與 `recommendations`。

### 資料流向
```
[Google Sheets] 
    ↓
[portfolio-service] → 寫入 trades → 計算 positions_snapshot
                                          ↓
                                    [radar-service] 讀取 positions_snapshot + indicator_values
                                          ↓
                                    產出 recommendations
```

### 重要原則
- **單一資料來源**：持倉與交易資料由 portfolio-service 管理。
- **服務解耦**：radar-service 透過 positions_snapshot 介面取得持倉資訊，不依賴 trades 實作細節。
- **策略抽換性**：Radar v1.4 策略引擎可抽換，但 positions_snapshot schema 為穩定契約。

## 策略抽換邊界

- **Modules**：`Strategy Engine`（核心框架） + `Strategy Plugin`（可抽換邏輯）。
- **固定區域**（不得在未經架構審核下修改）：
  - 資料輸入格式（positions, trades, indicator_values）。
  - 輸出 schema（`analysis_runs`, `recommendations`）。
- **可抽換區域**：
  - 指標組合與權重（A/B 因子群組）。
  - 風險閾值（回撤百分比、持股比例調整等）。
  - 輸出建議文案模板。

## Radar v1.4 因子群組

- **A 組（趨勢/風格）**：
  - `RS_XLU_XLK`（日線，相對強弱）
  - 市場寬度指標（後續版本可加入）
- **B 組（風險/波動）**：
  - 回撤（Drawdown %）
  - 均價法盈虧

策略引擎將 A/B 因子結果結合，產生權重建議與建議文字。

## 均價法盈虧計算

- 依照 `trades` 欄位中的買/賣紀錄計算平均成本。
- 公式：
  - 平均成本 = (∑(買入價格 × 數量) − ∑(賣出價格 × 數量，若需調整)) / 淨持有數量。
  - 未實現損益 = (現價 − 平均成本) × 淨持有數量。
- 均價法結果寫入 `positions_snapshot` 與 `indicator_values`，供策略判斷核心持股是否仍在獲利。

## 趨勢條件與調整規則

1. **趨勢過熱 + 回撤 > 10% + 核心持股仍有獲利**
   - 條件：
     - `RS_XLU_XLK` 顯示趨勢過熱（低波防禦類股大幅跑輸高成長類股）。
     - `drawdown_pct > 10%`。
     - 核心持股（標記 `is_core = true`）的均價法損益為正。
   - 行動：
     - 推出「獲利減碼 30%」建議，並寫入 `recommendations`。

2. **趨勢反轉**
   - 條件：
     - `RS_XLU_XLK` 明顯轉向（連續 N 日趨勢翻轉，預設 N=3）。
     - 或外部風險指標顯示資金快速撤出成長資產。
   - 行動：
     - 推出「獲利減碼 70%」建議，聚焦核心持股與高風險部位。

## `RS_XLU_XLK` 指標（日線）

- **定義**：
  - RS = `Close(XLU) / Close(XLK)`。
  - 使用日線資料，計算 5 日與 20 日移動平均判斷趨勢（MA5 > MA20 → 防禦領先）。
- **用途**：
  - 判斷市場風險偏好（低波 vs. 高成長）。
  - 為策略引擎提供趨勢過熱或反轉訊號。
- **資料來源**：
  - 透過外部 API 或內部批次，寫入 `indicator_values`。

## 輸出格式

- `analysis_runs`：紀錄每一次策略執行的輸入參數、產生的因子狀態、時間戳。
- `recommendations`：
  - `action`: `reduce_position`, `hold`, `add_position` 等。
  - `confidence`: 0~1。
  - `rationale`: 中文描述（列出 RS、回撤、核心盈虧等依據）。

## 後續擴充

- 新增更多因子群組（C 組：情緒、D 組：宏觀因子）。
- 提供回測模組（記錄在 `Strategy.md` 擴充章節）。
- 在 `API_CONTRACTS.md` 補充新的輸入輸出 schema 後，方可實作。