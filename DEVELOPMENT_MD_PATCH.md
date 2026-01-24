# Development.md 更新補丁

## 插入位置 1：在「## 開發階段與典型工作流」之後插入

在第 13 行（「## Prompt 模板（依階段區分）」之前）插入以下內容：

```markdown
## 硬禁止規則（Hard Guardrails）

以下規則為**硬性限制**，違規 PR 將直接退回，不予合併。所有規則都有對應的自動化測試（Guardrail Tests）確保執行。

### 1. 匯率與估值邊界規則（Sprint 1-4.A）

**唯一入口原則**：
- ✅ **允許**：使用 `from app.fx import get_fx_provider` 取得匯率服務
- ❌ **禁止**：除 `app/fx/*` 以外的任何模組直接讀取 `FX_*` / `VALUATION_*` 等估值相關環境變數
  - 包含但不限於：`os.getenv('FX_PROVIDER')`, `os.environ['VALUATION_CCY']`, `dotenv.load_dotenv()` 後讀取
- ❌ **禁止**：除 `app/fx/*` 以外的任何模組直接 import 匯率 provider 實作
  - 包含：`from app.fx.stub_provider import ...`, `from app.fx.interfaces import ...`

**違規示例**：
```python
# ❌ 錯誤 1：直接讀取環境變數
import os
fx_provider = os.getenv('FX_PROVIDER')
valuation_ccy = os.environ.get('VALUATION_CCY', 'TWD')

# ❌ 錯誤 2：直接 import 實作
from app.fx.stub_provider import StubFxProvider
provider = StubFxProvider()

# ❌ 錯誤 3：繞過工廠函數
from app.fx.interfaces import FxProvider
# 自己實例化 provider...
```

**正確用法**：
```python
# ✅ 正確：使用工廠函數
from app.fx import get_fx_provider
from decimal import Decimal

fx = get_fx_provider()

# 查詢匯率
rate = fx.get_rate('USD', 'TWD')

# 轉換金額
twd_amount = fx.convert(Decimal('100'), 'USD', 'TWD')
```

**架構意圖**：
- **帳務層（Accounting Layer）**：使用 `asset_ccy` 記帳，由資料庫欄位定義，不做折算
- **估值層（Valuation Layer）**：使用 `valuation_ccy`（通常為 TWD）折算，由 `app.fx` 模組提供
- Portfolio Service 的 `rebuild_positions`（Sprint 1-4.3）屬於帳務層，不做折算

**自動化檢查**：
- 測試檔案：`services/portfolio-service/tests/test_fx_guardrails.py`
- 執行命令：`docker compose exec portfolio-service pytest tests/test_fx_guardrails.py -v`
- CI 流程會自動執行此測試，違規時 PR 無法合併

**相關文件**：
- [Strategy.md](Strategy.md)：帳務層 vs 估值層的分層說明
- [SPRINT_1-4-A_README.md](SPRINT_1-4-A_README.md)：FX 模組完整文件

---
```

## 插入位置 2：在第 422 行（Sprint 1-4.2 結尾）之後插入

在「### Sprint 1-5: Portfolio 資料庫 Schema 與 Migration」之前插入以下內容：

```markdown
#### Sprint 1-4.A: 建立匯率折算邊界（FX Provider Interface & Guardrails）

**目標**：建立資產幣別匯率折算的清晰介面定義（Boundary），避免全域工具函數造成疊床架屋與副作用。

**完成條件**：
1. 在 `portfolio-service` 建立 `app/fx/` 模組：
   - `types.py`：定義 `Currency`, `ExchangeRate` 型別
   - `interfaces.py`：定義 `FxProvider` 抽象介面（ABC）
   - `stub_provider.py`：實現嚴格模式 Stub Provider
   - `__init__.py`：提供 `get_fx_provider()` 工廠函數與 `reset_fx_provider()` 測試輔助函數
2. `FxProvider` 介面方法：
   - `get_rate(base_ccy, quote_ccy, asof_date) -> Decimal`
   - `convert(amount, from_ccy, to_ccy, asof_date) -> Decimal`
   - `source() -> str`
   - `is_stub() -> bool`
3. `StubProvider` 嚴格行為（失敗優先原則）：
   - `from_ccy == to_ccy`：回傳原值（正常流程）
   - `from_ccy != to_ccy`：**必須** raise `NotImplementedError`（避免默默估錯）
   - 禁止在無匯率資料時默默回傳 1:1 或原值
4. 工廠函數從環境變數 `FX_PROVIDER=stub` 決定 provider（目前只支援 stub）
5. 規範守門測試（Guardrail Tests）：
   - 自動掃描 `app/` 目錄（排除 `app/fx/`）
   - 檢測違規的環境變數讀取
   - 檢測違規的 import 語句
   - CI 自動執行，違規時 PR 失敗
6. 單元測試覆蓋：
   - StubProvider 行為測試（同幣別 / 跨幣別）
   - Factory 函數測試（單例模式 / 環境變數控制）
   - 整合測試（完整工作流程）
   - Guardrail 有效性測試（確認守門員能擋下違規）

**輸出檔案**：
```bash
# 核心模組
services/portfolio-service/app/fx/__init__.py
services/portfolio-service/app/fx/types.py
services/portfolio-service/app/fx/interfaces.py
services/portfolio-service/app/fx/stub_provider.py

# 測試檔案
services/portfolio-service/tests/test_fx.py
services/portfolio-service/tests/test_fx_guardrails.py

# 文件
SPRINT_1-4-A_README.md（完整文件）
SPRINT_1-4-A_DOCS_PATCH.md（變更記錄）
```

**驗收命令**（容器內路徑）：
```bash
# 0. 啟動服務
docker compose up -d --build

# 1. 執行 FX 模組單元測試
docker compose exec portfolio-service pytest tests/test_fx.py -v

# 2. 執行規範守門測試（Guardrail Tests）
docker compose exec portfolio-service pytest tests/test_fx_guardrails.py -v

# 3. 驗證 API（Python REPL）
docker compose exec portfolio-service python3 -c "
from app.fx import get_fx_provider
from decimal import Decimal

fx = get_fx_provider()
print(f'✅ Provider: {fx.source()}, is_stub: {fx.is_stub()}')

# 同幣別轉換
result = fx.convert(Decimal('100'), 'USD', 'USD')
print(f'✅ 100 USD -> USD = {result}')

# 跨幣別轉換（應失敗）
try:
    fx.convert(Decimal('100'), 'USD', 'TWD')
    print('❌ 錯誤：應該拋出 NotImplementedError')
except NotImplementedError as e:
    print(f'✅ 跨幣別轉換正確失敗（預期行為）')
"

# 4. 執行所有 portfolio-service 測試
docker compose exec portfolio-service pytest tests/ -v
```

**預期測試結果**：
```
tests/test_fx.py::TestStubFxProvider::test_same_currency_get_rate PASSED
tests/test_fx.py::TestStubFxProvider::test_same_currency_convert PASSED
tests/test_fx.py::TestStubFxProvider::test_different_currency_get_rate_raises PASSED
tests/test_fx.py::TestStubFxProvider::test_different_currency_convert_raises PASSED
tests/test_fx.py::TestFxFactory::test_default_provider_is_stub PASSED
tests/test_fx.py::TestFxFactory::test_singleton_pattern PASSED
tests/test_fx.py::TestFxIntegration::test_full_workflow_same_currency PASSED
tests/test_fx.py::TestFxIntegration::test_full_workflow_cross_currency_fails PASSED

tests/test_fx_guardrails.py::TestFxGuardrails::test_no_direct_fx_env_access_outside_fx_module PASSED
tests/test_fx_guardrails.py::TestFxGuardrails::test_no_direct_provider_import_outside_fx_module PASSED
tests/test_fx_guardrails.py::TestFxGuardrails::test_fx_module_exists_and_has_public_api PASSED
tests/test_fx_guardrails.py::TestGuardrailEffectiveness::test_guardrail_can_detect_env_access_violation PASSED
tests/test_fx_guardrails.py::TestGuardrailEffectiveness::test_guardrail_can_detect_import_violation PASSED
tests/test_fx_guardrails.py::TestGuardrailEffectiveness::test_guardrail_allows_correct_usage PASSED
```

**架構決策記錄（ADR）**：

1. **為何不用全域工具函數？**
   - ❌ 測試時無法 mock，造成測試困難
   - ❌ 難以抽換實作，擴展性差
   - ❌ 環境變數散落各處，難以追蹤與管理
   - ✅ 介面清晰、易於測試、易於擴展

2. **為何 Stub 要嚴格模式（失敗優先）？**
   - ❌ 默默用 1:1 估值會造成重大財務錯誤（例如 100 USD 被當 100 TWD）
   - ✅ 明確失敗優於隱式錯誤（Fail-fast principle）
   - ✅ 強迫開發者明確處理跨幣別場景
   - ✅ 避免「先跑再說」的技術債累積

3. **為何用單例模式？**
   - ✅ FX Provider 通常需要快取匯率資料
   - ✅ 避免重複查詢外部 API（節省成本與時間）
   - ✅ 測試時可用 `reset_fx_provider()` 重置狀態
   - ✅ 符合 Domain Service 的典型模式

4. **為何需要 Guardrail Tests？**
   - ❌ 文件規範容易被忽略或遺忘
   - ✅ 自動化測試強制執行邊界規範
   - ✅ CI 流程確保違規無法合併
   - ✅ 降低 Code Review 負擔（機器自動檢查）

**相關文件**：
- [Strategy.md](Strategy.md)：帳務層 vs 估值層的分層說明與職責切分
- [SPRINT_1-4-A_README.md](SPRINT_1-4-A_README.md)：完整的 Sprint 1-4.A 文件與驗收報告
- [API_CONTRACTS.md](API_CONTRACTS.md)：未來 valuation 端點的契約定義（Sprint 2.x）

**下階段預告（Sprint 1-4.3）**：
- 實作 `rebuild_positions` 完整邏輯（帳務層）
- 使用 `asset_ccy` 記帳，不做匯率折算
- 為未來的估值層預留介面

---
```
