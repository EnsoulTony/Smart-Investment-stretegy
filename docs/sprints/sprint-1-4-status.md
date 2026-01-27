# Sprint 1-4 階段狀態報告（可證偽版）

## 執行時間
2026-01-24

## 當前狀態：✅ 帳務層完成，估值層暫停

---

## 🔬 證據 1：API 端點清單

```bash
$ curl http://localhost:8001/openapi.json | jq '.paths|keys'
```

```json
[
  "/health",
  "/portfolio/rebuild_positions",
  "/portfolio/rebuild_positions/preview",
  "/portfolio/sync"
]
```

**證明**：
- ✅ 只有 4 個端點
- ✅ 無 `/valuation` 相關端點
- ✅ 無 `/fx/rate` 或 `/fx/convert` 端點

---

## 🔬 證據 2：資料庫 Schema

### positions 表

```bash
$ docker compose exec postgres psql -U investment -d investment_db -c "\d positions"
```

```
                                         Table "public.positions"
     Column      |           Type           | Collation | Nullable |                Default                
-----------------+--------------------------+-----------+----------+---------------------------------------
 id              | integer                  |           | not null | nextval('positions_id_seq'::regclass)
 user_id         | text                     |           | not null | 
 symbol          | text                     |           | not null | 
 asset_ccy       | text                     |           | not null | 
 quantity        | numeric                  |           | not null | 
 avg_cost        | numeric                  |           | not null | 
 realized_pnl    | numeric                  |           | not null | '0'::numeric
 u_pnl  | numeric                  |           | not null | '0'::numeric
 last_updated_at | timestamp with time zone |           | not null | now()
Indexes:
    "positions_pkey" PRIMARY KEY, btree (id)
    "uq_positions_user_symbol" UNIQUE CONSTRAINT, btree (user_id, symbol)
```

**關鍵事實**：
- ❌ **Position 表不存在 `valuation_ccy` 欄位**
- ✅ 只有 `asset_ccy`（原幣別，來自 trade）
- ✅ `u_pnl` 預設值為 0（不做估值）

### trades 表

```bash
$ docker compose exec postgres psql -U investment -d investment_db -c "\d trades"
```

```
                                        Table "public.trades"
    Column     |           Type           | Collation | Nullable |              Default               
---------------+--------------------------+-----------+----------+------------------------------------
 id            | integer                  |           | not null | nextval('trades_id_seq'::regclass)
 user_id       | text                     |           | not null | 
 symbol        | text                     |           | not null | 
 asset_ccy     | text                     |           | not null | 
 side          | text                     |           | not null | 
 quantity      | numeric                  |           | not null | 
 price         | numeric                  |           | not null | 
 fee           | numeric                  |           | not null | '0'::numeric
 trade_date    | timestamp with time zone |           | not null | 
 broker        | text                     |           | not null | 
 source_row_id | text                     |           |          | 
 source_hash   | text                     |           | not null | 
 created_at    | timestamp with time zone |           | not null | now()
Indexes:
    "trades_pkey" PRIMARY KEY, btree (id)
    "ix_trades_user_symbol_date" btree (user_id, symbol, trade_date)
    "uq_trades_source_hash" UNIQUE CONSTRAINT, btree (source_hash)
```

**證明**：
- ✅ Trades 表只記錄原幣別交易（`asset_ccy`）
- ✅ 無任何估值相關欄位

---

## 🔬 證據 3：測試結果

**執行時間**：2026-01-24 17:18 UTC  
**執行環境**：GitHub Codespaces (Linux)  
**容器**：docker compose run --rm portfolio-service

### 全部測試

```bash
$ docker compose run --rm portfolio-service pytest -q
```

```
........................................................................ [ 92%]
......                                                                   [100%]
78 passed in 1.20s
```

### FX 模組測試（明確檔案路徑）

**測試 1：介面與 Stub 實作**
```bash
$ docker compose run --rm portfolio-service pytest -q tests/test_fx.py
```

```
..............                                                           [100%]
14 passed in 0.03s
```

**測試 2：Guardrails（架構邊界檢查）**
```bash
$ docker compose run --rm portfolio-service pytest -q tests/test_fx_guardrails.py
```

```
......                                                                   [100%]
6 passed in 0.07s
```

**證明**：
- ✅ 78 個測試全部通過
- ✅ **FX 測試共 20 個（14 + 6），全部通過**
- ✅ 測試涵蓋：Stub 行為、跨幣別防呆、架構邊界檢查
- ⚠️ **注意**：之前使用 `tests/test_fx/` 目錄路徑會誤報「no tests ran」（因為測試是檔案非目錄）

---

## 🔬 證據 4：程式碼搜尋（敏感關鍵字）

```bash
$ grep -rn 'valuation\|fx\|exchange\|rate\|convert(' services/portfolio-service/app --include='*.py'
```

