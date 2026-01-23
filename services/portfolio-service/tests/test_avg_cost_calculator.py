"""測試均價法計算器（Weighted Average Cost Calculator）。

測試範圍：
- BUY 交易的均價計算
- SELL 交易的已實現損益計算
- 手續費對成本與損益的影響
- 持倉歸零後的狀態重設
- 防禦性檢查（賣出超過持倉、負數輸入）

測試策略：
- 使用 Decimal 進行精確斷言（避免浮點誤差）
- 每個測試案例獨立，使用 fixture 建立測試資料
- 測試資料使用真實的 TradeRecord 物件（確保與現有模型一致）
"""

import pytest
from decimal import Decimal
from datetime import datetime

from app.schemas import TradeRecord
from app.avg_cost_calculator import compute_avg_cost, AvgCostState


@pytest.fixture
def base_trade_kwargs():
    """基礎交易記錄參數（可覆蓋）。"""
    return {
        "user_id": "test_user",
        "symbol": "AAPL",
        "asset_ccy": "USD",
        "trade_date": datetime(2026, 1, 1, 9, 30, 0),
        "broker": "IB"
    }


class TestAvgCostCalculatorBasic:
    """基礎場景測試：單筆交易與簡單組合。"""
    
    def test_single_buy_calculates_avg_cost_correctly(self, base_trade_kwargs):
        """測試 1：單筆 BUY 交易。
        
        驗證：
        - 持倉數量 = 買入數量
        - 平均成本 = (買入價格 * 數量 + 手續費) / 數量
        - 已實現損益 = 0（尚未賣出）
        """
        trades = [
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                fee=Decimal("1.50")
            )
        ]
        
        state = compute_avg_cost(trades)
        
        # 持倉數量正確
        assert state.qty == Decimal("100"), "持倉數量應為 100"
        
        # 平均成本 = (100 * 150.00 + 1.50) / 100 = 15001.50 / 100 = 150.015
        expected_avg_cost = Decimal("150.015")
        assert state.avg_cost == expected_avg_cost, f"平均成本應為 {expected_avg_cost}"
        
        # 尚未賣出，已實現損益為 0
        assert state.realized_pnl == Decimal("0"), "尚未賣出，已實現損益應為 0"
        
        # 累計手續費
        assert state.total_fee == Decimal("1.50"), "累計手續費應為 1.50"
    
    def test_two_buys_different_prices_calculates_weighted_avg(self, base_trade_kwargs):
        """測試 2：兩筆 BUY 交易（不同價格）。
        
        驗證加權平均成本計算：
        - 第一筆：100 股 @ 150 元（含手續費 1.5）
        - 第二筆：50 股 @ 180 元（含手續費 0.9）
        - 均價 = (100*150 + 1.5 + 50*180 + 0.9) / 150
        """
        trades = [
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                fee=Decimal("1.50")
            ),
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("50"),
                price=Decimal("180.00"),
                fee=Decimal("0.90")
            )
        ]
        
        state = compute_avg_cost(trades)
        
        # 持倉數量 = 100 + 50 = 150
        assert state.qty == Decimal("150")
        
        # 加權平均成本 = (15000 + 1.5 + 9000 + 0.9) / 150 = 24002.4 / 150 = 160.016
        expected_avg_cost = Decimal("160.016")
        assert state.avg_cost == expected_avg_cost, f"加權平均成本應為 {expected_avg_cost}"
        
        # 尚未賣出
        assert state.realized_pnl == Decimal("0")
        
        # 累計手續費 = 1.5 + 0.9 = 2.4
        assert state.total_fee == Decimal("2.40")


