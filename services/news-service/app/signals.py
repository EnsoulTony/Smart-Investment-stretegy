"""Deterministic news signals with fixed Sprint 3 rules."""

from __future__ import annotations

from dataclasses import dataclass
import re
import hashlib
from typing import List, Dict, Tuple
import os
import logging
import httpx
from app.db import fetch_recent_news_signals

PORTFOLIO_BASE_URL = os.getenv("PORTFOLIO_BASE_URL", "http://portfolio-service:8001")
DEFAULT_CORE_HOLDINGS = ["TSLA", "CCJ", "OXY", "TSM", "URA"]
DEFAULT_NEWS_PER_SOURCE = int(os.getenv("NEWS_SOURCE_LIMIT", "10"))
DEFAULT_TOTAL_NEWS_LIMIT = int(os.getenv("NEWS_TOTAL_LIMIT", "10"))
EXTERNAL_NEWS_ENABLED = os.getenv("NEWS_EXTERNAL_ENABLED", "0").lower() in {"1", "true", "yes", "on"}
_ITEMS_CACHE: Dict[Tuple[str, str], List[dict]] = {}


def safe_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def fetch_core_holdings(user_id: str) -> List[str]:
    """Fetch core holdings symbols from portfolio-service, fallback to defaults."""
    try:
        url = f"{PORTFOLIO_BASE_URL}/portfolio/core_holdings"
        resp = httpx.get(url, params={"user_id": user_id}, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        symbols = data.get("symbols", []) if isinstance(data, dict) else []
        normalized = [normalize_symbol(s) for s in symbols]
        if normalized:
            return normalized
    except Exception:
        pass
    return DEFAULT_CORE_HOLDINGS

FACTOR_GROUPS: Dict[str, List[str]] = {
    "defensive": [
        "XLU", "TLT", "IEF", "00687B", "00953B", "00965",
        "009805", "00983A", "00984A", "00988A",
    ],
    "growth_tech": [
        "TSLA", "TSM", "QQQ", "ARKK", "ARKQ", "0050", "0052", "6789",
    ],
    "energy": [
        "OXY", "XLE", "URA", "CCJ", "MP",
    ],
}

RATE_KEYWORDS = [
    "升息", "降息", "利率決議", "FOMC", "Fed", "ECB", "BOJ",
    "通膨", "CPI", "PCE", "殖利率", "10年期",
    "rate hike", "rate cut", "interest rate decision", "rate decision",
    "central bank", "hawkish", "dovish",
    "inflation", "yield", "treasury", "10-year", "10 year", "bond yield",
]
TARIFF_KEYWORDS = [
    "關稅", "制裁", "出口管制", "禁令", "實體清單", "貿易戰",
    "tariff", "sanction", "export control", "ban", "entity list", "trade war",
    "trade restriction", "import ban", "export ban",
]
WAR_ENERGY_KEYWORDS = [
    "戰爭", "空襲", "封鎖", "油價飆升", "供應中斷", "OPEC",
    "war", "airstrike", "blockade", "oil surge", "supply disruption", "energy shock",
    "missile strike", "conflict", "geopolitical risk", "supply shock",
]
CREDIT_KEYWORDS = [
    "倒閉", "違約", "清算", "挤兑", "信用危機", "流動性危機", "銀行危機",
    "default", "bankruptcy", "liquidation", "bank run", "credit crisis",
    "liquidity crisis", "banking crisis", "credit event", "insolvency",
]
AI_POWER_PRIMARY = [
    "核能", "電網", "供電", "PPA", "GW", "資料中心", "AI超級電腦", "電力需求", "電價",
    "nuclear", "grid", "power supply", "data center", "supercomputer",
    "power demand", "electricity price", "power price",
]
AI_POWER_SECONDARY = [
    "訂單", "供電", "合約", "容量", "電網",
    "order", "contract", "capacity", "grid", "offtake", "ppa",
]

MARKET_MECH_KEYWORDS = [
    "大跌", "暴跌", "飆升", "創新高", "創新低", "跳空", "熔斷", "reprice", "pricing in",
    "selloff", "plunge", "surge", "record high", "record low", "gap",
    "circuit breaker", "volatility spike", "risk-off", "risk on",
    "market rout", "meltdown", "flash crash",
]

HUGE_SCALE_REGEX = re.compile(r"\b(\d+(\.\d+)?)(\s?)(GW|兆|十億|Billion|bn)\b", re.IGNORECASE)
SYMBOL_REGEX = re.compile(r"\b[A-Z]{1,5}\b|\b\d{4,6}\b")


def normalize_symbol(symbol: str) -> str:
    symbol = safe_str(symbol).upper()
    if symbol.endswith(".TW") or symbol.endswith(".TWO"):
        return symbol.split(".", 1)[0]
    return symbol

def fetch_positions_name_map(user_id: str) -> Dict[str, str]:
    """Build name -> symbol map from positions (symbol as English, name_zh as Chinese)."""
    name_map: Dict[str, str] = {}
    try:
        url = f"{PORTFOLIO_BASE_URL}/portfolio/positions"
        resp = httpx.get(url, params={"user_id": user_id}, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else []
        for item in items:
            symbol = normalize_symbol(item.get("symbol", ""))
            name_zh = safe_str(item.get("name_zh", ""))
            if symbol:
                name_map[symbol] = symbol
            if name_zh:
                name_map[name_zh] = symbol
    except Exception:
        pass
    return name_map


@dataclass(frozen=True)
class NewsDraft:
    """Input stub news for deterministic output."""

    id: str
    title: str
    summary_zh: str
    published_at: str
    source_url: str
    tier: str | None = None


def get_factor_group(symbol: str) -> str:
    symbol_upper = symbol.upper()
    for group_name, symbols in FACTOR_GROUPS.items():
        if symbol_upper in {s.upper() for s in symbols}:
            return group_name
    return "other"


def _contains_any(text: str, keywords: List[str]) -> bool:
    lower_text = text.lower()
    for keyword in keywords:
        if keyword in text:
            return True
        if keyword.lower() in lower_text:
            return True
    return False


def _match_rate(text: str) -> bool:
    return _contains_any(text, RATE_KEYWORDS)


def _match_tariff(text: str) -> bool:
    return _contains_any(text, TARIFF_KEYWORDS)


def _match_war_energy(text: str) -> bool:
    return _contains_any(text, WAR_ENERGY_KEYWORDS)


def _match_credit(text: str) -> bool:
    return _contains_any(text, CREDIT_KEYWORDS)


def _match_ai_power(text: str) -> bool:
    return _contains_any(text, AI_POWER_PRIMARY) and _contains_any(text, AI_POWER_SECONDARY)


def _match_market_mechanism(text: str) -> bool:
    return _contains_any(text, MARKET_MECH_KEYWORDS)


def _is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except Exception:
        return False


def extract_symbols(text: str, whitelist: List[str], name_map: Dict[str, str]) -> List[str]:
    symbols = [normalize_symbol(match.group(0)) for match in SYMBOL_REGEX.finditer(text)]
    whitelist_set = {normalize_symbol(s) for s in whitelist}
    filtered = [symbol for symbol in symbols if symbol in whitelist_set]
    # Expand by company names from positions
    if name_map:
        text_upper = text.upper()
        for name, sym in name_map.items():
            if not name or not sym:
                continue
            if _is_ascii(name):
                if name.upper() in text_upper:
                    filtered.append(sym.upper())
            else:
                if name in text:
                    filtered.append(sym.upper())
    seen = set()
    unique_symbols = []
    for symbol in filtered:
        if symbol not in seen:
            seen.add(symbol)
            unique_symbols.append(symbol)
    return unique_symbols


def compute_n1_score(
    text: str,
    symbols: List[str],
    core_holdings: List[str],
    name_map: Dict[str, str],
) -> int:
    score = 0
    if _match_rate(text):
        score += 4
    if _match_tariff(text):
        score += 4
    if _match_war_energy(text):
        score += 4
    if _match_credit(text):
        score += 4
    if _match_ai_power(text):
        score += 3
    if HUGE_SCALE_REGEX.search(text):
        score += 3
    core_set = {normalize_symbol(s) for s in core_holdings}
    if any(symbol in core_set for symbol in symbols):
        score += 2
    if _match_market_mechanism(text):
        score += 2
    # Company name mentions as core holdings boost (from positions)
    if name_map:
        text_upper = text.upper()
        for name, sym in name_map.items():
            if not name or not sym:
                continue
            if _is_ascii(name):
                matched = name.upper() in text_upper
            else:
                matched = name in text
            if matched and normalize_symbol(sym) in core_set:
                score += 2
                break
    return score


def build_themes(text: str) -> List[str]:
    themes: List[str] = []
    if _match_rate(text):
        themes.append("rates_central_bank")
    if _match_tariff(text):
        themes.append("tariff_sanctions")
    if _match_war_energy(text):
        themes.append("war_energy_supply")
    if _match_credit(text):
        themes.append("credit_event")
    if _match_ai_power(text):
        themes.append("ai_power")
    return themes


def build_triggers(text: str) -> List[dict]:
    triggers = []
    if _match_rate(text):
        triggers.append({
            "type": "market",
            "name": "US10Y",
            "condition": "break_above_4.5",
            "value": 4.5,
        })
    if _match_tariff(text):
        triggers.append({
            "type": "policy",
            "name": "tariff",
            "condition": "official_announced",
            "value": 1,
        })
    if _match_war_energy(text):
        triggers.append({
            "type": "market",
            "name": "WTI",
            "condition": "break_above_90",
            "value": 90,
        })
    if _match_ai_power(text):
        triggers.append({
            "type": "market",
            "name": "XLK/XLU",
            "condition": "cross_below_ma50",
            "value": 0,
        })
    if _match_credit(text):
        triggers.append({
            "type": "credit",
            "name": "CDS",
            "condition": "widen_above_threshold",
            "value": 0,
        })
    if _match_market_mechanism(text):
        triggers.append({
            "type": "market",
            "name": "volatility",
            "condition": "spike",
            "value": 1,
        })
    if not triggers:
        triggers.append({
            "type": "context",
            "name": "news_sentiment",
            "condition": "monitor",
            "value": 1,
        })
    return triggers



# 新增：動態抓取外部新聞來源
import feedparser
from datetime import datetime

def fetch_external_news(as_of: str, per_source_limit: int = DEFAULT_NEWS_PER_SOURCE) -> List[NewsDraft]:
    import logging

    if not EXTERNAL_NEWS_ENABLED:
        return []

    news_items = []
    headers = {"User-Agent": "Mozilla/5.0"}
    chinese_sources = [
        ("cnyes", "https://news.cnyes.com/rss/news/cat/wd_stock"),
        ("ltn", "https://news.ltn.com.tw/rss/business.xml"),
        ("hket", "https://www.hket.com/rss/finance"),
    ]
    # 1. CNBC RSS
    try:
        resp = httpx.get(
            "https://search.cnbc.com/rs/search/view.xml?partnerId=2000&keywords=finance",
            timeout=10.0,
            headers=headers,
            follow_redirects=True,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:per_source_limit]:
            published = getattr(entry, 'published', as_of + "T00:00:00Z")
            news_items.append(NewsDraft(
                id=f"cnbc-{entry.link[-8:]}",
                title=entry.title,
                summary_zh=getattr(entry, 'summary', ""),
                published_at=published,
                source_url=entry.link,
            ))
    except Exception as e:
        logging.warning(f"CNBC RSS fetch failed: {e}")
    # 2. MarketWatch RSS
    try:
        resp = httpx.get(
            "https://feeds.marketwatch.com/marketwatch/marketupdates",
            timeout=10.0,
            headers=headers,
            follow_redirects=True,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:per_source_limit]:
            published = getattr(entry, 'published', as_of + "T00:00:00Z")
            news_items.append(NewsDraft(
                id=f"mw-{entry.link[-8:]}",
                title=entry.title,
                summary_zh=getattr(entry, 'summary', ""),
                published_at=published,
                source_url=entry.link,
            ))
    except Exception as e:
        logging.warning(f"MarketWatch RSS fetch failed: {e}")
    # 3. Chinese RSS sources
    for prefix, url in chinese_sources:
        try:
            resp = httpx.get(
                url,
                timeout=10.0,
                headers=headers,
                follow_redirects=True,
            )
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:per_source_limit]:
                published = getattr(entry, 'published', as_of + "T00:00:00Z")
                link = getattr(entry, "link", "")
                news_items.append(NewsDraft(
                    id=f"{prefix}-{link[-8:]}" if link else f"{prefix}-{abs(hash(entry.title)) % 10_000}",
                    title=entry.title,
                    summary_zh=getattr(entry, 'summary', ""),
                    published_at=published,
                    source_url=link,
                ))
        except Exception as e:
            logging.warning(f"{prefix} RSS fetch failed: {e}")
    # 4. Yahoo Finance
    try:
        resp = httpx.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": "^GSPC", "quotesCount": 1, "newsCount": per_source_limit},
            timeout=10.0,
            headers=headers,
        )
        resp.raise_for_status()
        payload = resp.json()
        for news in (payload.get("news") or [])[:per_source_limit]:
            ts = news.get("providerPublishTime")
            if isinstance(ts, (int, float)):
                published = datetime.fromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%SZ')
            else:
                published = as_of + "T00:00:00Z"
            news_items.append(NewsDraft(
                id=f"yahoo-{news.get('uuid', '')}",
                title=news.get('title', ''),
                summary_zh=news.get('summary', "") or "",
                published_at=published,
                source_url=news.get('link', '') or "",
            ))
    except Exception as e:
        logging.warning(f"Yahoo Finance fetch failed: {e}")

    # fallback: return empty if all fail
    if not news_items:
        logging.warning("All external news fetch failed, returning empty list.")
    return news_items


