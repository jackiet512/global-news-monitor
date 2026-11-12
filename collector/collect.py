"""RSS candidate collector; feed items are not independently verified facts."""
import hashlib,json,os,sys,time,urllib.request
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit
import feedparser
from display_text import article_url, chinese_text
ROOT=Path(__file__).resolve().parents[1]
SOURCES=json.loads((ROOT/"collector"/"sources.json").read_text(encoding="utf-8"))["sources"]
OUT=Path(os.environ.get("OUTPUT_FILE",ROOT/"collector"/"latest_run.json"))
EDITORIAL=json.loads((ROOT/"worker/src/editorial.json").read_text(encoding="utf-8"))

def relevant(title):
 return any(word in title for word in EDITORIAL["keep"]) or not any(
  all(word in title for word in group) for group in EDITORIAL["exclude"]
 )

def fetch(source):
 req=urllib.request.Request(source["url"],headers={"User-Agent":"GlobalNewsMonitor/1.0"})
 try:
  with urllib.request.urlopen(req,timeout=20) as response: payload=response.read(3000000)
  parsed=feedparser.parse(payload)
  if parsed.bozo and not parsed.entries:return [],str(parsed.bozo_exception)
  items=[]
  for e in parsed.entries[:30]:
   link=e.get("link","").strip();title=chinese_text(e.get("title",""))
   if not article_url(link) or not title or not relevant(title):continue
   published=None
   try:published=parsedate_to_datetime(e.get("published") or e.get("updated")).astimezone(timezone.utc).isoformat()
   except Exception:pass
   summary=chinese_text(e.get("summary",""))[:4000]
   if summary == title or "news.google.com" in source["url"]:
    summary=""  # 聚合源的描述是重复标题和媒体链接。
   body=next((chinese_text(c.value) for c in e.get("content",[]) if c.get("type") in ("text/html","text/plain")), "")
   images=[m.get("url","") for m in e.get("media_thumbnail",[])]
   images.extend(m.get("href","") for m in e.enclosures if m.get("type","").startswith("image/"))
   images.extend(m.get("url","") for m in e.get("media_content",[]) if m.get("medium")=="image" or m.get("type","").startswith("image/"))
   markup=BeautifulSoup(e.get("summary",""),"html.parser")
   photo=markup.find("img",src=True)
   if photo:images.append(urljoin(link,photo["src"]))
   if urlsplit(link).hostname=="www.chinanews.com.cn":
    try:
     with urllib.request.urlopen(link,timeout=3) as response:
      article=BeautifulSoup(response.read(1200000),"html.parser").select_one(".left_zw")
     if article:
      paragraphs=[p.get_text(strip=True) for p in article.select("p") if not p.find("img")]
      body="\n".join(p for p in paragraphs if p.strip() and not p.startswith("【编辑"))
      photo=article.find("img",src=True)
      if photo:images.insert(0,urljoin(link,photo["src"]))
    except (OSError, ValueError):
     pass
   picture=next((v for v in images if article_url(v) and v.startswith("https://")), "")
   short=bool(body and len(body)<=300)
   preview=body if short else summary or body
   if len(preview)>300:preview=preview[:280].rstrip()+"…"
   items.append({"image_url":picture,"reading_text":preview,"short_body":short,"source_name":source["name"],"category":source["category"],"title":title,"url":link,"summary":summary,"published_at":published,"fingerprint":hashlib.sha256(link.encode()).hexdigest(),"verification_status":"待核实","collected_at":datetime.now(timezone.utc).isoformat()})
  return items,None
 except Exception as exc:return [],f"{type(exc).__name__}: {exc}"
def main():
 items=[];errors=[]
 for source in SOURCES:
  if not source.get("enabled"):continue
  found,error=fetch(source);items.extend(found)
  if error:errors.append({"source":source["name"],"error":error})
  time.sleep(.2)
 unique={x["fingerprint"]:x for x in items}
 report={"run_at":datetime.now(timezone.utc).isoformat(),"candidate_count":len(items),"unique_candidate_count":len(unique),"source_error_count":len(errors),"source_errors":errors,"items":sorted(unique.values(),key=lambda x:x.get("published_at") or "",reverse=True),"note":"RSS候选信息，尚未完成多源交叉核验；不得直接视为已确认重大新闻。"}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 endpoint=os.getenv("NEWS_INGEST_URL");token=os.getenv("NEWS_INGEST_TOKEN")
 if endpoint and token:
  data=json.dumps(report,ensure_ascii=False).encode();req=urllib.request.Request(endpoint,data=data,headers={"User-Agent":"GlobalNewsMonitor/1.0","Content-Type":"application/json","Authorization":"Bearer "+token},method="POST")
  with urllib.request.urlopen(req,timeout=90) as response:print("数据库写入结果：",response.read().decode()[:1000])
 else:print("未配置写入地址或令牌，本次仅保存采集文件。")
 return 0
if __name__=="__main__":sys.exit(main())