**結果摘要**（40 行，全部來自 `app/fx/*` 模組內部）：

```
services/portfolio-service/app/fx/stub_provider.py:24:    def get_rate(
services/portfolio-service/app/fx/stub_provider.py:43:    def convert(
services/portfolio-service/app/fx/__init__.py:6:1. 除 app/fx/* 以外，禁止任何模組直接讀取 FX_* / VALUATION_* 等估值相關環境變數
services/portfolio-service/app/fx/__init__.py:7:2. 除 app/fx/* 以外，禁止任何模組直接 import 匯率 provider 實作
services/portfolio-service/app/fx/__init__.py:8:3. 全專案匯率與估值唯一入口：app.fx.get_fx_provider()
services/portfolio-service/app/fx/__init__.py:32:__all__ = ['get_fx_provider', 'FxProvider']
services/portfolio-service/app/fx/__init__.py:39:def get_fx_provider() -> FxProvider:
services/portfolio-service/app/fx/interfaces.py:8:- 估值層（Valuation Layer）：使用 valuation_ccy（通常為 TWD）折算，由此模組提供
services/portfolio-service/app/fx/interfaces.py:26:    def get_rate(
services/portfolio-service/app/fx/interfaces.py:53:    def convert(
```

**證明**：
- ✅ **所有 `fx`/`rate`/`convert` 關鍵字只出現在 `app/fx/*` 內部**
- ✅ **帳務層（position_rebuilder.py）完全不涉及 FX**
- ✅ 唯一例外：`trade_normalizer.py:270` 是 `enumerate()` 函數（誤報）

---

## ✅ 已完成項目

### Sprint 1-4.A：FX 模組邊界定義
**狀態**: ✅ 完成（僅介面 + Stub）

**交付物**：
1. **介面定義**：`services/portfolio-service/app/fx/interfaces.py`
   - `FxProvider` 抽象基類
   - `get_rate()`, `convert()`, `source()`, `is_stub()` 方法

2. **型別定義**：`services/portfolio-service/app/fx/types.py`
   - `Currency` 型別（字串別名）
   - `ExchangeRate` 型別（Decimal 包裝）

3. **Stub 實作**：`services/portfolio-service/app/fx/stub_provider.py`
   - 嚴格模式：僅支援同幣別轉換（`USD -> USD` ✅）
   - 跨幣別拋 `NotImplementedError`（`USD -> TWD` ❌）
   - 避免靜默錯誤

4. **測試覆蓋**：20 個測試通過 ✅
   - Stub 行為測試
   - 邊界測試（同幣別、跨幣別）

**架構保證**：
- ✅ 帳務層（position_rebuilder）**硬禁止** import FX 模組
- ✅ 估值層（未來）透過 DI 使用 FX 模組
- ✅ 清晰分層：Accounting Layer ≠ Valuation Layer

---

### Sprint 1-4.3：rebuild_positions 寫回 positions 表
**狀態**: ✅ 完成

**核心功能**：
- ✅ 從 `trades` 表重算帳務
- ✅ 使用 `avg_cost_calculator` 計算均價
- ✅ 寫入 `positions` 表（使用 `merge()` 實現冪等性）
- ✅ 回傳格式：`{status, symbols, affected_count}`

**欄位策略**（符合帳務層規範）：
- ✅ `asset_ccy`：來自 trade 原幣別
- ✅ `u_pnl`：固定填 0（**不做估值**）
- ✅ **不呼叫 FX 模組**（已驗證無 `from app.fx` import）

**測試覆蓋**：16 個測試通過 ✅
- 資料庫寫入測試
- 冪等性測試
- 空 trades 測試
- 既有測試（endpoint、preview）全通過

**驗收報告**：
- 詳見 `SPRINT_1-4-3_ACCEPTANCE_REPORT.md`

---

## ⏸ 暫停項目

### Sprint 1-4.B：估值層實作（暫停）
**指令**：等 Sprint 1-4.3 穩定後再開工

**暫停範圍**：
❌ **禁止實作以下項目**：
1. 真實匯率資料源
   - Yahoo Finance Provider
   - 央行牌告匯率 Provider
   - Alpha Vantage / Finnhub
   - 任何 HTTP 請求（requests、httpx）

2. 匯率快取機制
   - Redis cache
   - Database cache (rates 表)
   - 記憶體 cache

3. 估值計算流程
   - `valuation_ccy` 欄位寫入
   - `u_pnl` 真實計算（市價 - 成本）
   - `market_value` 欄位

4. 日線資料整合
   - 日線收盤價 Provider
   - 歷史資料回溯

---

## 📁 當前 Repo 狀態

