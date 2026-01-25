"""Price/Fx providers (abstract interface + stub implementations).

Sprint 1-4.B：可替換的 Provider 架構
- 定義抽象介面 (ABC)
- 提供 Stub 實作（deterministic，測試用）
- 支援未來替換成真實 Provider（Yahoo Finance, Alpha Vantage 等）

鐵律：
- Provider 必須是 deterministic（相同輸入 → 相同輸出）
- Stub 不依賴外網
- 回傳 evidence 需包含 provider 名稱與版本
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from datetime import date
from typing import Tuple


# ============================================================================
# Version & Constants
# ============================================================================

PROVIDER_VERSION = "1.4.B"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass(frozen=True)
class PriceResult:
    """價格查詢結果"""
    price: Decimal
    ccy: str
    source: str


# ============================================================================
# Abstract Interfaces
# ============================================================================

class BasePriceProvider(ABC):
    """價格 Provider 抽象介面

    實作須提供：
    - provider_name(): 返回 provider 名稱（用於 evidence）
    - provider_version(): 返回版本字串
    - source(): 返回資料來源標識
    - get_price(): 返回 (price, ccy, source) tuple
    """

    @staticmethod
    @abstractmethod
    def provider_name() -> str:
        """Provider 名稱（用於 evidence）"""
        pass

    @staticmethod
    @abstractmethod
    def provider_version() -> str:
        """Provider 版本"""
        pass

    @staticmethod
    @abstractmethod
    def source() -> str:
        """資料來源標識"""
        pass

    @abstractmethod
    def get_price(self, symbol: str, as_of: date) -> Tuple[Decimal, str, str]:
        """取得價格

        Args:
            symbol: 股票代號
            as_of: 查詢日期

        Returns:
            (price, currency, source) tuple
        """
        pass


class BaseFxProvider(ABC):
    """匯率 Provider 抽象介面

    實作須提供：
    - provider_name(): 返回 provider 名稱
    - provider_version(): 返回版本字串
    - get_rate(): 返回匯率
    """

    @staticmethod
    @abstractmethod
    def provider_name() -> str:
        """Provider 名稱（用於 evidence）"""
        pass

    @staticmethod
    @abstractmethod
    def provider_version() -> str:
        """Provider 版本"""
        pass

    @abstractmethod
    def get_rate(self, from_ccy: str, to_ccy: str, as_of: date) -> Decimal:
        """取得匯率

        Args:
            from_ccy: 來源幣別
            to_ccy: 目標幣別
            as_of: 查詢日期

        Returns:
            匯率（1 from_ccy = ? to_ccy）
        """
        pass


# ============================================================================
# Stub Implementations (Deterministic, for testing)
# ============================================================================

class StubPriceProvider(BasePriceProvider):
    """Stub 價格 Provider（測試用）

    特性：
    - Deterministic：相同 symbol → 相同價格
    - 價格計算：base = sum(ord(c) for c in symbol) % 100
    - 預設幣別：USD
    """

    @staticmethod
    def provider_name() -> str:
        return "stub"

    @staticmethod
    def provider_version() -> str:
        return PROVIDER_VERSION

    @staticmethod
    def source() -> str:
        return "stub_price"

    def get_price(self, symbol: str, as_of: date) -> Tuple[Decimal, str, str]:
        # Deterministic 價格計算
        base = sum(ord(ch) for ch in symbol) % 100
        price = Decimal("10") + Decimal(str(base)) / Decimal("10")
        return price, "USD", self.source()


class StubFxProvider(BaseFxProvider):
    """Stub 匯率 Provider（測試用）

    特性：
    - Deterministic：固定匯率表
    - 同幣別 → 1.0
    - 支援 USD/TWD 雙向
    """

    # 固定匯率表
    RATE_TABLE = {
        ("USD", "TWD"): Decimal("32"),
        ("TWD", "USD"): Decimal("0.03125"),
        ("EUR", "USD"): Decimal("1.08"),
        ("USD", "EUR"): Decimal("0.926"),
        ("GBP", "USD"): Decimal("1.27"),
        ("USD", "GBP"): Decimal("0.787"),
        ("JPY", "USD"): Decimal("0.0067"),
        ("USD", "JPY"): Decimal("149.25"),
    }

    @staticmethod
    def provider_name() -> str:
        return "stub"

    @staticmethod
    def provider_version() -> str:
        return PROVIDER_VERSION

    def get_rate(self, from_ccy: str, to_ccy: str, as_of: date) -> Decimal:
        if from_ccy == to_ccy:
            return Decimal("1")
        return self.RATE_TABLE.get((from_ccy, to_ccy), Decimal("1"))


# ============================================================================
# Default Providers (Aliases for backward compatibility)
# ============================================================================

# 預設 Provider（可在 main.py 中透過 factory 替換）
PriceProvider = StubPriceProvider
FxProvider = StubFxProvider


# ============================================================================
# Provider Factory (for dependency injection)
# ============================================================================

def get_price_provider(provider_type: str = "stub") -> BasePriceProvider:
    """取得價格 Provider

    Args:
        provider_type: "stub" | "yahoo" | "alphavantage"（未來擴充）

    Returns:
        BasePriceProvider 實作
    """
    providers = {
        "stub": StubPriceProvider,
        # 未來擴充：
        # "yahoo": YahooPriceProvider,
        # "alphavantage": AlphaVantagePriceProvider,
    }
    provider_cls = providers.get(provider_type, StubPriceProvider)
    return provider_cls()


def get_fx_provider(provider_type: str = "stub") -> BaseFxProvider:
    """取得匯率 Provider

    Args:
        provider_type: "stub" | "yahoo" | "ecb"（未來擴充）

    Returns:
        BaseFxProvider 實作
    """
    providers = {
        "stub": StubFxProvider,
        # 未來擴充：
        # "yahoo": YahooFxProvider,
        # "ecb": EcbFxProvider,
    }
    provider_cls = providers.get(provider_type, StubFxProvider)
    return provider_cls()