class TestAvgCostCalculatorSell:
    """賣出交易測試：已實現損益計算。"""
    
    def test_buy_then_partial_sell_realizes_pnl(self, base_trade_kwargs):
        """測試 3：BUY 後部分 SELL。
        
        場景：
        - 買入 100 股 @ 150 元（手續費 1.5）
        - 賣出 40 股 @ 160 元（手續費 0.8）
        
        驗證：
        - 持倉剩餘 60 股
        - 平均成本不變（仍為買入時的均價）
        - 已實現損益 = 40 * (160 - 150.015) - 0.8
        """
        trades = [
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                fee=Decimal("1.50")
            ),
            TradeRecord(
                **base_trade_kwargs,
                side="SELL",
                quantity=Decimal("40"),
                price=Decimal("160.00"),
                fee=Decimal("0.80")
            )
        ]
        
        state = compute_avg_cost(trades)
        
        # 持倉數量 = 100 - 40 = 60
        assert state.qty == Decimal("60"), "持倉應剩餘 60 股"
        
        # 平均成本不變（買入時的均價）
        buy_avg_cost = Decimal("150.015")
        assert state.avg_cost == buy_avg_cost, "平均成本不應改變"
        
        # 已實現損益 = 40 * (160 - 150.015) - 0.8 = 40 * 9.985 - 0.8 = 399.4 - 0.8 = 398.6
        expected_pnl = Decimal("398.60")
        assert state.realized_pnl == expected_pnl, f"已實現損益應為 {expected_pnl}"
        
        # 累計手續費 = 1.5 + 0.8 = 2.3
        assert state.total_fee == Decimal("2.30")
    
    def test_multiple_buys_and_sells_accumulate_state(self, base_trade_kwargs):
        """測試 4：多次 BUY + SELL 混合（狀態累積）。
        
        場景：
        - 買入 100 股 @ 150 元（手續費 1.5）
        - 賣出 50 股 @ 160 元（手續費 0.8）
        - 買入 30 股 @ 155 元（手續費 0.5）
        - 賣出 40 股 @ 165 元（手續費 0.7）
        
        驗證狀態正確累積。
        """
        trades = [
            # 第一次買入：100 股 @ 150
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                fee=Decimal("1.50")
            ),
            # 第一次賣出：50 股 @ 160
            TradeRecord(
                **base_trade_kwargs,
                side="SELL",
                quantity=Decimal("50"),
                price=Decimal("160.00"),
                fee=Decimal("0.80")
            ),
            # 第二次買入：30 股 @ 155
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("30"),
                price=Decimal("155.00"),
                fee=Decimal("0.50")
            ),
            # 第二次賣出：40 股 @ 165
            TradeRecord(
                **base_trade_kwargs,
                side="SELL",
                quantity=Decimal("40"),
                price=Decimal("165.00"),
                fee=Decimal("0.70")
            )
        ]
        
        state = compute_avg_cost(trades)
        
        # 手動計算驗證：
        # 1. 買入 100 @ 150，費用 1.5
        #    qty=100, avg_cost=(15000+1.5)/100=150.015
        
        # 2. 賣出 50 @ 160，費用 0.8
        #    qty=50, avg_cost=150.015（不變）
        #    realized_pnl = 50*(160-150.015)-0.8 = 50*9.985-0.8 = 499.25-0.8 = 498.45
        
        # 3. 買入 30 @ 155，費用 0.5
        #    old_cost = 50*150.015 = 7500.75
        #    new_cost = 30*155+0.5 = 4650.5
        #    qty = 80
        #    avg_cost = (7500.75+4650.5)/80 = 12151.25/80 = 151.890625
        
        # 4. 賣出 40 @ 165，費用 0.7
        #    qty = 40
        #    realized_pnl += 40*(165-151.890625)-0.7 = 40*13.109375-0.7 = 524.375-0.7 = 523.675
        #    total_realized_pnl = 498.45 + 523.675 = 1022.125
        
        assert state.qty == Decimal("40"), "最終持倉應為 40 股"
        assert state.avg_cost == Decimal("151.890625"), "平均成本計算錯誤"
        assert state.realized_pnl == Decimal("1022.125"), "已實現損益累積錯誤"
        assert state.total_fee == Decimal("3.50"), "累計手續費應為 3.50"
    
    def test_sell_all_resets_avg_cost_to_zero(self, base_trade_kwargs):
        """測試 5：賣出全部持倉後，avg_cost 重設為 0。
        
        驗證：
        - qty = 0
        - avg_cost = 0（持倉歸零）
        - realized_pnl 已計算
        """
        trades = [
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                fee=Decimal("1.50")
            ),
            TradeRecord(
                **base_trade_kwargs,
                side="SELL",
                quantity=Decimal("100"),  # 全部賣出
                price=Decimal("160.00"),
                fee=Decimal("1.00")
            )
        ]
        
        state = compute_avg_cost(trades)
        
        # 持倉歸零
        assert state.qty == Decimal("0"), "持倉應歸零"
        
        # 平均成本重設為 0
        assert state.avg_cost == Decimal("0"), "持倉歸零後，avg_cost 應重設為 0"
        
        # 已實現損益 = 100 * (160 - 150.015) - 1.0 = 998.5 - 1.0 = 997.5
        expected_pnl = Decimal("997.50")
        assert state.realized_pnl == expected_pnl, f"已實現損益應為 {expected_pnl}"


