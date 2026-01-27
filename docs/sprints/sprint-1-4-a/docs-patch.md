# Sprint 1-4.A 文檔補丁

此檔案包含需要添加到 Development.md 和 Strategy.md 的內容。

## 一、Development.md 新增內容

### 1. 在「## 開發階段與典型工作流」之後插入「## 硬禁止規則（Hard Rules）」

```markdown
## 硬禁止規則（Hard Rules）

以下規則為**硬性限制**，違規 PR 將直接退回，不予合併：

### 1. 匯率與估值邊界規則（Sprint 1-4.A）

**唯一入口原則**：
- ✅ **允許**：使用 `from app.fx import get_fx_provider` 取得匯率服務
- ❌ **禁止**：除 `app/fx/*` 以外的任何模組直接讀取 `FX_*` / `VALUATION_*` 等估值相關環境變數（`os.getenv` / `os.environ`）
- ❌ **禁止**：除 `app/fx/*` 以外的任何模組直接 import 匯率 provider 實作（如 `from app.fx.stub_provider import StubFxProvider`）

**違規示例**：
```python
# ❌ 錯誤：直接讀取環境變數
fx_provider = os.getenv('FX_PROVIDER')

# ❌ 錯誤：直接 import 實作
from app.fx.stub_provider import StubFxProvider
provider = StubFxProvider()

# ✅ 正確：使用工廠函數
from app.fx import get_fx_provider
fx = get_fx_provider()
rate = fx.get_rate('USD', 'TWD')
```

**架構意圖**：
- 帳務層（Accounting Layer）：使用 `asset_ccy` 記帳，由資料庫欄位定義
- 估值層（Valuation Layer）：使用 `valuation_ccy`（通常為 TWD）折算，由 `app.fx` 模組提供
- Portfolio Service 的 `rebuild_positions` 屬於帳務層，不做折算（Sprint 1-4.3）

---
```

### 2. 在 Sprint 1-4.2 之後插入「Sprint 1-4.A」

```markdown
#### Sprint 1-4.A: 建立匯率折算邊界（FX Provider Interface）

**目標**：建立資產幣別匯率折算的清晰介面定義（Boundary），避免全域工具函數造成疊床架屋與副作用。

**完成條件**：
- 在 `portfolio-service` 建立 `app/fx/` 模組：
  - `types.py`：定義 `Currency`, `ExchangeRate` 型別
  - `interfaces.py`：定義 `FxProvider` 抽象介面（ABC）
  - `stub_provider.py`：實現嚴格模式 Stub Provider
  - `__init__.py`：提供 `get_fx_provider()` 工廠函數
- `FxProvider` 介面方法：
  - `get_rate(base_ccy, quote_ccy, asof_date) -> Decimal`
  - `convert(amount, from_ccy, to_ccy, asof_date) -> Decimal`
  - `source() -> str`
  - `is_stub() -> bool`
- `StubProvider` 嚴格行為：
  - `from_ccy == to_ccy`：回傳原值
  - `from_ccy != to_ccy`：raise `NotImplementedError`（避免默默估錯）
- 工廠函數從環境變數 `FX_PROVIDER=stub` 決定 provider（目前只支援 stub）
- 測試覆蓋：
  - 同幣別 convert 正常
  - 跨幣別 convert 拋出 NotImplementedError
  - 工廠函數單例模式

**輸出檔案**：
```bash
services/portfolio-service/app/fx/types.py
services/portfolio-service/app/fx/interfaces.py
services/portfolio-service/app/fx/stub_provider.py
services/portfolio-service/app/fx/__init__.py
services/portfolio-service/tests/test_fx.py
```

**驗收命令**：
```bash
# 1. 執行單元測試
docker compose exec portfolio-service pytest tests/test_fx.py -v

# 2. 驗證 API（Python REPL）
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
    print(f'跨幣別轉換失敗（預期）: {e}')
"
```

**架構決策記錄**：
1. **為何不用全域函數**：避免測試時無法 mock、難以抽換實作、環境變數散落各處
2. **為何 Stub 要嚴格模式**：明確失敗優於隱式錯誤，避免在無真實匯率時默默用 1:1 估值
3. **為何用單例**：FX Provider 通常需要快取匯率，避免重複查詢外部 API

**相關文件**：
- [Strategy.md](Strategy.md)：帳務層 vs 估值層的分層說明
- [API_CONTRACTS.md](API_CONTRACTS.md)：未來 valuation 端點的契約定義（Sprint 2.x）

---
```

## 二、Strategy.md 新增內容

### 在「Portfolio Service」章節中插入「帳務層 vs 估值層」

```markdown
### 帳務層 vs 估值層（Accounting vs Valuation Layer）

Portfolio Service 在架構上區分兩個清晰的層次：

#### 1. 帳務層（Accounting Layer）
**職責**：記錄交易與持倉的**原始幣別**資訊
- **資料來源**：Google Sheets 交易流水帳
- **記帳單位**：`asset_ccy`（資產幣別，如 USD, TWD, EUR）
- **核心邏輯**：
  - 交易正規化（`trade_normalizer.py`）
  - 均價法計算（`avg_cost_calculator.py`）
  - 持倉重算（`position_rebuilder.py`）- Sprint 1-4.3
- **資料表**：`trades`, `positions`
- **API 端點**：
  - `POST /portfolio/sync`：同步交易
  - `POST /portfolio/rebuild`：重算持倉

**原則**：
- ✅ 所有金額以原始幣別記錄（`quantity`, `avg_cost`, `total_cost` 等）
- ✅ 資料庫保留原始交易事實，不做匯率折算
- ❌ 不在此層引入 `valuation_ccy` 或匯率轉換

#### 2. 估值層（Valuation Layer）
**職責**：將不同幣別的持倉**折算**為統一計價幣別（通常為 TWD）
- **資料來源**：帳務層的持倉資料 + 匯率服務
- **計價單位**：`valuation_ccy`（估值幣別，通常為 TWD）
- **核心邏輯**：
  - 匯率查詢（`app/fx/interfaces.py`）- Sprint 1-4.A
  - 幣別轉換（`FxProvider.convert`）
  - 總覽計算（未來 Sprint 2.x）
- **資料表**：`portfolio_snapshots`（未來）
- **API 端點**：
  - `GET /portfolio/valuation`（未來 Sprint 2.x）

**原則**：
- ✅ 使用 `app.fx.get_fx_provider()` 取得匯率
- ✅ 明確區分估值日期（`asof_date`）
- ❌ 不在資料庫直接存折算後金額（避免匯率過時）

#### 邊界範例

```python
# ✅ 帳務層（Sprint 1-4.3）
# 持倉重算：只計算原始幣別的持倉
positions = rebuild_positions(user_id="user123")
# positions = [
#   {"symbol": "AAPL", "quantity": 100, "avg_cost": 150.00, "asset_ccy": "USD"},
#   {"symbol": "2330", "quantity": 1000, "avg_cost": 500.00, "asset_ccy": "TWD"},
# ]

# ✅ 估值層（未來 Sprint 2.x）
# 總覽估值：將所有持倉折算為 TWD
from app.fx import get_fx_provider
fx = get_fx_provider()

total_value_twd = 0
for pos in positions:
    if pos['asset_ccy'] == 'TWD':
        value_twd = pos['quantity'] * pos['avg_cost']
    else:
        # 使用 FX Provider 折算
        value_in_asset_ccy = pos['quantity'] * pos['avg_cost']
        value_twd = fx.convert(
            Decimal(str(value_in_asset_ccy)),
            from_ccy=pos['asset_ccy'],
            to_ccy='TWD'
        )
    total_value_twd += value_twd
```

#### 為何要分層？

1. **資料一致性**：帳務層保留交易事實，不受匯率波動影響
2. **可回溯性**：任何時間點都能用當時的匯率重新估值
3. **測試可行性**：帳務層不依賴外部匯率 API，測試更穩定
4. **職責單一**：持倉重算專注於交易邏輯，估值專注於匯率轉換

---
```

## 三、驗收檢查清單

- [ ] `app/fx/` 模組所有檔案已建立
- [ ] 測試檔案 `tests/test_fx.py` 已建立並通過
- [ ] Development.md 已更新（硬禁止規則 + Sprint 1-4.A）
- [ ] Strategy.md 已更新（帳務層 vs 估值層）
- [ ] Docker compose 可正常啟動
- [ ] 測試命令可成功執行
- [ ] 文檔語意清晰，架構決策有記錄
