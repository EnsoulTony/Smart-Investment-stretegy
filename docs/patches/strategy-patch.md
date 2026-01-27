# Strategy.md 更新補丁

## 插入位置：在「### Portfolio Service 職責」段落之後插入

建議在第 7 行之後（Portfolio Service 職責說明之後）插入以下內容：

```markdown
### 帳務層 vs 估值層（Accounting vs Valuation Layer）

Portfolio Service 在架構上區分兩個清晰的層次，確保職責單一與資料一致性：

#### 1. 帳務層（Accounting Layer）
**職責**：記錄交易與持倉的**原始幣別**資訊，保留交易事實

- **資料來源**：Google Sheets 交易流水帳
- **記帳單位**：`asset_ccy`（資產幣別，如 USD, TWD, EUR, JPY）
- **核心邏輯**：
  - 交易正規化（`trade_normalizer.py`）：統一資料格式
  - 均價法計算（`avg_cost_calculator.py`）：計算加權平均成本
  - 持倉重算（`position_rebuilder.py`）：從交易流水重建持倉 - **Sprint 1-4.3**
- **資料表**：
  - `trades`：交易流水帳（原始交易記錄）
  - `positions`：持倉快照（按 user_id + symbol + asset_ccy）
- **API 端點**：
  - `POST /portfolio/sync`：同步 Google Sheets 交易到資料庫
  - `POST /portfolio/rebuild`：重算持倉（從 trades 重建 positions）

**核心原則**：
- ✅ 所有金額以原始幣別記錄（`quantity`, `avg_cost`, `total_cost` 等）
- ✅ 資料庫保留原始交易事實，不受匯率波動影響
- ✅ 支援多幣別持倉（同一 symbol 可以有多個幣別的持倉）
- ❌ **不在此層引入 `valuation_ccy` 或匯率轉換**
- ❌ **不在此層做貨幣折算或總覽計算**

**資料範例**：
```python
# positions 表範例（帳務層）
[
    {
        "user_id": "user123",
        "symbol": "AAPL",
        "asset_ccy": "USD",
        "quantity": 100,
        "avg_cost": 150.00,
        "total_cost": 15000.00
    },
    {
        "user_id": "user123",
        "symbol": "2330",
        "asset_ccy": "TWD",
        "quantity": 1000,
        "avg_cost": 500.00,
        "total_cost": 500000.00
    },
]
```

#### 2. 估值層（Valuation Layer）
**職責**：將不同幣別的持倉**折算**為統一計價幣別（通常為 TWD），提供總覽視圖

- **資料來源**：帳務層的持倉資料 + 匯率服務（`app.fx`）
- **計價單位**：`valuation_ccy`（估值幣別，通常為 TWD）
- **核心邏輯**：
  - 匯率查詢（`app/fx/interfaces.py`）：查詢 asset_ccy -> valuation_ccy 匯率 - **Sprint 1-4.A**
  - 幣別轉換（`FxProvider.convert`）：將金額轉換為統一幣別
  - 總覽計算（`valuation_service.py`）：計算總資產價值 - **未來 Sprint 2.x**
- **資料表**：
  - `portfolio_snapshots`：估值快照（未來，用於歷史回顧）
- **API 端點**：
  - `GET /portfolio/valuation`：取得以 TWD 計價的總覽 - **未來 Sprint 2.x**
  - `GET /portfolio/valuation?ccy=USD`：取得以其他幣別計價的總覽 - **未來 Sprint 2.x**

**核心原則**：
- ✅ 使用 `app.fx.get_fx_provider()` 作為唯一匯率入口（**硬禁止規則**）
- ✅ 明確區分估值日期（`asof_date`），支援歷史回顧
- ✅ 每次查詢都即時計算，使用最新匯率
- ❌ **不在資料庫直接存折算後金額**（避免匯率過時問題）
- ❌ **不允許繞過 `app.fx` 直接讀取 `FX_*` 環境變數**

**估值範例**：
```python
# 估值層計算（未來 Sprint 2.x）
from app.fx import get_fx_provider
from decimal import Decimal

fx = get_fx_provider()

# 從帳務層取得持倉
positions = [
    {"symbol": "AAPL", "quantity": 100, "avg_cost": 150.00, "asset_ccy": "USD"},
    {"symbol": "2330", "quantity": 1000, "avg_cost": 500.00, "asset_ccy": "TWD"},
]

# 折算為 TWD
total_value_twd = Decimal('0')
for pos in positions:
    value_in_asset_ccy = Decimal(str(pos['quantity'])) * Decimal(str(pos['avg_cost']))
    
    if pos['asset_ccy'] == 'TWD':
        value_twd = value_in_asset_ccy
    else:
        # 使用 FX Provider 折算
        value_twd = fx.convert(
            amount=value_in_asset_ccy,
            from_ccy=pos['asset_ccy'],
            to_ccy='TWD'
        )
    
    total_value_twd += value_twd

print(f"總資產估值（TWD）: {total_value_twd}")
```

#### 為何要分層？

1. **資料一致性**：
   - 帳務層保留交易事實，不受匯率波動影響
   - 即使匯率服務掛掉，交易記錄依然完整可用
   - 避免「資料庫裡的 TWD 金額是用哪天的匯率算的？」問題

2. **可回溯性**：
   - 任何時間點都能用當時的匯率重新估值
   - 支援「如果用昨天的匯率，我的總資產是多少？」查詢
   - 支援回測與績效分析

3. **測試可行性**：
   - 帳務層不依賴外部匯率 API，測試更穩定
   - 估值層可以 mock FX Provider，獨立測試估值邏輯
   - Guardrail Tests 確保邊界不被破壞

4. **職責單一**：
   - 持倉重算專注於交易邏輯（買賣、成本計算）
   - 估值專注於匯率轉換與總覽呈現
   - 未來可以獨立更換匯率資料來源（Yahoo, 央行, Bloomberg 等）

5. **效能最佳化**：
   - 帳務層寫入快速（無需查詢外部 API）
   - 估值層可以做快取（同一時間的匯率可以重用）
   - 可以獨立擴展（帳務層與估值層獨立水平擴展）

#### 邊界執行（Boundary Enforcement）

**硬禁止規則**（Development.md 詳細說明）：
- ❌ 除 `app/fx/*` 外，禁止直接讀取 `FX_*` / `VALUATION_*` 環境變數
- ❌ 除 `app/fx/*` 外，禁止直接 import provider 實作
- ✅ 必須使用 `app.fx.get_fx_provider()` 作為唯一入口

**自動化檢查**：
- `tests/test_fx_guardrails.py`：自動掃描所有檔案，檢測違規
- CI 流程自動執行，違規時 PR 無法合併

**當前狀態**（Sprint 1-4.A 完成）：
- ✅ 帳務層完整實作（Sprint 1-1 ~ 1-4.3）
- ✅ FX 模組邊界建立（Sprint 1-4.A）
- ⏳ 估值層介面定義（Sprint 2.x 規劃中）

---
```

## 建議插入位置

在 Strategy.md 的「### Portfolio Service 職責」段落之後，「## Radar v1.4 MVP 規則」之前插入上述內容。

這樣可以確保：
1. Portfolio Service 的完整職責說明在同一區域
2. 帳務層 vs 估值層的架構決策有明確文件
3. 與 Development.md 的硬禁止規則互相呼應
