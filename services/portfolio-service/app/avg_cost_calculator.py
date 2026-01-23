"""均價法計算器（Weighted Average Cost Calculator）。

本模組提供純函數計算邏輯，用於根據交易記錄計算持倉的平均成本與已實現損益。

核心規則：
1. BUY（買入）：
   - 新均價 = (舊持倉數量 × 舊均價 + 買入數量 × 買入價格 + 手續費) / (舊持倉數量 + 買入數量)
   - 持倉數量增加
   - 已實現損益不變

2. SELL（賣出）：
   - 已實現損益 += 賣出數量 × (賣出價格 - 平均成本) - 手續費
   - 持倉數量減少
   - 若持倉歸零，平均成本重設為 0

3. 防禦性檢查：
   - 賣出數量不得超過持倉數量（否則拋出 ValueError）
   - 數量、價格、手續費不得為負數

特性：
- 使用 Decimal 避免浮點數精度問題
- 純函數設計，無副作用，易於測試
- 假設輸入已按時間排序（由呼叫方負責）
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from app.schemas import TradeRecord


@dataclass
class AvgCostState:
    """持倉狀態（均價法計算結果）。
    
    Attributes:
        qty: 當前持倉數量（可為 0）
        avg_cost: 平均成本（持倉成本基礎）
        realized_pnl: 已實現損益（累計所有賣出交易的盈虧）
        total_fee: 累計手續費（所有交易的手續費總和）
    
    Notes:
        - 所有金額使用 Decimal 避免浮點誤差
        - qty = 0 時，avg_cost 應為 0
        - realized_pnl 包含手續費影響（買入時增加成本，賣出時減少收益）
    """
    qty: Decimal
    avg_cost: Decimal
    realized_pnl: Decimal
    total_fee: Decimal


def compute_avg_cost(trades: List[TradeRecord]) -> AvgCostState:
    """根據交易記錄計算均價法持倉狀態（純函數）。
    
    假設：
    1. 輸入的 trades 已按 trade_date 排序（由呼叫方負責）
    2. 所有交易屬於同一 user_id、symbol、asset_ccy（由呼叫方分組）
    3. TradeRecord 已通過 Pydantic 驗證（side 為 BUY/SELL，qty/price/fee >= 0）
    
    算法：
    - 初始狀態：qty=0, avg_cost=0, realized_pnl=0, total_fee=0
    - 依序處理每筆交易：
      - BUY: 更新均價與持倉數量
      - SELL: 計算已實現損益，減少持倉數量
    
    Args:
        trades: 交易記錄列表（已排序、已分組）
    
    Returns:
        AvgCostState: 最終持倉狀態
    
    Raises:
        ValueError: 當出現以下情況時
            - 賣出數量超過持倉數量（不允許放空）
            - 數量、價格、手續費為負數（防禦性檢查）
    
    Examples:
        >>> from app.schemas import TradeRecord
        >>> from datetime import datetime
        >>> from decimal import Decimal
        >>> 
        >>> # 範例 1: 買入 100 股 @ 10 元
        >>> trades = [
        ...     TradeRecord(
        ...         user_id="test", symbol="AAPL", asset_ccy="USD",
        ...         side="BUY", quantity=Decimal("100"), price=Decimal("10"),
        ...         fee=Decimal("1"), trade_date=datetime.now(), broker="IB"
        ...     )
        ... ]
        >>> state = compute_avg_cost(trades)
        >>> state.qty
        Decimal('100')
        >>> state.avg_cost  # (100*10 + 1) / 100 = 10.01
        Decimal('10.01')
        
        >>> # 範例 2: 買入後賣出一半
        >>> trades.append(
        ...     TradeRecord(
        ...         user_id="test", symbol="AAPL", asset_ccy="USD",
        ...         side="SELL", quantity=Decimal("50"), price=Decimal("12"),
        ...         fee=Decimal("0.5"), trade_date=datetime.now(), broker="IB"
        ...     )
        ... )
        >>> state = compute_avg_cost(trades)
        >>> state.qty
        Decimal('50')
        >>> state.realized_pnl  # 50*(12-10.01) - 0.5 = 99.5 - 0.5 = 99
        Decimal('99.00')
    """
    # 初始狀態
    qty = Decimal("0")
    avg_cost = Decimal("0")
    realized_pnl = Decimal("0")
    total_fee = Decimal("0")
    
    for trade in trades:
        # 防禦性檢查（雖然 Pydantic 已驗證，但作為純函數仍需檢查）
        if trade.quantity < 0:
            raise ValueError(f"交易數量不得為負數：{trade.quantity}")
        if trade.price < 0:
            raise ValueError(f"交易價格不得為負數：{trade.price}")
        if trade.fee < 0:
            raise ValueError(f"手續費不得為負數：{trade.fee}")
        
        total_fee += trade.fee
        
        if trade.side == "BUY":
            # BUY 規則：更新均價
            # 新均價 = (舊持倉成本 + 新買入成本 + 手續費) / 新持倉數量
            # 其中：舊持倉成本 = qty * avg_cost
            #       新買入成本 = trade.quantity * trade.price
            old_cost = qty * avg_cost
            new_cost = trade.quantity * trade.price + trade.fee
            new_qty = qty + trade.quantity
            
            if new_qty > 0:
                avg_cost = (old_cost + new_cost) / new_qty
            else:
                avg_cost = Decimal("0")  # 理論上不會發生（買入後 qty > 0）
            
            qty = new_qty
            
        elif trade.side == "SELL":
            # SELL 規則：計算已實現損益
            # 防禦性檢查：不允許賣出超過持倉
            if trade.quantity > qty:
                raise ValueError(
                    f"賣出數量 ({trade.quantity}) 超過持倉數量 ({qty})，"
                    f"不允許放空。symbol={trade.symbol}, date={trade.trade_date}"
                )
            
            # 已實現損益 = 賣出數量 × (賣出價格 - 平均成本) - 手續費
            pnl = trade.quantity * (trade.price - avg_cost) - trade.fee
            realized_pnl += pnl
            
            # 更新持倉數量
            qty -= trade.quantity
            
            # 若持倉歸零，平均成本重設為 0
            if qty == 0:
                avg_cost = Decimal("0")
        
        else:
            # 理論上不會發生（Pydantic 已驗證 side 為 BUY/SELL）
            raise ValueError(f"不支援的交易方向：{trade.side}")
    
    return AvgCostState(
        qty=qty,
        avg_cost=avg_cost,
        realized_pnl=realized_pnl,
        total_fee=total_fee
    )
