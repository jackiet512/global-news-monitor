"""为已经入选的新闻补充来自发布方的正文段落。"""
import ipaddress
import json
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from googlenewsdecoder import gnewsdecoder
from trafilatura import extract
from programme import channel, schedule


def _ip_blocked(addr):
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _hostname_blocked(hostname):
    if not hostname:
        return True
    host = hostname.lower().strip(".")
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or host.endswith(".localhost"):
        return True
    if host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        addr = ipaddress.ip_address(host)
        return _ip_blocked(addr)
    except ValueError:
        pass
    return False


def _url_allowed(link, require_https=False):
    parts = urlsplit(link)
    if require_https:
        if parts.scheme != "https":
            return False
    elif parts.scheme not in ("http", "https"):
        return False
    host = parts.hostname or ""
    if _hostname_blocked(host):
        return False
    try:
        for _, _, _, _, sockaddr in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM):
            ip = sockaddr[0]
            try:
                if _ip_blocked(ipaddress.ip_address(ip)):
                    return False
            except ValueError:
                continue
    except OSError:
        pass
    return True


def preview(body, translate):
    paragraphs = list(dict.fromkeys(line.strip() for line in body.splitlines() if line.strip()))
    if not paragraphs:
        return "", False
    source = "\n".join(paragraphs)
    chunk = source[:2200]
    if len(source) > len(chunk):
        boundary = max(chunk.rfind(c) for c in "。！？.!?\n")
        if boundary > 0:
            chunk = chunk[: boundary + 1]
    translated = translate(chunk).strip()
    if len(translated) <= 300:
        return translated, chunk == source
    sentences = re.split(r"(?<=[。！？])|\n+", translated)
    result = ""
    for sentence in sentences:
        result += sentence
        if len(result) >= 210:
            break
    return result if len(result) <= 420 else result[:400] + "…", False


def enrich(items, sites, read, translate):
    def visit(item):
        try:
            link = item["url"]
            if urlsplit(link).hostname == "news.google.com":
                resolved = gnewsdecoder(link, timeout=8)
                link = resolved.get("decoded_url", "")
            host = urlsplit(link).hostname or ""
            source = item.get("source_name", "")
            if source == "Hacker News":
                if not _url_allowed(link, require_https=True):
                    return
                if host.endswith("ycombinator.com") or not link.startswith("https://"):
                    return
            else:
                if source not in sites:
                    return
                allowed = {sites[source][0]}
                if source == "英国广播公司":
                    allowed.add("bbc.co.uk")
                if source == "美国广播公司":
                    allowed.add("abcnews.go.com")
                if not any(host == domain or host.endswith("." + domain) for domain in allowed):
                    return
            if not urlsplit(link).path.strip("/") and source != "Hacker News":
                return
            if channel(source, "", link):
                item["channel_page"] = True
                return
            item["url"] = link
            html = read(link)
            page = BeautifulSoup(html, "html.parser")
            container = (
                page.select_one("#detail")
                if source == "新华网"
                else page.select_one("#ozoom, #articleContent, .article-box .article")
                if source == "人民日报"
                else None
            )
            image = page.select_one('meta[property="og:image"],meta[itemprop="thumbnailUrl"]')
            picture = image.get("content", "") if image else ""
            if not picture and container:
                image = container.select_one("img[src]")
                picture = image.get("src", "") if image else ""
            if picture and not item.get("image_url"):
                url = urljoin(link, picture)
                if url.startswith("https://"):
                    item["image_url"] = url
            candidates = []
            if container:
                candidates.append("\n".join(p.get_text(strip=True) for p in container.select("p")))
            for script in page.select('script[type="application/ld+json"]'):
                try:
                    data = json.loads(script.get_text())
                except ValueError:
                    continue
                nodes = data if isinstance(data, list) else [data]
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    nodes.extend(node.get("@graph", []) if isinstance(node.get("@graph"), list) else [])
                    if isinstance(node.get("articleBody"), str):
                        candidates.append(BeautifulSoup(node["articleBody"], "html.parser").get_text(" ", strip=True))
            candidates.append(extract(html, include_comments=False, include_tables=False, favor_precision=True) or "")
            body = next((value for value in candidates if value.strip() and not schedule(value)), "")
            lines = [
                line
                for line in body.splitlines()
                if not re.match(
                    r"^(?:责编[：:]|责任编辑[：:]|正在播放$|来自香港$|• 来源|ABC News Live is)",
                    line.strip(),
                    re.I,
                )
            ]
            body = "\n".join(lines).strip()
            meta = page.select_one('meta[property="og:description"],meta[name="description"]')
            description = meta.get("content", "").strip() if meta else ""
            if not schedule(description) and len(body) < 100 and len(description) > len(body):
                body = description
            text, complete = preview(body, translate)
            if text and text.strip() != item["title"] and (complete or len(text) > len(item.get("reading_text") or "")):
                item["reading_text"] = text
                item["short_body"] = (
                    complete
                    and bool(container or any(n.strip() for n in candidates[:-1]))
                    and body != description
                )
        except Exception as exc:
            print("原文补充失败", item.get("source_name"), type(exc).__name__)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(visit, items))