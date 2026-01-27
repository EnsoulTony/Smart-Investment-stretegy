# 賣空錯誤診斷報告
**日期:** 2026-01-25  
**問題:** Tony 的 rebuild_positions 失敗（UUUU 賣空錯誤）

---

## 🔍 問題分析

### 現況
- **錯誤訊息:** `ValueError: 賣出數量 (20) 超過持倉數量 (0)，不允許放空。symbol=UUUU, date=2026-01-22`
- **HTTP 回應:** `200 OK` + `{"status": "failed", "symbols_count": 0}`
- **trades_count:** 70 筆
- **symbols_count:** 50 個

### 核心問題
❌ **Exception 被吞掉，錯誤訊息遺失**

```python
# services/portfolio-service/app/position_rebuilder.py:160-173
except Exception as e:
    logger.exception("持倉重算失敗，user_id=%s, error=%s", user_id, str(e))
    self.session.rollback()  # ✅ Rollback 正確
    return {                 # ❌ 不應該 return，應該 raise
        "status": "failed",
        "user_id": user_id,
        "symbols_count": 0,
        # ...
        "evidence": {
            "positions_columns": []  # ❌ 沒有包含錯誤訊息
        }
    }
```

### 影響
1. **API 回應 HTTP 200** - 呼叫方無法判斷是否成功
2. **錯誤資訊遺失** - Evidence 不包含哪個 symbol 失敗
3. **無法追蹤問題** - 只能從 log 找（不符合「可證偽」原則）

---

## ✅ Transaction 實作正確

### 確認事項
- ✅ **有 try-except 區塊**
- ✅ **Exception 時執行 rollback**
- ✅ **Commit 在最後**
- ✅ **使用 merge() 實現冪等性**

### Transaction 結構
```python
try:
    trades_orm = list_trades_for_user(self.session, user_id)  # ✅ 查詢
    # ... 處理邏輯
    self.session.commit()  # ✅ Commit
except Exception as e:
    self.session.rollback()  # ✅ Rollback
    return {"status": "failed", ...}  # ❌ 應該 raise
```

**結論:** Transaction 實作完全正確，不會有資料不一致問題。

---

## ✅ 排序邏輯正確

### 確認事項
```python
# services/portfolio-service/app/trades_repository.py:61-66
trades = db.query(Trade).filter(
    Trade.user_id == user_id
).order_by(
    Trade.trade_date.asc(),   # ✅ 主要排序：交易日期（升序）
    Trade.created_at.asc()     # ✅ 次要排序：匯入順序（穩定性）
).all()
```

**結論:** 排序邏輯已實作，同日交易順序穩定。

---

## ❌ 問題根源：UUUU 交易資料異常

### 可能原因
1. **Google Sheets 資料錯誤** - 賣出早於買入（或先有賣單）
2. **Sync 邏輯未驗證** - 匯入時未檢查合理性
3. **交易已刪除** - 診斷時 UUUU 記錄已不在 DB（可能被重新 sync 覆蓋）

### 診斷結果
```sql
-- 所有 SQL 查詢都回傳空
SELECT * FROM trades WHERE user_id='tony' AND symbol='UUUU';
-- 0 rows

-- 但 log 顯示錯誤仍在發生
-- 2026-01-25: ValueError: 賣出數量 (20) 超過持倉數量 (0)，symbol=UUUU
```

**推測:** UUUU 交易記錄在某次 sync 後被清除，但 portfolio-service 仍在使用舊的 cache 或連線。

---

## 🔧 建議修復方案

### P0: 立即修復（本次 commit）

#### 1. 改善錯誤回應（不吞掉 Exception）

**檔案:** `services/portfolio-service/app/position_rebuilder.py`  
**行數:** 160-173

**現況（錯誤）:**
```python
except Exception as e:
    logger.exception("持倉重算失敗，user_id=%s, error=%s", user_id, str(e))
    self.session.rollback()
    return {  # ❌ 吞掉錯誤
        "status": "failed",
        "user_id": user_id,
        "symbols_count": 0,
        ...
    }
```

