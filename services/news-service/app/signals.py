"""Deterministic news signals with fixed Sprint 3 rules."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Dict
import os
import httpx

PORTFOLIO_BASE_URL = os.getenv("PORTFOLIO_BASE_URL", "http://portfolio-service:8001")
DEFAULT_CORE_HOLDINGS = ["TSLA", "CCJ", "OXY", "TSM", "URA"]


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
    return triggers


def build_stub_news(as_of: str) -> List[NewsDraft]:
    return [
        NewsDraft(
            id="stub-001",
            title="Fed 利率決議前夕，10年期殖利率飆升至4.7%，TSLA 大跌",
            summary_zh="市場開始 reprice，交易員認為通膨壓力升溫。",
            published_at=f"{as_of}T09:00:00Z",
            source_url="https://www.federalreserve.gov/newsevents/pressreleases.htm",
        ),
        NewsDraft(
            id="stub-002",
            title="OPEC 封鎖傳聞推升油價飆升，OXY 與 CCJ 大漲",
            summary_zh="供應中斷疑慮升溫，WTI 接近 90。",
            published_at=f"{as_of}T11:30:00Z",
            source_url="https://www.opec.org/opec_web/en/press_room/press_room.htm",
        ),
        NewsDraft(
            id="stub-003",
            title="ECB 討論降息時程，歐股小幅走高",
            summary_zh="市場關注利率決議訊號。",
            published_at=f"{as_of}T12:15:00Z",
            source_url="https://www.ecb.europa.eu/press/pr/date/html/index.en.html",
        ),
        NewsDraft(
            id="stub-004",
            title="美國宣布新增出口管制，影響 AI 伺服器供應鏈",
            summary_zh="部分廠商評估調整庫存與出貨。",
            published_at=f"{as_of}T13:45:00Z",
            source_url="https://www.commerce.gov/news/press-releases",
        ),
        NewsDraft(
            id="stub-005",
            title="核能新訂單帶動電網升級，台灣 1.2 GW 計畫啟動",
            summary_zh="專案聚焦供電容量與合約節點。",
            published_at=f"{as_of}T15:00:00Z",
            source_url="https://www.energy.gov/ne",
        ),
    ]


def build_signal_items(as_of: str, user_id: str = "tony") -> List[dict]:
    core_holdings = fetch_core_holdings(user_id)
    # fallback to empty list ok
    items = []
    for draft in build_stub_news(as_of):
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
    return items
