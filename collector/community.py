"""HN / Reddit 社区讨论脉络检索（免密钥，故障隔离）。"""
import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

UA = "GlobalNewsMonitor/1.0 (+https://github.com/jackiet512/global-news-monitor)"
HN_SEARCH = "https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=5&query={q}"
REDDIT = "https://www.reddit.com/search.json?q={q}&sort=relevance&t=month&limit=5&raw_json=1"

STOP = set(
    "the and for with from after says over into that this news live video what about amid their than have was how who more has new his her are its will president market".split()
)


def _get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status in (403, 429):
            raise urllib.error.HTTPError(url, resp.status, "rate limit", resp.headers, None)
        return json.loads(resp.read())


def query_terms(item, limit=6):
    original = item.get("original_title") or item.get("title") or ""
    words = [w for w in re.findall(r"[a-z]{4,}", original.lower()) if w not in STOP]
    if len(words) < 3:
        title = item.get("title") or ""
        for seg in re.findall(r"[一-鿿]{2,}", title):
            words.append(seg)
    seen = []
    for w in words:
        if w not in seen:
            seen.append(w)
        if len(seen) >= limit:
            break
    return seen[:limit] if len(seen) >= 3 else seen


def _hn_discussions(query, translate=None, timeout=8):
    url = HN_SEARCH.format(q=quote(query))
    try:
        data = _get(url, timeout=timeout)
    except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None
    out = []
    for hit in data.get("hits") or []:
        oid = hit.get("objectID") or hit.get("story_id")
        title = (hit.get("title") or hit.get("story_title") or "").strip()
        if translate:
            try:
                title = translate(title)
            except (OSError, ValueError):
                pass
        link = (hit.get("url") or "").strip()
        out.append(
            {
                "title": title,
                "points": int(hit.get("points") or 0),
                "num_comments": int(hit.get("num_comments") or 0),
                "discussion_url": f"https://news.ycombinator.com/item?id={oid}" if oid else "",
                "url": link,
            }
        )
    return out


def _reddit_discussions(query, timeout=8):
    url = REDDIT.format(q=quote(query))
    try:
        data = _get(url, timeout=timeout)
    except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None
    out = []
    for child in (data.get("data") or {}).get("children") or []:
        post = child.get("data") or {}
        permalink = post.get("permalink") or ""
        out.append(
            {
                "subreddit": post.get("subreddit") or "",
                "title": post.get("title") or "",
                "score": int(post.get("score") or 0),
                "num_comments": int(post.get("num_comments") or 0),
                "url": f"https://www.reddit.com{permalink}" if permalink else "",
            }
        )
    return out


def search_community(query, translate=None):
    hn = _hn_discussions(query, translate=translate)
    reddit = _reddit_discussions(query)
    status = {
        "hn": "ok" if hn else "unavailable",
        "reddit": "ok" if reddit else "unavailable",
    }
    if hn is not None and not hn:
        status["hn"] = "empty"
    if reddit is not None and not reddit:
        status["reddit"] = "empty"
    return {
        "hn": hn or [],
        "reddit": reddit or [],
        "source_status": status,
    }


def enrich_items(items, translate=None, max_workers=4, budget=12):
    """为新闻条目附加 community 与 query_terms；异常不抛出。"""
    terms_map = {id(item): query_terms(item) for item in items}
    for item in items:
        item["query_terms"] = terms_map[id(item)]
    errors = []

    def work(item):
        q = " ".join(terms_map[id(item)][:5])
        if not q.strip():
            return item, None
        try:
            result = search_community(q, translate=translate)
            existing = item.get("community") or {}
            merged = dict(existing)
            if result["hn"]:
                merged["hn"] = (existing.get("hn") or []) + [
                    x for x in result["hn"] if x not in (existing.get("hn") or [])
                ]
            if result["reddit"]:
                merged["reddit"] = result["reddit"]
            item["community"] = merged
            item["source_status"] = result.get("source_status", {})
            return item, None
        except Exception as exc:
            return item, str(exc)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(work, item) for item in items]
        for fut in as_completed(futures, timeout=budget):
            try:
                _, err = fut.result()
                if err:
                    errors.append(err)
            except Exception as exc:
                errors.append(str(exc))
    return items, errors