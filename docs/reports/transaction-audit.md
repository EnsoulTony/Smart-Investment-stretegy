# Transaction 稽核報告
**稽核日期:** 2026-01-25  
**稽核範圍:** portfolio-service 資料庫交易與排序邏輯

---

## 📊 稽核結果總覽

| 項目 | 狀態 | 說明 |
|------|------|------|
| Transaction 實作 | ✅ **正確** | 有完整 try-commit-except-rollback |
| 交易排序（主要） | ✅ **正確** | `trade_date.asc()` 升序 |
| 交易排序（次要） | ❌ **缺少** | 缺少 `created_at.asc()` 二級排序 |
| 賣空檢查 | ⚠️ **部分** | compute_avg_cost 有檢查，但錯誤發生時機太晚 |
| 資料驗證 | ❌ **不足** | 缺少「匯入前驗證」階段 |

---

## ✅ Transaction 實作正確

### 程式碼位置
- **檔案:** `services/portfolio-service/app/position_rebuilder.py`
- **函式:** `PositionRebuilder.rebuild_positions()`
- **行數:** 89-165

### Transaction 結構
```python
try:
    # 1. 查詢所有交易
    trades_orm = list_trades_for_user(self.session, user_id)
    
    # 2. 分組並計算
    grouped_trades = defaultdict(list)
    for trade_orm in trades_orm:
        trade_record = TradeRecord(...)
        grouped_trades[(symbol, asset_ccy)].append(trade_record)
    
    # 3. 計算均價並寫入 positions
    for (symbol, asset_ccy), trades in grouped_trades.items():
        state = compute_avg_cost(trades)  # 👈 這裡會拋出 ValueError
        # ... merge position
    
    # 4. Commit
    self.session.commit()  # ✅ 正確
    
except Exception as e:
    self.session.rollback()  # ✅ 正確
    logger.error("持倉重算失敗，user_id=%s, error=%s", user_id, e)
    raise
```

### ✅ 優點
1. **完整的 try-except-rollback 結構**
2. **Commit 在最後，確保原子性**
3. **Exception 會觸發 rollback，不會留下髒資料**
4. **使用 session.merge() 實現冪等性**

---

## ❌ 問題 1: 缺少二級排序

### 現況
**檔案:** `services/portfolio-service/app/trades_repository.py`  
**函式:** `list_trades_for_user()`

```python
def list_trades_for_user(db: Session, user_id: str) -> List[Trade]:
    """查詢指定用戶的所有交易記錄（按時間排序）。
    
    排序規則：
    1. 主要排序：trade_date ASC（交易日期由舊到新）
    2. 次要排序：created_at ASC（同日多筆時，按匯入順序）  👈 文件有寫
    """
    return (
        db.query(Trade)
        .filter(Trade.user_id == user_id)
        .order_by(Trade.trade_date.asc())  # ❌ 缺少 created_at.asc()
        .all()
    )
```

### 問題影響
**同日多筆交易順序不穩定**，可能導致：
1. **先賣後買 vs 先買後賣** - 影響已實現損益計算
2. **資料庫回傳順序變動** - 重複執行結果不一致
3. **觸發 ValueError** - 若先處理賣單，可能出現「賣出數量超過持倉」錯誤

### 修復方案
```python
return (
    db.query(Trade)
    .filter(Trade.user_id == user_id)
    .order_by(
        Trade.trade_date.asc(),
        Trade.created_at.asc()  # ✅ 新增二級排序
    )
    .all()
)
```

---

## ⚠️ 問題 2: 錯誤檢測時機太晚

### 現況
**賣空檢查在 `compute_avg_cost()` 內部**

```python
# position_rebuilder.py
for (symbol, asset_ccy), trades in grouped_trades.items():
    state = compute_avg_cost(trades)  # 👈 這裡才檢查，已經在 transaction 內
    # ...
```

**問題:**
- 當第 50 個 symbol 出現賣空錯誤時，**前 49 個 symbol 的計算已完成**
- 雖然會 rollback，但**效能浪費**（已處理大量資料）
- **錯誤訊息不夠明確**（使用者不知道是第幾筆交易有問題）

### 建議改進
**新增「匯入前驗證」階段：**

```python
def rebuild_positions(self, user_id: str) -> Dict:
    try:
        trades_orm = list_trades_for_user(self.session, user_id)
        
        # ✅ 階段 1: 快速驗證（不寫入 DB）
        validation_errors = []
        grouped_trades = defaultdict(list)
        
        for trade_orm in trades_orm:
            trade_record = TradeRecord(...)
            grouped_trades[(symbol, asset_ccy)].append(trade_record)
        
        # ✅ 階段 2: 預先檢查所有 symbol
        for (symbol, asset_ccy), trades in grouped_trades.items():
            try:
                compute_avg_cost(trades)  # 只檢查，不使用結果
            except ValueError as e:
                validation_errors.append({
                    "symbol": symbol,
                    "asset_ccy": asset_ccy,
                    "error": str(e),
                    "trades_count": len(trades)
                })
        
        # ✅ 階段 3: 若有錯誤，直接失敗（不進 transaction）
        if validation_errors:
            raise ValueError(
                f"交易資料驗證失敗，發現 {len(validation_errors)} 個問題：\n" +
                "\n".join([f"  - {e['symbol']}: {e['error']}" for e in validation_errors])
            )
        
        # ✅ 階段 4: 驗證通過，開始寫入（原有邏輯）
        for (symbol, asset_ccy), trades in grouped_trades.items():
            state = compute_avg_cost(trades)  # 這次不會失敗
            # ... merge position
        
        self.session.commit()
        
    except Exception as e:
        self.session.rollback()
        raise
```

