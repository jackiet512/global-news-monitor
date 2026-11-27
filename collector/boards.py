"""从媒体要闻订阅或指定媒体的新闻索引选稿。"""
import calendar
import hashlib
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from urllib.parse import urlencode, urlsplit

from reading import enrich
from events import signals, same_event, incident_clues, matching_incident
from headlines import publication_metadata
from programme import channel, schedule
from hackernews import collect_hn
from polymarket import attach_polymarket
from sports import is_sports_news
from community import enrich_items, ensure_en_titles, to_english
import feedparser
from bs4 import BeautifulSoup

SITES = {
    "路透社": ("reuters.com", ""),
    "英国广播公司": ("bbc.com", "https://feeds.bbci.co.uk/news/rss.xml"),
    "美国有线电视新闻网": ("cnn.com", ""),
    "哥伦比亚广播公司": ("cbsnews.com", "https://www.cbsnews.com/latest/rss/main"),
    "美联社": ("apnews.com", ""),
    "凤凰卫视": ("v.ifeng.com", ""),
    "新华网": ("news.cn", ""),
    "人民日报": ("paper.people.com.cn", ""),
    "美国广播公司": ("abcnews.com", "https://abcnews.go.com/abcnews/topstories"),
    "福克斯新闻": ("foxnews.com", "https://feeds.foxnews.com/foxnews/latest"),
}
BJ = timezone(timedelta(hours=8))
def read(url):
    req = urllib.request.Request(url, headers={"User-Agent":"GlobalNewsMonitor/1.0"})
    with urllib.request.urlopen(req,timeout=12) as response:
        return response.read(4000000)

def chinese(text):
    if not text or re.search("[一-鿿]", text):return text
    args=urlencode(dict(client="gtx",sl="auto",tl="zh-CN",dt="t",q=text))
    rows=json.loads(read("https://translate.googleapis.com/translate_a/single?"+args))[0]
    return "".join(row[0] for row in rows if row[0])

def fetch(pair):
    name,(domain,feed)=pair
    cn=name in ("凤凰卫视","新华网","人民日报")
    index="https://news.google.com/rss/search?"+urlencode(dict(q="site:"+domain+(" 凤凰卫视" if name=="凤凰卫视" else "")+" when:7d",hl="zh-CN" if cn else "en-US",gl="CN" if cn else "US",ceid="CN:zh-Hans" if cn else "US:en"))
    for url in filter(None,(feed,index)):
        try:
            rows=feedparser.parse(read(url)).entries
            result=[]
            for row in rows:
                indexed=url==index
                host=urlsplit(row.get("source",{}).get("href","") if indexed else row.link).hostname or ""
                if not (host==domain or host.endswith("."+domain) or domain.endswith("."+host) or (domain=="bbc.com" and host.endswith(".bbc.co.uk"))):continue
                stamp=row.get("published_parsed")
                if not stamp:continue
                title=row.title.rsplit(" - ",1)[0] if indexed else row.title
                summary="" if indexed else BeautifulSoup(row.get("summary",""),"html.parser").get_text(" ",strip=True)[:300]
                media=row.get("media_thumbnail") or row.get("media_content") or []
                result.append((title,row.link,summary,media[0].get("url","") if media else "",datetime.fromtimestamp(calendar.timegm(stamp),BJ).replace(microsecond=0).isoformat(timespec="seconds")))
            if result:return result
        except (OSError,ValueError):continue
    return []

def duplicate(key,seen):
    for other in seen:
        m=SequenceMatcher(None,key,other,autojunk=False)
        if key==other or m.ratio()>=.65 or (m.find_longest_match().size>=9 and m.ratio()>=.42):return True
    return False

def terms(title):
    words=set(re.findall(r"[a-z]{3,}",title.lower()))-set("the and for with from after says over into that this news live video what about amid their than have was how who more has new his her are its".split())
    for segment in re.findall(r"[一-鿿]+",title):
        words.update(segment[i:i+2] for i in range(len(segment)-1))
    return words

