"""匯率折算模組：Stub Provider

Stub 實作：嚴格模式，僅支援同幣別轉換。
用於開發/測試階段，避免在無真實匯率來源時默默用錯誤匯率。

行為規範：
- from_ccy == to_ccy：回傳原值（正常）
- from_ccy != to_ccy：raise NotImplementedError（嚴格，避免靜默錯誤）
"""
from decimal import Decimal
from datetime import date
from typing import Optional

from .interfaces import FxProvider
from .types import Currency, ExchangeRate


class StubFxProvider(FxProvider):
    """Stub 匯率提供者（僅供開發/測試）
    
    嚴格模式：不支援跨幣別轉換，明確失敗優於隱式錯誤。
    """
    
    def get_rate(
        self, 
        base_ccy: Currency, 
        quote_ccy: Currency, 
        asof_date: Optional[date] = None
    ) -> ExchangeRate:
        """取得匯率（僅支援同幣別）
        
        Raises:
            NotImplementedError: 當 base_ccy != quote_ccy
        """
        if base_ccy == quote_ccy:
            return ExchangeRate(Decimal('1'))
        
        raise NotImplementedError(
            f"StubFxProvider 不支援跨幣別匯率查詢：{base_ccy} -> {quote_ccy}。"
            f"請設定真實的 FX_PROVIDER（如 yahoo, central_bank 等）。"
        )
    
    def convert(
        self, 
        amount: Decimal, 
        from_ccy: Currency, 
        to_ccy: Currency,
        asof_date: Optional[date] = None
    ) -> Decimal:
        """轉換金額（僅支援同幣別）
        
        Raises:
            NotImplementedError: 當 from_ccy != to_ccy
        """
        if from_ccy == to_ccy:
            return amount
        
        raise NotImplementedError(
            f"StubFxProvider 不支援跨幣別轉換：{amount} {from_ccy} -> {to_ccy}。"
            f"請設定真實的 FX_PROVIDER（如 yahoo, central_bank 等）。"
        )
    
    def source(self) -> str:
        """資料來源識別"""
        return "stub"
    
    def is_stub(self) -> bool:
        """是否為 Stub"""
        return True