### 優點
1. **快速失敗 (Fail Fast)** - 發現問題立即終止
2. **完整錯誤報告** - 一次列出所有問題 symbol
3. **節省資源** - 不浪費 DB transaction
4. **更好的除錯體驗** - 使用者知道哪些 symbol 有問題

---

## ⚠️ 問題 3: Tony 的「UUUU 賣空錯誤」

### 錯誤訊息
```
ValueError: 賣出數量 (20) 超過持倉數量 (0)，不允許放空。
symbol=UUUU, date=2026-01-22 00:00:00+00:00
```

### 可能原因
1. **缺少二級排序** → 同日交易順序錯誤（先處理賣單）
2. **交易資料有誤** → Google Sheets 本身就有問題（賣出早於買入）
3. **sync 邏輯問題** → 資料匯入時未驗證合理性

### 除錯步驟
```sql
-- 1. 檢查 tony 的 UUUU 交易記錄
SELECT trade_date, action, quantity, price, created_at
FROM trades
WHERE user_id='tony' AND symbol='UUUU'
ORDER BY trade_date ASC, created_at ASC;

-- 2. 檢查是否有「賣出早於買入」的情況
WITH cumulative AS (
    SELECT 
        trade_date,
        action,
        quantity,
        SUM(CASE WHEN action='buy' THEN quantity ELSE -quantity END) 
            OVER (ORDER BY trade_date, created_at) as running_qty
    FROM trades
    WHERE user_id='tony' AND symbol='UUUU'
)
SELECT * FROM cumulative
WHERE running_qty < 0;  -- 找出「賣超」的點

-- 3. 檢查同日多筆交易的順序
SELECT trade_date, COUNT(*) as count, 
       STRING_AGG(action || ':' || quantity, ', ') as trades
FROM trades
WHERE user_id='tony' AND symbol='UUUU'
GROUP BY trade_date
HAVING COUNT(*) > 1;
```

---

## 🔧 修復計畫

### 優先級 P0（立即修復）
1. ✅ **新增二級排序** - `order_by(trade_date.asc(), created_at.asc())`
   - **檔案:** `trades_repository.py:list_trades_for_user()`
   - **影響範圍:** 所有 rebuild_positions 呼叫
   - **風險:** 低（純查詢邏輯，不影響寫入）

### 優先級 P1（本週完成）
2. ⚠️ **新增匯入前驗證** - Fail Fast 機制
   - **檔案:** `position_rebuilder.py:rebuild_positions()`
   - **影響範圍:** rebuild_positions API
   - **風險:** 中（變更核心邏輯，需要測試）

3. 🔍 **除錯 tony 的資料** - 找出 UUUU 問題根源
   - 執行上述 SQL 診斷
   - 確認是否為 Google Sheets 資料錯誤
   - 若是資料問題，需要在 sync 階段加驗證

### 優先級 P2（下週規劃）
4. 📝 **新增單元測試** - 覆蓋邊界情況
   - 測試同日多筆交易（先買後賣 vs 先賣後買）
   - 測試賣空情況
   - 測試 transaction rollback

---

## 📋 Transaction 最佳實踐檢查表

| 項目 | 狀態 | 說明 |
|------|------|------|
| ✅ 使用 try-except | 通過 | 有完整結構 |
| ✅ Exception 時 rollback | 通過 | 確保不留髒資料 |
| ✅ Commit 在最後 | 通過 | 確保原子性 |
| ✅ 使用 merge() 實現冪等性 | 通過 | 重複執行結果一致 |
| ❌ 資料驗證在 transaction 前 | 不通過 | 建議新增 Fail Fast |
| ❌ 完整的錯誤報告 | 不通過 | 只報第一個錯誤 |
| ⚠️ 排序邏輯完整 | 部分通過 | 缺少二級排序 |

---

## 🎯 結論

### 好消息 ✅
- **Transaction 實作完全正確** - 有 commit、rollback、try-except
- **不會有資料不一致問題** - rollback 確保 ACID 特性
- **已有基本的資料完整性保護**

### 需要改進 ⚠️
1. **新增二級排序** - 確保同日交易順序穩定
2. **新增 Fail Fast 驗證** - 提早發現資料問題
3. **改善錯誤訊息** - 一次列出所有問題

### 下一步
- 我會立即修復「缺少二級排序」問題
- 然後除錯 tony 的 UUUU 資料
- 最後實作 Fail Fast 驗證機制

---

**稽核人員:** GitHub Copilot  
**稽核結論:** Transaction 實作正確 ✅，但排序邏輯需要補強 ⚠️
