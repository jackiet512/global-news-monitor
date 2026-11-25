"""HN / Reddit 社区讨论脉络检索（免密钥，故障隔离）。"""
import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from urllib.parse import quote, urlencode

UA = "GlobalNewsMonitor/1.0 (+https://github.com/jackiet512/global-news-monitor)"
HN_SEARCH = "https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=5&query={q}"
REDDIT = "https://www.reddit.com/search.json?q={q}&sort=relevance&t=month&limit=5&raw_json=1"

STOP = set(
    "the and for with from after says over into that this news live video what about amid their than have was how who more has new his her are its will president market".split()
)

_EN_CACHE: dict[str, str] = {}


def _http_get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status in (403, 429):
            raise urllib.error.HTTPError(url, resp.status, "rate limit", resp.headers, None)
        return json.loads(resp.read())


def to_english(text, read=None):
    """中文标题译英（免密钥 Google 翻译接口，带内存缓存）。"""
    text = (text or "").strip()
    if not text or not re.search("[一-鿿]", text):
        return text
    if text in _EN_CACHE:
        return _EN_CACHE[text]
    try:
        args = urlencode(dict(client="gtx", sl="auto", tl="en", dt="t", q=text))
        url = "https://translate.googleapis.com/translate_a/single?" + args
        if read:
            raw = read(url)
        else:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
        rows = json.loads(raw)[0]
        result = "".join(row[0] for row in rows if row and row[0]).strip() or text
        _EN_CACHE[text] = result
        return result
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError, IndexError, TypeError):
        return text


def ensure_en_titles(items, read=None):
    for item in items:
        if item.get("en_title"):
            continue
        orig = item.get("original_title") or item.get("title") or ""
        if len(re.findall(r"[a-z]{4,}", orig.lower())) >= 2:
            item["en_title"] = orig
        elif re.search("[一-鿿]", orig) or re.search("[一-鿿]", item.get("title") or ""):
            item["en_title"] = to_english(item.get("title") or orig, read=read)
        else:
            item["en_title"] = orig


def query_terms(item, limit=6):
    en = item.get("en_title") or item.get("original_title") or ""
    if len(re.findall(r"[a-z]{4,}", en.lower())) < 3:
        title = item.get("title") or en
        if re.search("[一-鿿]", title):
            en = to_english(title) or en
    words = [w for w in re.findall(r"[a-z]{4,}", en.lower()) if w not in STOP]
    seen = []
    for w in words:
        if w not in seen:
            seen.append(w)
        if len(seen) >= limit:
            break
    return seen


def _hn_discussions(query, timeout=8):
    url = HN_SEARCH.format(q=quote(query))
    try:
        data = _http_get(url, timeout=timeout)
    except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None
    out = []
    for hit in data.get("hits") or []:
        oid = hit.get("objectID") or hit.get("story_id")
        title = (hit.get("title") or hit.get("story_title") or "").strip()
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
        data = _http_get(url, timeout=timeout)
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


def search_community(query):
    hn = _hn_discussions(query)
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


def enrich_items(items, translate=None, max_workers=4, budget=12, max_items=12):
    """为全部条目生成 query_terms；仅前 max_items 条预检索社区脉络。"""
    ensure_en_titles(items)
    for item in items:
        item["query_terms"] = query_terms(item)
    errors = []

    def work(item):
        q = " ".join(item["query_terms"][:5])
        if not q.strip():
            return item, None
        try:
            result = search_community(q)
            existing = item.get("community") or {}
            merged = dict(existing)
            if result["hn"]:
                merged["hn"] = (existing.get("hn") or []) + [
                    x
                    for x in result["hn"]
                    if x.get("discussion_url")
                    and not any(y.get("discussion_url") == x.get("discussion_url") for y in (existing.get("hn") or []))
                ]
            if result["reddit"]:
                merged["reddit"] = result["reddit"]
            item["community"] = merged
            item["source_status"] = result.get("source_status", {})
            return item, None
        except Exception as exc:
            return item, str(exc)

    pool = ThreadPoolExecutor(max_workers=max_workers)
    futures = [pool.submit(work, item) for item in items[:max_items]]
    try:
        for fut in as_completed(futures, timeout=budget):
            try:
                _, err = fut.result()
                if err:
                    errors.append(err)
            except Exception as exc:
                errors.append(str(exc))
    except FuturesTimeoutError:
        errors.append("community enrich timeout")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return items, errors