**修復方案 A（推薦）: 在 Evidence 中包含錯誤訊息**
```python
except ValueError as e:  # 更精確的 exception 類型
    logger.exception("持倉重算失敗，user_id=%s, error=%s", user_id, str(e))
    self.session.rollback()
    return {
        "status": "failed",
        "user_id": user_id,
        "symbols_count": 0,
        "upserted_count": 0,
        "deleted_or_zeroed_count": 0,
        "run_id": str(uuid4()),
        "evidence": {
            "error_type": e.__class__.__name__,  # ✅ 新增
            "error_message": str(e),              # ✅ 新增
            "error_symbol": self._extract_symbol_from_error(e),  # ✅ 新增
            "positions_columns": [],
            "verification_sql": {
                "trades_count": f"select count(*) from trades where user_id='{user_id}';",
                "positions_count": f"select count(*) from positions where user_id='{user_id}';"
            }
        }
    }

except Exception as e:  # 其他錯誤
    logger.exception("持倉重算失敗（未預期錯誤），user_id=%s", user_id)
    self.session.rollback()
    raise  # ✅ 非業務錯誤應該 raise
```

**修復方案 B（更激進）: 改回 raise**
```python
except ValueError as e:
    logger.exception("持倉重算失敗，user_id=%s, error=%s", user_id, str(e))
    self.session.rollback()
    raise HTTPException(
        status_code=422,  # Unprocessable Entity
        detail={
            "error": "rebuild_failed",
            "message": str(e),
            "user_id": user_id,
            "verification_sql": {
                "trades": f"select * from trades where user_id='{user_id}' order by trade_date, created_at;"
            }
        }
    )
```

---

#### 2. 新增 Fail Fast 驗證（可選）

**目的:** 在開始 transaction 前就發現問題

```python
def rebuild_positions(self, user_id: str) -> Dict:
    if not user_id or not user_id.strip():
        raise ValueError("user_id 不可為空")
    
    logger.info("開始重算持倉並寫入 positions 表，user_id=%s", user_id)
    
    try:
        trades_orm = list_trades_for_user(self.session, user_id)
        grouped_trades = defaultdict(list)
        
        # 轉換 ORM -> Pydantic
        for trade_orm in trades_orm:
            trade_record = TradeRecord(...)
            grouped_trades[(trade_record.symbol, trade_record.asset_ccy)].append(trade_record)
        
        # ✅ 新增: Fail Fast 驗證（不寫入 DB）
        validation_errors = []
        for (symbol, asset_ccy), trades in grouped_trades.items():
            try:
                compute_avg_cost(trades)  # 只驗證，不使用結果
            except ValueError as e:
                validation_errors.append({
                    "symbol": symbol,
                    "asset_ccy": asset_ccy,
                    "error": str(e),
                    "trades_count": len(trades),
                    "first_trade_date": trades[0].trade_date.isoformat() if trades else None,
                    "last_trade_date": trades[-1].trade_date.isoformat() if trades else None
                })
        
        # ✅ 若有錯誤，立即終止（不進 transaction）
        if validation_errors:
            error_summary = "\n".join([
                f"  • {e['symbol']} ({e['asset_ccy']}): {e['error']}"
                for e in validation_errors
            ])
            raise ValueError(
                f"交易資料驗證失敗，發現 {len(validation_errors)} 個問題標的：\n{error_summary}\n\n"
                f"建議執行：\n"
                f"  docker compose exec -T postgres psql -U postgres -d portfolio -c \\\n"
                f"    \"SELECT trade_date, action, quantity FROM trades WHERE user_id='{user_id}' AND symbol IN ('{validation_errors[0]['symbol']}') ORDER BY trade_date, created_at;\""
            )
        
        # ✅ 驗證通過，開始寫入（原有邏輯）
        for (symbol, asset_ccy), trades in grouped_trades.items():
            state = compute_avg_cost(trades)  # 這次不會失敗
            # ... merge position
        
        self.session.commit()
        # ... return success
        
    except ValueError as e:
        logger.exception("持倉重算失敗（業務錯誤），user_id=%s", user_id)
        self.session.rollback()
        return {
            "status": "failed",
            "user_id": user_id,
            "symbols_count": 0,
            "evidence": {
                "error_type": "ValueError",
                "error_message": str(e),
                "validation_errors": validation_errors if 'validation_errors' in locals() else []
            }
        }
    
    except Exception as e:
        logger.exception("持倉重算失敗（系統錯誤），user_id=%s", user_id)
        self.session.rollback()
        raise  # 系統錯誤應該 raise
```

