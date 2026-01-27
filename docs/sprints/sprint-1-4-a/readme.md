# Sprint 1-4.A 完成報告

## 🎯 目標達成

建立資產幣別匯率折算的清晰介面定義（Boundary），避免全域工具函數造成疊床架屋與副作用。

## 📦 交付物

### 1. 核心模組 (`services/portfolio-service/app/fx/`)

```
app/fx/
├── __init__.py          # Factory & Public API（唯一入口）
├── types.py            # 類型定義（Currency, ExchangeRate）
├── interfaces.py       # FxProvider 抽象介面
└── stub_provider.py    # Stub 實作（嚴格模式）
```

### 2. 測試檔案

```
tests/test_fx.py        # 完整單元測試與整合測試
```

### 3. 文檔更新

```
SPRINT_1-4-A_DOCS_PATCH.md  # 文檔補丁（待手動應用到 Development.md 和 Strategy.md）
```

## 🔐 硬禁止規則（Hard Rules）

### ⚠️ 違規將直接退回 PR

1. **禁止**除 `app/fx/*` 以外的任何模組直接讀取 `FX_*` / `VALUATION_*` 環境變數
2. **禁止**除 `app/fx/*` 以外的任何模組直接 import 匯率 provider 實作
3. **必須**使用 `app.fx.get_fx_provider()` 作為唯一入口

### ✅ 正確用法

```python
from app.fx import get_fx_provider
from decimal import Decimal

fx = get_fx_provider()
rate = fx.get_rate('USD', 'TWD')
twd_amount = fx.convert(Decimal('100'), 'USD', 'TWD')
```

### ❌ 錯誤用法

```python
# 錯誤 1：直接讀取環境變數
import os
fx_provider = os.getenv('FX_PROVIDER')

# 錯誤 2：直接 import 實作
from app.fx.stub_provider import StubFxProvider
provider = StubFxProvider()
```

## 🏗️ 架構決策

### 帳務層 vs 估值層

| 層次 | 職責 | 幣別 | 模組 |
|-----|-----|-----|------|
| **帳務層** | 記錄原始交易與持倉 | `asset_ccy` | `trade_normalizer`, `avg_cost_calculator`, `position_rebuilder` |
| **估值層** | 折算為統一計價幣別 | `valuation_ccy` (TWD) | `app.fx.*` (未來 Sprint 2.x) |

**重要**：Sprint 1-4.3 的 `rebuild_positions` 屬於帳務層，不做折算。

## 🧪 驗收命令

### 1. 執行單元測試

```bash
docker compose exec portfolio-service pytest tests/test_fx.py -v
```

預期輸出：
```
test_fx.py::TestStubFxProvider::test_same_currency_get_rate PASSED
test_fx.py::TestStubFxProvider::test_same_currency_convert PASSED
test_fx.py::TestStubFxProvider::test_different_currency_get_rate_raises PASSED
test_fx.py::TestStubFxProvider::test_different_currency_convert_raises PASSED
test_fx.py::TestStubFxProvider::test_source_returns_stub PASSED
test_fx.py::TestStubFxProvider::test_is_stub_returns_true PASSED
test_fx.py::TestFxFactory::test_default_provider_is_stub PASSED
test_fx.py::TestFxFactory::test_singleton_pattern PASSED
test_fx.py::TestFxIntegration::test_full_workflow_same_currency PASSED
test_fx.py::TestFxIntegration::test_full_workflow_cross_currency_fails PASSED
```

### 2. 驗證 API（Python REPL）

```bash
docker compose exec portfolio-service python3 -c "
from app.fx import get_fx_provider
from decimal import Decimal

fx = get_fx_provider()
print(f'Provider: {fx.source()}, is_stub: {fx.is_stub()}')

# 同幣別轉換
result = fx.convert(Decimal('100'), 'USD', 'USD')
print(f'100 USD -> USD = {result}')

# 跨幣別轉換（應失敗）
try:
    fx.convert(Decimal('100'), 'USD', 'TWD')
except NotImplementedError as e:
    print(f'跨幣別轉換失敗（預期）: {str(e)[:50]}...')
"
```

預期輸出：
```
Provider: stub, is_stub: True
100 USD -> USD = 100
跨幣別轉換失敗（預期）: StubFxProvider 不支援跨幣別轉換：100 USD -> T...
```

## 📋 檢查清單

- [x] ✅ 建立 `app/fx/types.py`
- [x] ✅ 建立 `app/fx/interfaces.py`
- [x] ✅ 建立 `app/fx/stub_provider.py`
- [x] ✅ 建立 `app/fx/__init__.py`
- [x] ✅ 建立 `tests/test_fx.py`
- [x] ✅ 建立文檔補丁 `SPRINT_1-4-A_DOCS_PATCH.md`
- [ ] ⏳ 應用補丁到 `Development.md`（需手動操作）
- [ ] ⏳ 應用補丁到 `Strategy.md`（需手動操作）
- [ ] ⏳ 執行驗收命令（需 `docker compose up -d --build`）

## 🚀 下一步

1. **啟動服務並測試**：
   ```bash
   docker compose up -d --build
   docker compose exec portfolio-service pytest tests/test_fx.py -v
   ```

2. **手動更新文檔**：
   - 參考 [SPRINT_1-4-A_DOCS_PATCH.md](SPRINT_1-4-A_DOCS_PATCH.md)
   - 更新 [Development.md](Development.md)
   - 更新 [Strategy.md](Strategy.md)

3. **繼續 Sprint 1-4.3**：
   - 實作 `rebuild_positions` 完整邏輯
   - 使用帳務層原則（不做匯率折算）

## 💡 架構意圖

### 為何不用全域函數？
- ❌ 測試時無法 mock
- ❌ 難以抽換實作
- ❌ 環境變數散落各處
- ✅ 介面清晰、易於擴展

### 為何 Stub 要嚴格模式？
- ❌ 默默用 1:1 估值會造成重大錯誤
- ✅ 明確失敗優於隱式錯誤
- ✅ 強迫開發者處理跨幣別場景

### 為何用單例模式？
- ✅ FX Provider 需要快取匯率
- ✅ 避免重複查詢外部 API
- ✅ 測試時可用 `reset_fx_provider()` 重置

---

**作者**: Tom（首席架構師）  
**日期**: 2026-01-24  
**Sprint**: 1-4.A