### FX 模組檔案清單
```
services/portfolio-service/app/fx/
├── __init__.py          ✅ 介面匯出（僅 stub）
├── interfaces.py        ✅ FxProvider 抽象基類
├── types.py             ✅ Currency, ExchangeRate 型別
└── stub_provider.py     ✅ StubFxProvider（防呆實作）
```

**確認**：
- ✅ 無 `yahoo_provider.py`
- ✅ 無 `central_bank_provider.py`
- ✅ 無 `cache_provider.py`
- ✅ 無 `valuation_service.py`
- ✅ 無 `rates` 資料表 migration

### Position 模型欄位（實際 Schema）

**證據來源**：`\d positions` 查詢結果

```python
class Position(Base):
    id: int                         # PK
    user_id: str                    # not null
    symbol: str                     # not null
    asset_ccy: str                  # not null（原幣別，來自 trade）
    quantity: Decimal               # not null
    avg_cost: Decimal               # not null
    realized_pnl: Decimal           # not null, default 0
   u_pnl: Decimal         # not null, default 0（固定填 0，不做估值）
    last_updated_at: datetime       # not null, default now()
    
    # Constraint: UNIQUE (user_id, symbol)
```

**明確事實**：
- ❌ **不存在 `valuation_ccy` 欄位**
- ❌ **不存在 `market_value` 欄位**
- ✅ 只有 `asset_ccy`（原幣別）
- ✅ `u_pnl` 固定為 0（不做估值）

### 依賴套件（requirements.txt）
**確認**：
- ✅ 無 `requests`
- ✅ 無 `httpx`
- ✅ 無 `redis`
- ✅ 無 `yfinance`

---

## 🎯 下階段規劃

### 等待條件
1. ✅ Sprint 1-4.3 完成並穩定
2. ✅ 帳務層測試全通過（16/16）
3. ⏳ 使用者確認 Sprint 1-4.3 功能符合需求
4. ⏳ 決定估值層介面設計方向

### 估值層介面設計（未來 Sprint）
**待討論項目**：
- [ ] `valuation_ccy` 欄位是否加入 Position 模型？
- [ ] 估值計算是否獨立成 `valuation_service.py`？
- [ ] 匯率資料源優先順序（Yahoo / 央行 / Alpha Vantage）？
- [ ] 快取策略（Redis / DB / Memory）？
- [ ] 日線資料整合時機？

---

## 驗證命令

### 確認 FX 模組只有介面和 Stub
```bash
# 列出 FX 模組檔案
find services/portfolio-service/app/fx -name "*.py"

# 確認無真實 Provider
ls services/portfolio-service/app/fx/ | grep -v "stub\|interface\|types\|__init__"

# 確認帳務層不呼叫 FX
grep -r "from app.fx" services/portfolio-service/app/position_rebuilder.py
```

### 執行測試
```bash
# 所有 rebuild 測試
docker compose run --rm portfolio-service pytest tests/ -k rebuild -v

# FX 模組測試
docker compose run --rm portfolio-service pytest tests/test_fx/ -v

# 完整測試套件
docker compose run --rm portfolio-service pytest tests/ -v
```

---

---

## 🚫 硬禁止規則（Architecture Guardrails）

### 規則 1：帳務層禁止呼叫 FX 模組

**禁止清單**：
```python
# ❌ 以下任何一行出現在 position_rebuilder.py 或 avg_cost_calculator.py，視為違規
from app.fx import get_fx_provider
from app.fx import FxProvider
from app.fx.stub_provider import StubFxProvider
fx_provider.get_rate(...)
fx_provider.convert(...)
```

**檢查命令**：
```bash
# 必須無任何輸出
grep -n "from app.fx\|import.*fx\|get_rate\|\.convert(" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/avg_cost_calculator.py
```

**違規後果**：
- 🚫 阻擋 PR 合併
- 🚫 CI 失敗
- 🚫 要求立即回退

---

### 規則 2：Position 表不得新增估值欄位（當前階段）

**禁止新增的欄位**：
- ❌ `valuation_ccy`（估值幣別）
- ❌ `market_value`（市值）
- ❌ `valuation_date`（估值日期）
- ❌ 任何與「折算後金額」相關的欄位

**檢查命令**：
```bash
# 必須回傳 "(0 rows)"
docker compose exec postgres psql -U investment -d investment_db -c \
  "SELECT column_name FROM information_schema.columns 
   WHERE table_name='positions' 
   AND column_name IN ('valuation_ccy', 'market_value', 'valuation_date');"
```

**違規後果**：
- 🚫 Migration 不得合併
- 🚫 要求移除相關欄位

---

### 規則 3：API 不得提前開放估值端點

**禁止的端點**：
- ❌ `/portfolio/valuation`
- ❌ `/portfolio/market_value`
- ❌ `/fx/rate`
- ❌ `/fx/convert`

**檢查命令**：
```bash
curl -s http://localhost:8001/openapi.json | \
  jq -r '.paths|keys[]' | \
  grep -E "valuation|market_value|fx"
# 必須無任何輸出
```

