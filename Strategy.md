# Strategy.md｜Radar v1.4 策略說明（MVP）

本文件定義 Radar v1.4 的策略邊界、抽換規則、因子群組與指標計算方式，適用於 services/radar-service 及任何引用 Strategy Engine 的服務。

## Portfolio Service 與 Radar Service 邊界

### Portfolio Service 職責
- 管理交易流水帳（`trades` 表）。
- 計算均價法持倉（`positions` 表）。
- 產出持倉快照，包含以下欄位：
  - `user_id`: 使用者 ID
  - `symbol`: 股票代號
  - `asset_ccy`: 資產幣別
  - `quantity`: 持有數量
  - `avg_cost`: 平均成本
  - `realized_pnl`: 已實現損益
  - `u_pnl`: 未實現損益（帳務層固定為 0）
  - `last_updated_at`: 最後更新時間

### Radar Service 職責
- **只讀取** `positions` 表，取得最新持倉快照。
- **不直接接觸** `trades` 表，避免與 portfolio-service 耦合。
- 讀取 `indicator_values` 表（例如 `RS_XLU_XLK`、`drawdown_pct`）。
- 執行策略引擎分析，產出 `analysis_runs` 與 `recommendations`。

### 資料流向
```
[Google Sheets] 
    ↓
[portfolio-service] → 寫入 trades → 計算 positions
                                          ↓
                                    [radar-service] 讀取 positions + indicator_values
                                          ↓
                                    產出 recommendations
```

### 重要原則
- **單一資料來源**：持倉與交易資料由 portfolio-service 管理。
- **服務解耦**：radar-service 透過 positions 介面取得持倉資訊，不依賴 trades 實作細節。
- **策略抽換性**：Radar v1.4 策略引擎可抽換，但 positions schema 為穩定契約。

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
  - 未實現損益 = (現價 − 平均成本) × 淨持有數量（當前帳務層不計算，`u_pnl` 固定為 0）。
- 均價法結果寫入 `positions` 與 `indicator_values`，供策略判斷核心持股是否仍在獲利。

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

## Portfolio Service 內部邊界：帳務層 vs 估值層

### 當前階段：Sprint 1-4.3（帳務層完成）

**帳務層（Accounting Layer）**：
- ✅ 交易同步（Google Sheets → trades 表）
- ✅ 均價法計算（`avg_cost_calculator.py`）
- ✅ 持倉重算（`position_rebuilder.py`）
- ✅ 已實現損益累積（`realized_pnl`）

**❌ 硬禁止項目**（Sprint 1-4.3 階段）：
- 呼叫 FX 模組（`from app.fx import ...`）
- 匯率折算邏輯（`convert(amount, from_ccy, to_ccy)`）
- 市價估值計算（`u_pnl` 必須固定為 0）
- 新增估值欄位（`valuation_ccy`、`market_value`）

---

### 未來階段：Sprint 1-4.B（估值層）

**估值層（Valuation Layer）** - 未實作：
- ⏸ 真實匯率資料源（Yahoo Finance / 央行牌告 / Alpha Vantage）
- ⏸ 匯率 cache 機制（Redis / DB rates 表）
- ⏸ 市價估值計算（`quantity * market_price * fx_rate`）
- ⏸ 透過 Alembic migration 新增 `valuation_ccy` / `market_value` 欄位

**架構保證**：
```
┌─────────────────────────────────────────┐
│       Portfolio Service                 │
├─────────────────────────────────────────┤
│  Accounting Layer    Valuation Layer    │
│  (Sprint 1-4.3)      (Sprint 1-4.B)     │
│  ❌ 禁止呼叫 FX      ✅ 可呼叫 FX       │
│  - rebuild_*         - valuation_*      │
│  - avg_cost_*        - market_value_*   │
│                             ↓           │
│         FX Module (Sprint 1-4.A)        │
│         get_fx_provider() ← 唯一入口    │
│         ├── StubFxProvider (當前)       │
│         └── YahooFxProvider (未來)      │
└─────────────────────────────────────────┘
```

---

### FX 模組邊界守則（Guardrails）

**硬禁止規則**（已實作 6 個自動檢查測試）：

1. **匯率邏輯集中化**
   - ❌ 除 `app/fx/*` 之外，禁止直接讀取 `FX_*` / `VALUATION_*` 環境變數
   - ❌ 除 `app/fx/*` 之外，禁止直接 import 匯率 provider 實作
   - ✅ **唯一入口**：`app.fx.get_fx_provider()`（或等價 factory）

2. **帳務層不做折算**（最陰險的發散來源）
   - ❌ 帳務模組（`position_rebuilder.py`、`avg_cost_calculator.py`、`trades_repository.py`）**禁止**呼叫 `fx.convert()` 或 `fx.get_rate()`
   - ❌ 帳務 API（`rebuild_positions`、`calculate_avg_cost`）**禁止**接受 `target_ccy` 參數
   - ✅ **僅估值層**（Sprint 1-4.B 之後的 `valuation_service.py`）可呼叫 FX API
   - ✅ 帳務層只記錄原始幣別（`asset_ccy`）和原始金額，不做任何折算

2. **帳務層純淨性**
   - ❌ `position_rebuilder.py` / `avg_cost_calculator.py` 禁止呼叫 FX 模組
   - ✅ 只使用原幣別（`asset_ccy`）進行帳務計算

3. **測試執行規範**
   - ❌ 禁止在 repo root 的 host venv 執行 `pytest`（會跨 service 收集測試）
   - ✅ 必須在容器內執行：`docker compose exec -T portfolio-service pytest ...`

**驗收命令**（可證偽證據）：

