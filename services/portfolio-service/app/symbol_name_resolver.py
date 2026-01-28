"""Resolve symbol name_zh using mapping table + external providers."""

from __future__ import annotations

from typing import Dict, Optional, Tuple
import os
import re
import httpx

from app.repositories.symbol_name_mappings_repo import SymbolNameMappingsRepository
from app.utils import safe_str


TW_SYMBOL_RE = re.compile(r"^\d{4,5}(\.TW|\.TWO)?$", re.IGNORECASE)


class SymbolNameResolver:
    def __init__(self, repo: SymbolNameMappingsRepository):
        self.repo = repo
        self.cache: Dict[Tuple[str, str], str] = {}
        self.provider = os.getenv("SYMBOL_NAME_PROVIDER", "auto").lower()
        self.timeout = float(os.getenv("SYMBOL_NAME_TIMEOUT", "2.5"))

    def resolve(self, symbol: str, asset_ccy: Optional[str] = None) -> str:
        symbol = safe_str(symbol).upper()
        if not symbol:
            return ""

        market = self.infer_market(symbol, asset_ccy)
        cache_key = (symbol, market)
        if cache_key in self.cache:
            return self.cache[cache_key]

        mapping = self.repo.get_mapping(symbol, market)
        if mapping:
            self.cache[cache_key] = mapping.name_zh
            return mapping.name_zh

        if self.provider in {"disabled", "off", "none"}:
            return ""

        name, source = self._resolve_from_provider(symbol, market)
        if name:
            self.repo.upsert_mapping(symbol=symbol, market=market, name_zh=name, source=source)
        self.cache[cache_key] = name
        return name

    def infer_market(self, symbol: str, asset_ccy: Optional[str]) -> str:
        if asset_ccy and asset_ccy.upper() == "TWD":
            return "TW"
        if TW_SYMBOL_RE.match(symbol):
            return "TW"
        return "US"

    def _resolve_from_provider(self, symbol: str, market: str) -> Tuple[str, str]:
        if market == "TW":
            return self._resolve_tw(symbol)
        return self._resolve_us(symbol)

    def _resolve_us(self, symbol: str) -> Tuple[str, str]:
        return self._resolve_yahoo(symbol, source="yahoo_us")

    def _resolve_tw(self, symbol: str) -> Tuple[str, str]:
        # Try TWSE and OTC suffixes if not already present.
        if symbol.endswith(".TW") or symbol.endswith(".TWO"):
            return self._resolve_yahoo(symbol, source="yahoo_tw")
        name, source = self._resolve_yahoo(f"{symbol}.TW", source="yahoo_tw")
        if name:
            return name, source
        return self._resolve_yahoo(f"{symbol}.TWO", source="yahoo_tw")

    def _resolve_yahoo(self, symbol: str, source: str) -> Tuple[str, str]:
        try:
            params = {"q": symbol, "quotesCount": 1, "newsCount": 0}
            resp = httpx.get(
                "https://query2.finance.yahoo.com/v1/finance/search",
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
            quotes = payload.get("quotes") or []
            if quotes:
                quote = quotes[0]
                name = quote.get("shortname") or quote.get("longname") or ""
                return name, source
        except Exception:
            return "", source
        return "", source
