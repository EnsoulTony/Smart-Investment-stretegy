"""FX 匯率折算模組：介面定義（Boundary）

定義 FxProvider 介面，作為匯率折算的唯一邊界。
全專案所有匯率查詢/轉換必須透過此介面，嚴禁直接讀取環境變數或實作。

架構原則：
- 帳務層（Accounting Layer）：使用 asset_ccy 記帳，由資料庫欄位定義
- 估值層（Valuation Layer）：使用 valuation_ccy（通常為 TWD）折算，由此模組提供
- Portfolio Service 的 rebuild_positions 屬於帳務層，不做折算
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import date
from typing import Optional

from .types import Currency, ExchangeRate


class FxProvider(ABC):
    """匯率提供者抽象介面
    
    定義匯率查詢與轉換的標準介面，所有實作必須遵守此契約。
    """
    
    @abstractmethod
    def get_rate(
        self, 
        base_ccy: Currency, 
        quote_ccy: Currency, 
        asof_date: Optional[date] = None
    ) -> ExchangeRate:
        """取得匯率（quote_ccy per base_ccy）
        
        Args:
            base_ccy: 基準幣別（分子）
            quote_ccy: 計價幣別（分母）
            asof_date: 查詢日期，None 表示最新
            
        Returns:
            匯率（Decimal），表示 1 單位 base_ccy = X 單位 quote_ccy
            
        Raises:
            NotImplementedError: 該 provider 不支援此幣別對或查詢
            ValueError: 參數不合法
        
        Example:
            rate = provider.get_rate('USD', 'TWD')  # 1 USD = 31.5 TWD
            # rate = Decimal('31.5')
        """
        pass
    
    @abstractmethod
    def convert(
        self, 
        amount: Decimal, 
        from_ccy: Currency, 
        to_ccy: Currency,
        asof_date: Optional[date] = None
    ) -> Decimal:
        """轉換金額幣別
        
        Args:
            amount: 原始金額
            from_ccy: 來源幣別
            to_ccy: 目標幣別
            asof_date: 查詢日期，None 表示最新
            
        Returns:
            轉換後金額（Decimal）
            
        Raises:
            NotImplementedError: 該 provider 不支援此幣別對或查詢
            ValueError: 參數不合法
            
        Example:
            result = provider.convert(Decimal('100'), 'USD', 'TWD')
            # result = Decimal('3150')  # 假設 1 USD = 31.5 TWD
        """
        pass
    
    @abstractmethod
    def source(self) -> str:
        """回傳資料來源識別
        
        Returns:
            資料來源名稱（如 'stub', 'yahoo', 'central_bank' 等）
        """
        pass
    
    @abstractmethod
    def is_stub(self) -> bool:
        """是否為 Stub（測試用假實作）
        
        Returns:
            True 表示此為 stub provider，僅支援同幣別轉換
        """
        pass