---

### P1: 資料修復（手動操作）

#### 1. 重啟 portfolio-service（清除可能的 cache）
```bash
docker compose restart portfolio-service
```

#### 2. 重新 sync tony 的資料
```bash
curl -X POST "http://localhost:8001/portfolio/sync?user_id=tony"
```

#### 3. 檢查是否有問題 symbol
```sql
-- 找出「先賣後買」的 symbol
WITH cumulative AS (
    SELECT 
        symbol,
        trade_date,
        action,
        quantity,
        SUM(CASE WHEN action='buy' THEN quantity ELSE -quantity END) 
            OVER (PARTITION BY symbol ORDER BY trade_date, created_at) as running_qty
    FROM trades
    WHERE user_id='tony'
)
SELECT DISTINCT symbol
FROM cumulative
WHERE running_qty < 0
ORDER BY symbol;
```

#### 4. 若找到問題 symbol，檢查 Google Sheets 原始資料
```bash
# 假設找到問題 symbol 是 XXXX
curl "http://localhost:8001/portfolio/trades/summary?user_id=tony&symbol=XXXX" | jq
```

---

### P2: 監控與測試（下週）

#### 1. 新增單元測試
```python
# tests/test_position_rebuilder_short_selling.py

def test_rebuild_should_fail_on_short_selling():
    """測試：賣出超過持倉時應該失敗"""
    # Given: 先賣後買的交易記錄
    trades = [
        Trade(user_id="test", symbol="TEST", action="sell", quantity=10, ...),
        Trade(user_id="test", symbol="TEST", action="buy", quantity=5, ...)
    ]
    
    # When: 執行 rebuild
    result = rebuild_positions("test", db)
    
    # Then: 應該失敗並包含錯誤訊息
    assert result["status"] == "failed"
    assert "error_message" in result["evidence"]
    assert "TEST" in result["evidence"]["error_message"]
```

#### 2. 新增 API 測試
```python
def test_rebuild_api_should_return_422_on_invalid_data():
    """測試：資料異常時應該回傳 422"""
    response = client.post("/portfolio/rebuild_positions?user_id=invalid_user")
    assert response.status_code == 422  # Unprocessable Entity
    assert "error_message" in response.json()
```

---

## 📊 最終確認

### ✅ 已確認正確的部分
1. **Transaction 實作** - 有 commit、rollback、try-except
2. **排序邏輯** - 二級排序已實作（trade_date + created_at）
3. **資料完整性** - Rollback 確保不會有髒資料

### ❌ 需要修復的部分
1. **錯誤回應** - Exception 被吞掉，應該在 Evidence 中包含錯誤訊息
2. **Fail Fast** - 缺少「匯入前驗證」階段
3. **HTTP 狀態碼** - 業務錯誤應該用 422，不是 200

### ⚠️ 需要調查的部分
1. **UUUU 交易記錄** - 為何 SQL 查詢是空的但 log 仍有錯誤？
2. **Google Sheets 資料** - 是否有「先賣後買」的情況？
3. **Sync 邏輯** - 是否需要在匯入時驗證合理性？

---

## 🎯 下一步行動

### 立即執行
1. ✅ 創建此診斷報告
2. ⚠️ 重啟 portfolio-service
3. ⚠️ 重新測試 tony 的 rebuild

### 本週完成
4. ⚠️ 修復錯誤回應（Evidence 包含錯誤訊息）
5. ⚠️ 新增 Fail Fast 驗證
6. ⚠️ 新增單元測試

### 下週規劃
7. ⚠️ 調查 Google Sheets 原始資料
8. ⚠️ 評估 Sync 階段是否需要驗證
9. ⚠️ 改善 API 文件（說明可能的錯誤情況）

---

**結論:**  
✅ Transaction 實作正確，不會有資料不一致問題  
⚠️ 但錯誤處理需要改進，應該在 Evidence 中包含錯誤詳情  
❌ UUUU 問題根源不明，需要進一步調查 Google Sheets 資料
