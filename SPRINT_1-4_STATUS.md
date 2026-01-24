# Sprint 1-4 階段狀態報告

## 執行時間
2026-01-24

## 當前狀態：✅ 帳務層完成，估值層暫停

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
- ✅ `unrealized_pnl`：固定填 0（**不做估值**）
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
   - `unrealized_pnl` 真實計算（市價 - 成本）
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

### Position 模型欄位
```python
class Position(Base):
    user_id: str
    symbol: str
    asset_ccy: str          ✅ 原幣別（來自 trade）
    quantity: Decimal
    avg_cost: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal ✅ 固定填 0（不做估值）
    # ❌ 無 valuation_ccy 欄位
    # ❌ 無 market_value 欄位
```

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

## 結論

✅ **當前 Repo 符合要求**：
- ✅ 只保留「介面」與「Stub 防呆」
- ✅ 無任何真實資料源實作
- ✅ 無估值計算流程
- ✅ 帳務層與估值層邊界清晰

⏸ **估值層實作已暫停**，等待 Sprint 1-4.3 穩定後再討論設計方向。

---

**報告日期**：2026-01-24  
**最後更新**：Sprint 1-4.3 驗收完成後