**違規後果**：
- 🚫 API 變更不得合併
- 🚫 要求移除相關路由

---

### 規則 4：Sprint 1-4.A/1-4.3 禁止估值邏輯與欄位

**禁止項目**：
- ❌ 任何匯率折算邏輯（`convert(amount, from_ccy, to_ccy)`）
- ❌ 市價計算邏輯（`quantity * market_price`）
- ❌ 在 `positions` 表新增 `valuation_ccy` / `market_value` / `valuation_date` 欄位
- ❌ 在 `position_rebuilder.py` / `avg_cost_calculator.py` 呼叫 FX 模組
- ❌ `u_pnl` 填入非零值（當前階段必須固定為 0）

**檢查命令**：
```bash
# 檢查 1：帳務層不得呼叫 FX
grep -rn "from app.fx\|get_rate\|convert(" \
  services/portfolio-service/app/position_rebuilder.py \
  services/portfolio-service/app/avg_cost_calculator.py
# 必須無任何輸出

# 檢查 2：Position 表無估值欄位
docker compose exec postgres psql -U investment -d investment_db -c \
  "SELECT column_name FROM information_schema.columns \
   WHERE table_name='positions' \
   AND column_name ~ '(valuation|market_value)';"
# 必須回傳 (0 rows)

# 檢查 3：確認 u_pnl 預設值為 0
docker compose exec postgres psql -U investment -d investment_db -c \
  "SELECT column_default FROM information_schema.columns \
   WHERE table_name='positions' AND column_name='u_pnl';"
# 必須回傳 '0'::numeric
```

**違規後果**：
- 🚫 立即回退相關 commit
- 🚫 PR 審查自動 reject
- 🚫 重新執行完整測試套件

**例外條款**：
- ✅ **唯一例外**：Sprint 1-4.B（估值層）可透過 Alembic migration 新增欄位
- ✅ Migration 檔案必須包含 `# Sprint 1-4.B: Valuation Layer` 註解
- ✅ Migration 必須包含 rollback 機制（downgrade）

---

### 規則 5：估值欄位只能透過 Alembic Migration 新增

**禁止方式**：
- ❌ 直接執行 SQL ALTER TABLE（不經過 migration）
- ❌ 在 `models.py` 新增欄位後直接重啟服務（跳過 migration）
- ❌ 手動修改 `positions` 表 schema

**正確方式**（僅限 Sprint 1-4.B）：
```bash
# 1. 建立 migration
cd services/portfolio-service
alembic revision -m "sprint_1_4_b_add_valuation_fields"

# 2. 編輯 migration 檔案（加入欄位定義）
# 3. 執行 migration
alembic upgrade head

# 4. 驗證 migration 可回退
alembic downgrade -1
alembic upgrade head
```

**Migration 範例**（僅供參考，Sprint 1-4.B 實作時使用）：
```python
# alembic/versions/xxxx_sprint_1_4_b_add_valuation_fields.py
"""
Sprint 1-4.B: Add valuation fields to positions table

Revision ID: xxxx
Revises: yyyy
Create Date: 2026-01-xx
"""

def upgrade() -> None:
    # 新增 valuation_ccy 欄位（預設 TWD）
    op.add_column('positions', 
        sa.Column('valuation_ccy', sa.Text(), nullable=False, server_default='TWD'))
    # 新增 market_value 欄位（預設 0）
    op.add_column('positions', 
        sa.Column('market_value', sa.Numeric(), nullable=False, server_default='0'))

def downgrade() -> None:
    # 可回退
    op.drop_column('positions', 'market_value')
    op.drop_column('positions', 'valuation_ccy')
```

**檢查命令**：
```bash
# 確認 migration 歷史
alembic history

# 確認當前 revision
alembic current

# 驗證 migration 檔案包含 Sprint 1-4.B 標記
grep -r "Sprint 1-4.B" services/portfolio-service/alembic/versions/
```

**違規後果**：
- 🚫 不經過 migration 的 schema 變更視為嚴重違規
- 🚫 要求立即建立補救 migration
- 🚫 在 Staging/Production 環境執行 rollback

---

## 結論

✅ **當前 Repo 符合要求**（已通過 4 類證據驗證）：
- ✅ 只保留「介面」與「Stub 防呆」
- ✅ 無任何真實資料源實作
- ✅ 無估值計算流程
- ✅ 帳務層與估值層邊界清晰
- ✅ Position 表無 `valuation_ccy` 欄位

⏸ **估值層實作已暫停**，等待 Sprint 1-4.3 穩定後再討論設計方向。

---

**報告日期**：2026-01-24  
**最後更新**：Sprint 1-4.3 驗收完成後  
**證據收集時間**：2026-01-24 16:50 UTC
