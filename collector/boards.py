import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BOARDS = {
    "澎湃新闻": "https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar",
    "中国新闻网": "https://www.chinanews.com.cn/scroll-news/news1.html",
    "IT之家": "https://www.ithome.com/",
}


def read(url):
    request = urllib.request.Request(url, headers={"User-Agent": "GlobalNewsMonitor/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return response.read(3000000)


def entries(site, url):
    raw = read(url)
    if site == "澎湃新闻":
        for row in json.loads(raw)["data"]["hotNews"]:
            when = datetime.fromtimestamp(row["pubTimeLong"]/1000, timezone.utc)
            yield row["name"], "https://www.thepaper.cn/newsDetail_forward_"+row["contId"], row.get("pic",""), when.isoformat()
    else:
        page = BeautifulSoup(raw, "html.parser")
        selector = "#zxrb + .rdph-list a" if site == "中国新闻网" else "#d-1 a"
        for link in page.select(selector):
            yield link.get("title") or link.get_text(strip=True), urljoin(url,link["href"]), "", None


def normalized(title):
    return re.sub(r"[^一-鿿a-z0-9]", "", title.lower())


def duplicate(title, seen):
    for other in seen:
        match = SequenceMatcher(None,title,other,autojunk=False)
        if title == other or match.ratio() >= .70 or (match.find_longest_match().size >= 10 and match.ratio() >= .45):
            return True
    return False


def collect(relevant):
    items, errors, seen, urls = [], [], [], set()
    for site, url in BOARDS.items():
        try:
            candidates=list(entries(site,url))
            if not candidates: raise ValueError("榜单为空")
        except Exception as exc:
            errors.append({"source":site,"error":str(exc)})
            continue
        count=0
        for title, link, image, published in candidates:
            key=normalized(title)
            if not relevant(title) or link in urls or duplicate(key,seen):continue
            body=summary=""
            try:
                page=BeautifulSoup(read(link),"html.parser")
                article=page.select_one("#paragraph, .left_zw, [class*=index_cententWrap]")
                if article:
                    body="\n".join(p.get_text(strip=True) for p in article.select("p") if p.get_text(strip=True))
                    photo=article.select_one("img[src]")
                    if photo and not image:image=urljoin(link,photo["src"])
                meta=page.select_one('meta[name="description"]')
                if meta and site=="IT之家":summary=meta.get("content","")
                stamp=page.select_one("#pubtime,.content_left_time,meta[name=pubdate]")
                if stamp and not published:
                    nums=re.search(r"(20\d\d)\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2}):(\d\d)",stamp.get("content") or stamp.get_text(" ",strip=True))
                    if nums:published=datetime(*map(int,nums.groups()),tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc).isoformat()
            except (OSError, ValueError):
                pass
            short=bool(body and len(body)<=300)
            text=body if short else summary or body
            category="AI与科技" if site=="IT之家" else "社会与突发"
            if re.search("会谈|外交|总统|俄乌|领导人|纪念大会|APEC",title):category="国际政治"
            elif re.search("银行|利率|经济|金融|股市|财报",title):category="全球经济金融"
            items.append(dict(title=title,url=link,source_name=site,category=category,image_url=image,reading_text=text if len(text)<=300 else text[:280]+"…",short_body=short,summary="",published_at=published,collected_at=datetime.now(timezone.utc).isoformat(),verification_status="待核实",fingerprint=hashlib.sha256(link.encode()).hexdigest()))
            urls.add(link);seen.append(key);count+=1
            if count==10:break
    return items,errors
