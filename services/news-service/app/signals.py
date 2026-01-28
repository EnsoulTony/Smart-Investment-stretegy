"""Deterministic news signals with fixed Sprint 3 rules."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Dict
import os
import httpx

PORTFOLIO_BASE_URL = os.getenv("PORTFOLIO_BASE_URL", "http://portfolio-service:8001")
DEFAULT_CORE_HOLDINGS = ["TSLA", "CCJ", "OXY", "TSM", "URA"]
DEFAULT_NEWS_PER_SOURCE = int(os.getenv("NEWS_SOURCE_LIMIT", "10"))
DEFAULT_TOTAL_NEWS_LIMIT = int(os.getenv("NEWS_TOTAL_LIMIT", "10"))


def fetch_core_holdings(user_id: str) -> List[str]:
    """Fetch core holdings symbols from portfolio-service, fallback to defaults."""
    try:
        url = f"{PORTFOLIO_BASE_URL}/portfolio/core_holdings"
        resp = httpx.get(url, params={"user_id": user_id}, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        symbols = data.get("symbols", []) if isinstance(data, dict) else []
        normalized = [s.upper() for s in symbols]
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
]
TARIFF_KEYWORDS = [
    "關稅", "制裁", "出口管制", "禁令", "實體清單", "貿易戰",
]
WAR_ENERGY_KEYWORDS = [
    "戰爭", "空襲", "封鎖", "油價飆升", "供應中斷", "OPEC",
]
CREDIT_KEYWORDS = [
    "倒閉", "違約", "清算", "挤兑", "信用危機", "流動性危機", "銀行危機",
]
AI_POWER_PRIMARY = [
    "核能", "電網", "供電", "PPA", "GW", "資料中心", "AI超級電腦", "電力需求", "電價",
]
AI_POWER_SECONDARY = [
    "訂單", "供電", "合約", "容量", "電網",
]

MARKET_MECH_KEYWORDS = [
    "大跌", "暴跌", "飆升", "創新高", "創新低", "跳空", "熔斷", "reprice", "pricing in",
]

HUGE_SCALE_REGEX = re.compile(r"\b(\d+(\.\d+)?)(\s?)(GW|兆|十億|Billion|bn)\b", re.IGNORECASE)
SYMBOL_REGEX = re.compile(r"\b[A-Z]{1,5}\b")


@dataclass(frozen=True)
class NewsDraft:
    """Input stub news for deterministic output."""

    id: str
    title: str
    summary_zh: str
    published_at: str
    source_url: str


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


def extract_symbols(text: str, whitelist: List[str]) -> List[str]:
    symbols = [match.group(0) for match in SYMBOL_REGEX.finditer(text)]
    whitelist_set = {s.upper() for s in whitelist}
    filtered = [symbol for symbol in symbols if symbol in whitelist_set]
    seen = set()
    unique_symbols = []
    for symbol in filtered:
        if symbol not in seen:
            seen.add(symbol)
            unique_symbols.append(symbol)
    return unique_symbols


def compute_n1_score(text: str, symbols: List[str], core_holdings: List[str]) -> int:
    score = 0
    if _match_rate(text):
        score += 2
    if _match_tariff(text):
        score += 2
    if _match_war_energy(text):
        score += 2
    if _match_credit(text):
        score += 2
    if _match_ai_power(text):
        score += 2
    if HUGE_SCALE_REGEX.search(text):
        score += 3
    if any(symbol in {s.upper() for s in core_holdings} for symbol in symbols):
        score += 2
    if _match_market_mechanism(text):
        score += 2
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
    return triggers



# 新增：動態抓取外部新聞來源
import feedparser
from datetime import datetime

def fetch_external_news(as_of: str, per_source_limit: int = DEFAULT_NEWS_PER_SOURCE) -> List[NewsDraft]:
    import logging
    news_items = []
    headers = {"User-Agent": "Mozilla/5.0"}
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
    # 3. Yahoo Finance
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

    # fallback stub if all fail
    if not news_items:
        logging.warning("All external news fetch failed, using fallback stub news.")
        fallback_drafts = [
            NewsDraft(
                id="stub-n1-rate-tariff",
                title="FOMC 升息與關稅升溫，市場重新定價",
                summary_zh="TSLA 與 OXY 受政策衝擊，殖利率走高。",
                published_at=as_of + "T00:00:00Z",
                source_url="https://example.com/fallback-n1-1",
            ),
            NewsDraft(
                id="stub-n1-war-energy",
                title="戰爭升溫推升油價飆升，能源股大跌",
                summary_zh="OXY 與 URA 受供應中斷影響，WTI 逼近 90。",
                published_at=as_of + "T00:00:00Z",
                source_url="https://example.com/fallback-n1-2",
            ),
            NewsDraft(
                id="stub-n3-ai-power",
                title="資料中心擴張帶動電力需求",
                summary_zh="AI 供電合約擴大，電網容量與 PPA 訂單增加。",
                published_at=as_of + "T00:00:00Z",
                source_url="https://example.com/fallback-n3-1",
            ),
            NewsDraft(
                id="stub-n3-credit",
                title="區域銀行流動性觀察",
                summary_zh="市場關注信用危機與流動性危機風險。",
                published_at=as_of + "T00:00:00Z",
                source_url="https://example.com/fallback-n3-2",
            ),
            NewsDraft(
                id="stub-n3-growth",
                title="科技股回穩，投資人風險偏好回升",
                summary_zh="TSM 相關供應鏈關注度升高，股價創新高。",
                published_at=as_of + "T00:00:00Z",
                source_url="https://example.com/fallback-n3-3",
            ),
        ]
        desired = max(per_source_limit * 3, DEFAULT_TOTAL_NEWS_LIMIT)
        # Repeat with unique ids to reach desired count
        news_items = []
        for i in range(desired):
            base = fallback_drafts[i % len(fallback_drafts)]
            news_items.append(NewsDraft(
                id=f"{base.id}-{i+1}",
                title=base.title,
                summary_zh=base.summary_zh,
                published_at=base.published_at,
                source_url=base.source_url,
            ))
    return news_items


def build_signal_items(as_of: str, user_id: str = "tony") -> List[dict]:
    core_holdings = fetch_core_holdings(user_id)
    items = []
    # 改為抓取外部新聞
    for draft in fetch_external_news(as_of, per_source_limit=DEFAULT_NEWS_PER_SOURCE):
        text = f"{draft.title} {draft.summary_zh}"
        symbols = extract_symbols(text, core_holdings)
        factor_groups = []
        seen_groups = set()
        for symbol in symbols:
            group = get_factor_group(symbol)
            if group not in seen_groups:
                seen_groups.add(group)
                factor_groups.append(group)
        themes = build_themes(text)
        triggers = build_triggers(text)
        score = compute_n1_score(text, symbols, core_holdings)
        tier = "N1" if score >= 6 else "N3"
        confidence = 0.85 if tier == "N1" else 0.6
        items.append({
            "id": draft.id,
            "score": score,
            "tier": tier,
            "title": draft.title,
            "published_at": draft.published_at,
            "summary_zh": draft.summary_zh,
            "source_url": draft.source_url,
            "symbols": symbols,
            "factor_groups": factor_groups,
            "themes": themes,
            "falsifiable_triggers": triggers,
            "confidence": confidence,
        })
    # 排序後取前 N 筆
    items.sort(key=lambda item: item["score"], reverse=True)
    trimmed = items[:DEFAULT_TOTAL_NEWS_LIMIT]
    return trimmed
