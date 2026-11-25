"""Polymarket Gamma API 概率匹配（免密钥）。"""
import json
import re
import urllib.error
import urllib.request
from difflib import SequenceMatcher

from community import to_english

GAMMA = "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=80"
UA = "GlobalNewsMonitor/1.0"

STOP_EN = {
    "will", "the", "and", "for", "with", "what", "when", "before", "after",
    "president", "market", "world", "global", "news", "says", "report", "china",
    "united", "states", "us", "ai", "model", "new", "year", "month", "from",
    "that", "this", "into", "over", "than", "have", "been", "were", "would",
    "could", "should", "about", "their", "there", "which", "while", "during",
    "2024", "2025", "2026", "2027",
}
STOP_ZH = set("的 了 在 是 与 及 和 对 将 被 有 也 都 而 或 一个 市场 新闻 总统 美国 中国".split())


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _parse_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _fmt_volume(vol):
    try:
        n = float(vol or 0)
    except (TypeError, ValueError):
        return ""
    if n >= 1_000_000:
        return f"${n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"${n / 1_000:.0f}K"
    if n > 0:
        return f"${n:.0f}"
    return ""


def _market_prob(market):
    outcomes = _parse_list(market.get("outcomes"))
    prices = _parse_list(market.get("outcomePrices"))
    if not outcomes or len(outcomes) != len(prices):
        return None
    floats = []
    for p in prices:
        try:
            floats.append(float(p))
        except (TypeError, ValueError):
            return None
    if all(v == 0 for v in floats):
        return None
    if market.get("closed"):
        return None
    for i, name in enumerate(outcomes):
        if str(name).lower() == "yes":
            return {"outcome": "Yes", "probability": round(floats[i] * 100), "question": str(market.get("question") or "")}
    best_i = max(range(len(floats)), key=lambda i: floats[i])
    return {
        "outcome": str(outcomes[best_i]),
        "probability": round(floats[best_i] * 100),
        "question": str(market.get("question") or ""),
    }


def _tokens_en(text):
    return {
        w for w in re.findall(r"[a-z]{3,}", (text or "").lower())
        if w not in STOP_EN and not w.isdigit()
    }


def _tokens_zh(text):
    grams = set()
    for seg in re.findall(r"[一-鿿]+", text or ""):
        grams.update(seg[i : i + 2] for i in range(len(seg) - 1))
    return {g for g in grams if g not in STOP_ZH}


def _en_source(item):
    en = item.get("en_title") or item.get("original_title") or ""
    if len(_tokens_en(en)) < 2:
        title = item.get("title") or en
        if re.search("[一-鿿]", title):
            en = to_english(title) or en
    return en


def fetch_events(timeout=10):
    try:
        return _get(GAMMA, timeout=timeout)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return []


def _event_candidates(events):
    out = []
    for ev in events or []:
        slug = ev.get("slug") or ""
        title = ev.get("title") or ""
        vol = ev.get("volume") or ev.get("volume24hr") or 0
        vol_text = _fmt_volume(vol)
        for mk in ev.get("markets") or []:
            prob = _market_prob(mk)
            if not prob:
                continue
            out.append(
                {
                    "slug": slug,
                    "event_title": title,
                    "question": prob["question"],
                    "outcome": prob["outcome"],
                    "probability": prob["probability"],
                    "volume_text": vol_text,
                    "url": f"https://polymarket.com/event/{slug}" if slug else "",
                    "tokens_en": _tokens_en(title + " " + prob["question"]),
                    "tokens_zh": _tokens_zh(title),
                }
            )
    return out


def match_polymarket(item, events=None, translate=None):
    """为单条新闻匹配最佳 Polymarket 盘口；无命中返回 None。"""
    if events is None:
        events = fetch_events()
    candidates = _event_candidates(events)
    en_source = _en_source(item)
    title = item.get("title") or ""
    news_en = _tokens_en(en_source)
    news_zh = _tokens_zh(title)
    if len(news_en) < 2 and len(news_zh) < 2:
        return None
    best = None
    best_score = 0
    for c in candidates:
        shared_en = news_en & c["tokens_en"]
        shared_zh = news_zh & c["tokens_zh"]
        if len(shared_en) < 2 and len(shared_zh) < 2:
            continue
        score = len(shared_en) + len(shared_zh) * 0.8
        ratio = SequenceMatcher(None, en_source.lower(), c["event_title"].lower()).ratio()
        score += ratio * 0.5
        if score > best_score:
            best_score = score
            event_title = c["event_title"]
            question = c["question"]
            if translate:
                try:
                    event_title = translate(event_title)
                    question = translate(question)
                except (OSError, ValueError):
                    pass
            best = {
                "event_title": event_title,
                "question": question,
                "outcome": c["outcome"],
                "probability": c["probability"],
                "volume_text": c["volume_text"],
                "url": c["url"],
            }
    if best_score < 2:
        return None
    return best


def attach_polymarket(items, translate=None):
    events = fetch_events()
    for item in items:
        item["polymarket"] = match_polymarket(item, events=events, translate=translate)
    return items