"""Resolve symbol name_zh using mapping table + external providers."""

from __future__ import annotations

from typing import Dict, Optional, Tuple
import logging
import os
import re
import time
import httpx

from app.repositories.symbol_name_mappings_repo import SymbolNameMappingsRepository
from app.utils import safe_str


TW_SYMBOL_RE = re.compile(r"^\d{4,6}(\.TW|\.TWO)?$", re.IGNORECASE)

TWSE_LIST_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_LIST_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

logger = logging.getLogger(__name__)

_TWSE_CACHE: Dict[str, str] = {}
_TPEX_CACHE: Dict[str, str] = {}
_TWSE_CACHE_AT = 0.0
_TPEX_CACHE_AT = 0.0


def _cache_ttl_seconds() -> float:
    try:
        return float(os.getenv("SYMBOL_NAME_TW_CACHE_TTL", "21600"))
    except Exception:
        return 21600.0


def _normalize_tw_symbol(symbol: str) -> str:
    if symbol.endswith(".TW") or symbol.endswith(".TWO"):
        return symbol.split(".", 1)[0]
    return symbol


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
        base_symbol = _normalize_tw_symbol(symbol)
        name = self._resolve_twse(base_symbol)
        if name:
            return name, "twse"
        name = self._resolve_tpex(base_symbol)
        if name:
            return name, "tpex"
        # Fallback to Yahoo if TWSE/TPEx fail.
        if symbol.endswith(".TW") or symbol.endswith(".TWO"):
            return self._resolve_yahoo(symbol, source="yahoo_tw")
        name, source = self._resolve_yahoo(f"{base_symbol}.TW", source="yahoo_tw")
        if name:
            return name, source
        return self._resolve_yahoo(f"{base_symbol}.TWO", source="yahoo_tw")

    def _resolve_twse(self, symbol: str) -> str:
        global _TWSE_CACHE_AT, _TWSE_CACHE
        now = time.time()
        ttl = _cache_ttl_seconds()
        if not _TWSE_CACHE or now - _TWSE_CACHE_AT > ttl:
            try:
                resp = httpx.get(
                    TWSE_LIST_URL,
                    timeout=self.timeout,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                rows = resp.json()
                _TWSE_CACHE = {
                    safe_str(row.get("Code")).upper(): safe_str(row.get("Name"))
                    for row in (rows or [])
                    if row.get("Code") and row.get("Name")
                }
                _TWSE_CACHE_AT = now
            except Exception as exc:
                logger.warning("TWSE lookup failed: %s", exc)
                return ""
        return _TWSE_CACHE.get(symbol, "")

    def _resolve_tpex(self, symbol: str) -> str:
        global _TPEX_CACHE_AT, _TPEX_CACHE
        now = time.time()
        ttl = _cache_ttl_seconds()
        if not _TPEX_CACHE or now - _TPEX_CACHE_AT > ttl:
            try:
                resp = httpx.get(
                    TPEX_LIST_URL,
                    timeout=self.timeout,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                rows = resp.json()
                _TPEX_CACHE = {
                    safe_str(row.get("SecuritiesCompanyCode")).upper(): safe_str(
                        row.get("CompanyName")
                    )
                    for row in (rows or [])
                    if row.get("SecuritiesCompanyCode") and row.get("CompanyName")
                }
                _TPEX_CACHE_AT = now
            except Exception as exc:
                logger.warning("TPEx lookup failed: %s", exc)
                return ""
        return _TPEX_CACHE.get(symbol, "")

    def _resolve_yahoo(self, symbol: str, source: str) -> Tuple[str, str]:
        try:
            params = {"q": symbol, "quotesCount": 1, "newsCount": 0}
            resp = httpx.get(
                "https://query2.finance.yahoo.com/v1/finance/search",
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            payload = resp.json()
            quotes = payload.get("quotes") or []
            if quotes:
                quote = quotes[0]
                name = quote.get("shortname") or quote.get("longname") or ""
                return name, source
        except Exception as exc:
            logger.warning("Yahoo lookup failed for %s: %s", symbol, exc)
            return "", source
        return "", source
