"""Hacker News 热榜采集（Algolia 免密钥 API）。"""
import hashlib
import html
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

UA = "GlobalNewsMonitor/1.0"
FRONT = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=35"
STORY = "https://hn.algolia.com/api/v1/search?tags=story&numericFilters=created_at_i>{cutoff}&hitsPerPage=35"
ITEM = "https://hn.algolia.com/api/v1/items/{oid}"
DISCUSS = "https://news.ycombinator.com/item?id={oid}"
BJ = timezone(timedelta(hours=8))


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _public_url(hit):
    raw = (hit.get("url") or "").strip()
    if raw:
        p = urlparse(raw)
        if p.scheme in ("http", "https") and p.netloc:
            return raw
    oid = hit.get("objectID") or hit.get("story_id")
    return DISCUSS.format(oid=oid) if oid else ""


def _score(hit):
    return int(hit.get("points") or 0) + 2 * int(hit.get("num_comments") or 0)


def _category(title_en, title_zh):
    for pat, cat in [
        (r"外交|总统|议会|大选|军队|战争|会谈|部长", "国际政治"),
        (r"利率|股市|经济|财报|银行", "全球经济金融"),
    ]:
        if re.search(pat, title_zh):
            return cat
    return "AI与科技"


def _bj_iso(stamp):
    try:
        text = (stamp or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BJ).isoformat()


def _strip_html(text):
    if not text:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip()


def top_comments(oid, translate, limit=2, timeout=10):
    try:
        data = _get(ITEM.format(oid=oid), timeout=timeout)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return []
    children = data.get("children") or []
    ranked = sorted(
        (c for c in children if (c.get("type") or "") == "comment" and c.get("text")),
        key=lambda c: int(c.get("points") or 0),
        reverse=True,
    )
    out = []
    for node in ranked[:limit]:
        author = (node.get("author") or "anonymous").strip()
        text = _strip_html(node.get("text") or "")
        if len(text) > 320:
            text = text[:300] + "…"
        try:
            text = translate(text)
        except (OSError, ValueError):
            pass
        out.append({"author": author, "text": f"@{author}: {text}"})
    return out


def _hn_community(hit, oid, title_zh, translate):
    story = {
        "title": title_zh,
        "points": int(hit.get("points") or 0),
        "num_comments": int(hit.get("num_comments") or 0),
        "discussion_url": DISCUSS.format(oid=oid),
        "url": (hit.get("url") or "").strip(),
    }
    comments = top_comments(oid, translate)
    if comments:
        story["comments"] = comments
    return {"hn": [story]}


def collect_hn(translate, chinese, limit=5, min_score=8):
    hits = []
    try:
        data = _get(FRONT)
        hits = data.get("hits") or []
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        hits = []
    if not hits:
        cutoff = int((datetime.now(timezone.utc) - timedelta(days=3)).timestamp())
        try:
            data = _get(STORY.format(cutoff=cutoff))
            hits = data.get("hits") or []
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
            return [], "unavailable"
    seen = set()
    ranked = sorted(hits, key=_score, reverse=True)
    items = []
    status = "ok"
    for hit in ranked:
        if len(items) >= limit:
            break
        if _score(hit) < min_score:
            continue
        oid = str(hit.get("objectID") or hit.get("story_id") or "")
        if not oid or oid in seen:
            continue
        url = _public_url(hit)
        if not url:
            continue
        original = (hit.get("title") or hit.get("story_title") or "").strip()
        if not original:
            continue
        try:
            title = chinese(original)
        except (OSError, ValueError):
            continue
        stamp = _bj_iso(hit.get("created_at"))
        cat = _category(original, title)
        hn_meta = {
            "object_id": oid,
            "points": int(hit.get("points") or 0),
            "num_comments": int(hit.get("num_comments") or 0),
            "discussion_url": DISCUSS.format(oid=oid),
        }
        community = _hn_community(hit, oid, title, translate)
        items.append(
            dict(
                title=title,
                original_title=original,
                en_title=original,
                url=url,
                source_name="Hacker News",
                category=cat,
                image_url="",
                reading_text="",
                short_body=False,
                summary="",
                published_at=stamp,
                hn_meta=hn_meta,
                community=community,
                fingerprint=hashlib.sha256(url.encode()).hexdigest(),
            )
        )
        seen.add(oid)
    if not items:
        status = "empty"
    return items, status