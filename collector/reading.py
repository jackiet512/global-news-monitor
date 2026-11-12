"""为已经入选的新闻补充来自发布方的正文段落。"""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from googlenewsdecoder import gnewsdecoder
from trafilatura import extract


def preview(body, translate):
    paragraphs = list(dict.fromkeys(line.strip() for line in body.splitlines() if line.strip()))
    if not paragraphs:
        return "", False
    source = "\n".join(paragraphs)
    # 外文译成中文后往往短很多。先取足量原文，再在完整句子处结束。
    chunk = source[:2200]
    if len(source) > len(chunk):
        boundary = max(chunk.rfind(c) for c in "。！？.!?\n")
        if boundary > 0:
            chunk = chunk[:boundary + 1]
    translated = translate(chunk).strip()
    if len(translated) <= 300:
        return translated, chunk == source
    sentences = re.split(r"(?<=[。！？])|\n+", translated)
    result = ""
    for sentence in sentences:
        result += sentence
        if len(result) >= 210:
            break
    return result if len(result)<=420 else result[:400]+"…", False


def enrich(items, sites, read, translate):
    def visit(item):
        try:
            link = item["url"]
            if urlsplit(link).hostname == "news.google.com":
                resolved = gnewsdecoder(link, timeout=8)
                link = resolved.get("decoded_url","")
            host = urlsplit(link).hostname or ""
            allowed = {sites[item["source_name"]][0]}
            if item["source_name"] == "英国广播公司":
                allowed.add("bbc.co.uk")
            if item["source_name"] == "美国广播公司":
                allowed.add("abcnews.go.com")
            if not any(host==domain or host.endswith("."+domain) for domain in allowed):
                return
            html = read(link)
            body = extract(html, include_comments=False, include_tables=False, favor_precision=True) or ""
            text, complete = preview(body, translate)
            if text and (complete or len(text)>len(item["reading_text"])):
                item["reading_text"]=text
                item["short_body"]=complete
            image = BeautifulSoup(html,"html.parser").select_one('meta[property="og:image"]')
            if not item["image_url"] and image and image.get("content","").startswith("https://"):
                item["image_url"]=image["content"]
            item["url"]=link
        except Exception as exc:
            print("原文补充失败",item["source_name"],type(exc).__name__)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(visit,items))