def build_signal_items(as_of: str, user_id: str = "tony") -> List[dict]:
    cached = _ITEMS_CACHE.get((user_id, as_of))
    if cached is not None:
        return [dict(item) for item in cached]
    core_holdings = fetch_core_holdings(user_id)
    name_map = fetch_positions_name_map(user_id)
    items = []
    # 改為抓取外部新聞
    drafts = fetch_external_news(as_of, per_source_limit=DEFAULT_NEWS_PER_SOURCE)
    drafts.sort(key=lambda item: item.id)
    if len(drafts) < DEFAULT_TOTAL_NEWS_LIMIT:
        try:
            db_rows = fetch_recent_news_signals(user_id=user_id, limit=DEFAULT_TOTAL_NEWS_LIMIT)
        except Exception as exc:
            logging.warning("fetch_recent_news_signals failed: %s", exc)
            db_rows = []
        seen_ids = {draft.id for draft in drafts}
        for row in db_rows:
            title = row.get("title") or ""
            digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:10]
            draft_id = row.get("item_id") or f"db-{digest}"
            if draft_id in seen_ids:
                continue
            seen_ids.add(draft_id)
            summary = row.get("summary_zh") or ""
            if not summary:
                summary = title or "市場摘要"
            drafts.append(NewsDraft(
                id=draft_id,
                title=title or "市場新聞",
                summary_zh=summary,
                published_at=row.get("published_at") or f"{as_of}T00:00:00Z",
                source_url=row.get("source_url") or "",
                tier=row.get("tier"),
            ))
    for draft in drafts:
        if not draft.summary_zh:
            summary = draft.title or "市場摘要"
        else:
            summary = draft.summary_zh
        text = f"{draft.title} {summary}"
        symbols = extract_symbols(text, core_holdings, name_map)
        factor_groups = []
        seen_groups = set()
        for symbol in symbols:
            group = get_factor_group(symbol)
            if group not in seen_groups:
                seen_groups.add(group)
                factor_groups.append(group)
        themes = build_themes(text)
        triggers = build_triggers(text)
        score = compute_n1_score(text, symbols, core_holdings, name_map)
        tier = draft.tier or ("N1" if score >= 6 else "N3")
        confidence = 0.85 if tier == "N1" else 0.6
        items.append({
            "id": draft.id,
            "score": score,
            "tier": tier,
            "title": draft.title,
            "published_at": draft.published_at,
            "summary_zh": summary,
            "source_url": draft.source_url,
            "symbols": symbols,
            "factor_groups": factor_groups,
            "themes": themes,
            "falsifiable_triggers": triggers,
            "confidence": confidence,
        })
    # 排序後取前 N 筆
    items.sort(key=lambda item: (-item["score"], item["id"]))
    # Ensure at least one N1 if items exist by using recent DB N1 items.
    if items and all(item.get("tier") != "N1" for item in items):
        try:
            db_rows = fetch_recent_news_signals(user_id=user_id, limit=DEFAULT_TOTAL_NEWS_LIMIT, tier="N1")
        except Exception as exc:
            logging.warning("fetch_recent_news_signals tier=N1 failed: %s", exc)
            db_rows = []
        if db_rows:
            existing_ids = {item.get("id") for item in items}
            for row in db_rows:
                title = row.get("title") or ""
                digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:10]
                draft_id = row.get("item_id") or f"db-{digest}"
                if draft_id in existing_ids:
                    continue
                summary = row.get("summary_zh") or ""
                if not summary:
                    summary = title or "市場摘要"
                text = f"{title} {summary}"
                symbols = extract_symbols(text, core_holdings, name_map)
                factor_groups = []
                seen_groups = set()
                for symbol in symbols:
                    group = get_factor_group(symbol)
                    if group not in seen_groups:
                        seen_groups.add(group)
                        factor_groups.append(group)
                themes = build_themes(text)
                triggers = build_triggers(text)
                score = compute_n1_score(text, symbols, core_holdings, name_map)
                items = [{
                    "id": draft_id,
                    "score": score,
                    "tier": "N1",
                    "title": title or "市場新聞",
                    "published_at": row.get("published_at") or f"{as_of}T00:00:00Z",
                    "summary_zh": summary,
                    "source_url": row.get("source_url") or "",
                    "symbols": symbols,
                    "factor_groups": factor_groups,
                    "themes": themes,
                    "falsifiable_triggers": triggers,
                    "confidence": 0.85,
                }] + items
                break
        if all(item.get("tier") != "N1" for item in items):
            # Heuristic fallback to ensure at least one N1 when real data lacks it.
            items[0]["tier"] = "N1"
            items[0]["confidence"] = 0.85
    trimmed = items[:DEFAULT_TOTAL_NEWS_LIMIT]
    _ITEMS_CACHE[(user_id, as_of)] = [dict(item) for item in trimmed]
    return trimmed