def coverage(tokens, other_sites):
    score=0
    for site in other_sites:
        best=max((len(tokens & other)/max(len(tokens | other),1) for other in site if len(tokens & other)>=2),default=0)
        if best>=.13:score+=best
    return score

def collect(relevant):
    seen=set();urls=set();items=[];errors=[]
    with ThreadPoolExecutor(max_workers=10) as pool:
        boards=list(pool.map(fetch,SITES.items()))
    events=[]
    selected_clues=[]
    signatures=[[terms(row[0]) for row in board] for board in boards]
    for i in sorted(range(len(boards)),key=lambda i:not bool(list(SITES.values())[i][1])):
        name=list(SITES)[i]
        rows=boards[i]
        # 同一话题被多个媒体关注时提高优先级，同分沿用来源顺序。
        others=signatures[:i]+signatures[i+1:]
        ranked=sorted(enumerate(rows),key=lambda pair:coverage(signatures[i][pair[0]],others),reverse=True)
        rows=[row for _,row in ranked]
        count=0
        for title,link,summary,image,stamp in rows[:35]:
            if publication_metadata(title) or link in urls or channel(name,title,link):continue
            original=title
            if is_sports_news(original_title=original, url=link):continue
            try:title=chinese(title)
            except (OSError,ValueError):continue
            key=re.sub(r"[^一-鿿a-z0-9]","",title.lower())
            if not key or publication_metadata(title) or not relevant(title) or duplicate(key,seen):continue
            if is_sports_news(title=title, original_title=original, url=link, summary=summary):continue
            event=signals(original,title,stamp)
            if any(same_event(event,previous) for previous in events):continue
            try:summary="" if schedule(summary) else chinese(summary)
            except (OSError,ValueError):summary=""
            cat="社会与突发"
            for pattern,category in [("外交|总统|议会|大选|军队|战争|会谈|部长","国际政治"),("利率|股市|经济|财报|银行","全球经济金融"),("芯片|科技|人工智能|机器人|航天","AI与科技")]:
                if re.search(pattern,title):cat=category;break
            en_title=original if re.search(r"[a-z]{4,}", original.lower()) else (to_english(title) if re.search("[一-鿿]", title) else original)
            item=dict(title=title,original_title=original,en_title=en_title,url=link,source_name=name,category=cat,image_url=image,reading_text=summary,short_body=False,summary=summary,published_at=stamp,collected_at=datetime.now(BJ).replace(microsecond=0).isoformat(timespec="seconds"),verification_status="待核实",fingerprint=hashlib.sha256(link.encode()).hexdigest())
            clue=incident_clues(item)
            if any(matching_incident(clue,old) for old in selected_clues):continue
            selected_clues.append(clue)
            items.append(item)
            events.append(event)
            seen.add(key);urls.add(link);count+=1
            if count==5:break
        if count<5:errors.append(dict(source=name,error=f"本轮取得 {count} 条可展示新闻"))
    try:
        hn_items, hn_status = collect_hn(chinese, chinese, limit=5)
        if hn_status == "unavailable":
            errors.append(dict(source="Hacker News", error="HN Algolia 不可用"))
        for row in hn_items:
            row["collected_at"] = datetime.now(BJ).replace(microsecond=0).isoformat(timespec="seconds")
            row["verification_status"] = "待核实"
            key = re.sub(r"[^一-鿿a-z0-9]", "", row["title"].lower())
            if not key or duplicate(key, seen):
                continue
            event = signals(row["original_title"], row["title"], row["published_at"])
            if any(same_event(event, previous) for previous in events):
                continue
            items.append(row)
            events.append(event)
            seen.add(key)
            urls.add(row["url"])
    except Exception:
        errors.append(dict(source="Hacker News", error="HN 热榜采集异常"))
    enrich(items, SITES, read, chinese)
    ensure_en_titles(items, read=read)
    try:
        attach_polymarket(items, translate=chinese)
    except Exception:
        errors.append(dict(source="Polymarket", error="盘口匹配异常"))
    try:
        enrich_items(items, translate=chinese)
    except Exception:
        errors.append(dict(source="Community", error="社区脉络检索异常"))
    return [item for item in items if not item.get("channel_page")], errors