```bash
# FX 模組測試（介面 + Stub + Guardrails）
docker compose exec -T portfolio-service pytest -q -k fx
# 期望：20 passed, 55 deselected

# 測試收集證據（確認 20 個測試來源）
docker compose exec -T portfolio-service pytest -q -k fx --collect-only
# 輸出：20/75 tests collected (55 deselected)
# - tests/test_fx.py: 14 tests
# - tests/test_fx_guardrails.py: 6 tests

# 帳務層不呼叫 FX 驗證
grep -rn "from app.fx" services/portfolio-service/app   --include="*.py"   --exclude-dir=fx   --exclude-dir=__pycache__
# 期望：（空，無任何匹配）
```

### Sprint 1-4.B：估值層骨架（API-only 取數邊界）

**當前階段**（2026-01-24）：估值服務骨架已完成，實作架構鐵律。

**未來階段**（Sprint 1-4.C+）：擴充市價、FX provider、未實現損益計算。

#### 📐 服務邊界明確化

```
估值層 (valuation-service)          帳務層 (portfolio-service)
─────────────────────────           ─────────────────────────

✅ 責任：                            ✅ 責任：
- 市價取得（未來）                   - 均價計算（avg_cost）
- 匯率折算（未來）                   - 已實現損益（realized_pnl）
- 未實現損益計算（未來）             - 持倉數量（quantity）
- 估值快照儲存（未來）               - 原始幣別記錄（asset_ccy）

✅ 取數方式：                        ✅ 取數方式：
- HTTP API only                      - DB query (允許)
- PortfolioClient.get_positions()    - SQLAlchemy Session
- PORTFOLIO_BASE_URL 環境變數        - DATABASE_URL 環境變數

❌ 禁止：                            ❌ 禁止：
- 任何 DB driver (sqlalchemy/psycopg2) - fx.get_rate() / fx.convert()
- DATABASE_URL 環境變數               - market_value 計算
- postgresql:// 連線字串              - u_pnl 計算（除 0 填充）
```

#### 🔬 驗收證據（可證偽）

```bash
# 1. valuation-service 健康檢查
curl -s http://localhost:8005/health | jq
# 期望：{"status": "healthy", "service": "valuation-service"}

# 2. 環境變數檢查（HTTP URL，非 DB URL）
docker compose exec -T valuation-service python -c "import os; print(os.getenv('PORTFOLIO_BASE_URL'))"
# 期望：http://portfolio-service:8001

# 3. Guardrails 測試（估值層禁止 DB）
docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
# 期望：4 passed（禁止 sqlalchemy/psycopg2/postgresql://）

# 4. Guardrails 測試（帳務層禁止估值）
docker compose exec -T portfolio-service pytest -q tests/test_guardrails_accounting_boundary.py
# 期望：4 passed（禁止 FX 呼叫、估值計算）

# 5. 全量測試（確認架構邊界不影響現有功能）
docker compose exec -T portfolio-service pytest -q
# 期望：79 passed（75 原有 + 4 新 Guardrails）

docker compose exec -T valuation-service pytest -q
# 期望：5 passed（4 Guardrails + 1 health）
```

---


### Sprint 1-4.B：估值層骨架（API-only 取數邊界）

**當前階段**（2026-01-24）：估值服務骨架已完成，實作架構鐵律。

**未來階段**（Sprint 1-4.C+）：擴充市價、FX provider、未實現損益計算。

#### 📐 服務邊界明確化

```
估值層 (valuation-service)          帳務層 (portfolio-service)
─────────────────────────           ─────────────────────────

✅ 責任：                            ✅ 責任：
- 市價取得（未來）                   - 均價計算（avg_cost）
- 匯率折算（未來）                   - 已實現損益（realized_pnl）
- 未實現損益計算（未來）             - 持倉數量（quantity）
- 估值快照儲存（未來）               - 原始幣別記錄（asset_ccy）

✅ 取數方式：                        ✅ 取數方式：
- HTTP API only                      - DB query (允許)
- PortfolioClient.get_positions()    - SQLAlchemy Session
- PORTFOLIO_BASE_URL 環境變數        - DATABASE_URL 環境變數

❌ 禁止：                            ❌ 禁止：
- 任何 DB driver (sqlalchemy/psycopg2) - fx.get_rate() / fx.convert()
- DATABASE_URL 環境變數               - market_value 計算
- postgresql:// 連線字串              - u_pnl 計算（除 0 填充）
```

#### 🔬 驗收證據（可證偽）

```bash
# 1. valuation-service 健康檢查
curl -s http://localhost:8005/health | jq
# 期望：{"status": "healthy", "service": "valuation-service"}

# 2. 環境變數檢查（HTTP URL，非 DB URL）
docker compose exec -T valuation-service python -c "import os; print(os.getenv('PORTFOLIO_BASE_URL'))"
# 期望：http://portfolio-service:8001

# 3. Guardrails 測試（估值層禁止 DB）
docker compose exec -T valuation-service pytest -q tests/test_guardrails_no_db.py
# 期望：4 passed（禁止 sqlalchemy/psycopg2/postgresql://）

# 4. Guardrails 測試（帳務層禁止估值）
docker compose exec -T portfolio-service pytest -q tests/test_guardrails_accounting_boundary.py
# 期望：4 passed（禁止 FX 呼叫、估值計算）

# 5. 全量測試（確認架構邊界不影響現有功能）
docker compose exec -T portfolio-service pytest -q
# 期望：79 passed（75 原有 + 4 新 Guardrails）

docker compose exec -T valuation-service pytest -q
# 期望：5 passed（4 Guardrails + 1 health）
```

---

## 後續擴充

## 後續擴充

- 新增更多因子群組（C 組：情緒、D 組：宏觀因子）。
- 提供回測模組（記錄在 `Strategy.md` 擴充章節）。
- 在 `API_CONTRACTS.md` 補充新的輸入輸出 schema 後，方可實作。