class TestAvgCostCalculatorFees:
    """手續費影響測試。"""
    
    def test_fee_increases_buy_cost(self, base_trade_kwargs):
        """測試 6：手續費增加 BUY 的成本基礎。
        
        對比有無手續費的均價差異。
        """
        # 無手續費
        trades_no_fee = [
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("100.00"),
                fee=Decimal("0")
            )
        ]
        state_no_fee = compute_avg_cost(trades_no_fee)
        
        # 有手續費
        trades_with_fee = [
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("100.00"),
                fee=Decimal("10.00")  # 10 元手續費
            )
        ]
        state_with_fee = compute_avg_cost(trades_with_fee)
        
        # 無手續費：avg_cost = 100
        assert state_no_fee.avg_cost == Decimal("100.00")
        
        # 有手續費：avg_cost = (10000 + 10) / 100 = 100.10
        assert state_with_fee.avg_cost == Decimal("100.10")
        
        # 驗證手續費確實增加了成本
        assert state_with_fee.avg_cost > state_no_fee.avg_cost
    
    def test_fee_reduces_sell_profit(self, base_trade_kwargs):
        """測試 7：手續費減少 SELL 的盈利。
        
        驗證賣出時手續費從已實現損益中扣除。
        """
        trades = [
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("100.00"),
                fee=Decimal("0")  # 買入無手續費，簡化計算
            ),
            TradeRecord(
                **base_trade_kwargs,
                side="SELL",
                quantity=Decimal("100"),
                price=Decimal("110.00"),
                fee=Decimal("5.00")  # 賣出手續費 5 元
            )
        ]
        
        state = compute_avg_cost(trades)
        
        # 無手續費時，盈利應為：100 * (110 - 100) = 1000
        # 扣除手續費後：1000 - 5 = 995
        expected_pnl = Decimal("995.00")
        assert state.realized_pnl == expected_pnl, "手續費應減少盈利"


class TestAvgCostCalculatorDefensive:
    """防禦性檢查測試。"""
    
    def test_sell_more_than_qty_raises_error(self, base_trade_kwargs):
        """測試 8：賣出數量超過持倉，拋出 ValueError。
        
        驗證防禦性檢查：不允許放空。
        """
        trades = [
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                fee=Decimal("1.50")
            ),
            TradeRecord(
                **base_trade_kwargs,
                side="SELL",
                quantity=Decimal("150"),  # 賣出 150 股，但只有 100 股
                price=Decimal("160.00"),
                fee=Decimal("1.00")
            )
        ]
        
        with pytest.raises(ValueError) as exc_info:
            compute_avg_cost(trades)
        
        # 驗證錯誤訊息包含關鍵字
        assert "賣出數量" in str(exc_info.value)
        assert "超過持倉數量" in str(exc_info.value)
        assert "不允許放空" in str(exc_info.value)
    
    def test_sell_without_position_raises_error(self, base_trade_kwargs):
        """測試：無持倉時直接賣出，拋出 ValueError。"""
        trades = [
            TradeRecord(
                **base_trade_kwargs,
                side="SELL",  # 直接賣出，無持倉
                quantity=Decimal("50"),
                price=Decimal("100.00"),
                fee=Decimal("1.00")
            )
        ]
        
        with pytest.raises(ValueError) as exc_info:
            compute_avg_cost(trades)
        
        assert "賣出數量" in str(exc_info.value)
        assert "超過持倉數量" in str(exc_info.value)


class TestAvgCostCalculatorEdgeCases:
    """邊界條件測試。"""
    
    def test_empty_trades_returns_zero_state(self):
        """測試：空交易列表回傳全零狀態。"""
        trades = []
        state = compute_avg_cost(trades)
        
        assert state.qty == Decimal("0")
        assert state.avg_cost == Decimal("0")
        assert state.realized_pnl == Decimal("0")
        assert state.total_fee == Decimal("0")
    
    def test_zero_fee_trades_work_correctly(self, base_trade_kwargs):
        """測試：零手續費交易正常運作。"""
        trades = [
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("100.00"),
                fee=Decimal("0")  # 零手續費
            ),
            TradeRecord(
                **base_trade_kwargs,
                side="SELL",
                quantity=Decimal("50"),
                price=Decimal("110.00"),
                fee=Decimal("0")  # 零手續費
            )
        ]
        
        state = compute_avg_cost(trades)
        
        assert state.qty == Decimal("50")
        assert state.avg_cost == Decimal("100.00")
        assert state.realized_pnl == Decimal("500.00")  # 50 * (110 - 100)
        assert state.total_fee == Decimal("0")
    
    def test_buy_sell_buy_again_after_zero_position(self, base_trade_kwargs):
        """測試：持倉歸零後再次買入，avg_cost 重新計算。
        
        場景：
        - 買入 100 股 @ 100
        - 賣出 100 股 @ 110（歸零）
        - 再次買入 50 股 @ 120
        
        驗證第二次買入時 avg_cost 正確計算（不受第一次影響）。
        """
        trades = [
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("100"),
                price=Decimal("100.00"),
                fee=Decimal("0")
            ),
            TradeRecord(
                **base_trade_kwargs,
                side="SELL",
                quantity=Decimal("100"),
                price=Decimal("110.00"),
                fee=Decimal("0")
            ),
            TradeRecord(
                **base_trade_kwargs,
                side="BUY",
                quantity=Decimal("50"),
                price=Decimal("120.00"),
                fee=Decimal("1.00")
            )
        ]
        
        state = compute_avg_cost(trades)
        
        # 持倉 = 50 股
        assert state.qty == Decimal("50")
        
        # avg_cost = (50 * 120 + 1) / 50 = 6001 / 50 = 120.02
        assert state.avg_cost == Decimal("120.02")
        
        # realized_pnl = 第一次賣出的盈利：100 * (110 - 100) = 1000
        assert state.realized_pnl == Decimal("1000.00")
