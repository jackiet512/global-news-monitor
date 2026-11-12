"""区分频道节目表与单篇报道（包括直播文字报道）。"""
import re
from urllib.parse import urlsplit

def schedule(text):
    times = re.findall(r"(?<!\d)\d{1,2}[:：]\d{2}", text)
    return len(times) >= 3 and bool(re.search(
        r"abc\s*(?:news\s*live|新闻直播)|upcoming|节目表|播出安排|now playing", text, re.I))

def channel(site, title, link):
    return site == "美国广播公司" and (
        urlsplit(link).path.rstrip("/") == "/video/41463246"
        or bool(re.search(r"(?:^|[|:\-–])\s*ABC News Live\s*$", title, re.I)))
