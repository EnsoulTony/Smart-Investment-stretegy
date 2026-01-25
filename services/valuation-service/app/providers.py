"""Price/Fx providers (stub implementations)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import date


@dataclass(frozen=True)
class PriceResult:
    price: Decimal
    ccy: str
    source: str


class PriceProvider:
    """Stub price provider."""

    @staticmethod
    def provider_name() -> str:
        return "stub"

    @staticmethod
    def source() -> str:
        return "stub_price"

    def get_price(self, symbol: str, as_of: date) -> tuple[Decimal, str, str]:
        base = sum(ord(ch) for ch in symbol) % 100
        price = Decimal("10") + Decimal(str(base)) / Decimal("10")
        return price, "USD", self.source()


class FxProvider:
    """Stub FX provider."""

    @staticmethod
    def provider_name() -> str:
        return "stub"

    def get_rate(self, from_ccy: str, to_ccy: str, as_of: date) -> Decimal:
        if from_ccy == to_ccy:
            return Decimal("1")
        mapping = {
            ("USD", "TWD"): Decimal("32"),
            ("TWD", "USD"): Decimal("0.03125"),
        }
        return mapping.get((from_ccy, to_ccy), Decimal("1"))
