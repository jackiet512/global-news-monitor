"""RSS candidate collector; feed items are not independently verified facts."""
import hashlib,json,os,sys,time,urllib.request
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import feedparser
ROOT=Path(__file__).resolve().parents[1]
SOURCES=json.loads((ROOT/"collector"/"sources.json").read_text(encoding="utf-8"))["sources"]
OUT=Path(os.environ.get("OUTPUT_FILE",ROOT/"collector"/"latest_run.json"))
def fetch(source):
 req=urllib.request.Request(source["url"],headers={"User-Agent":"GlobalNewsMonitor/1.0"})
 try:
  with urllib.request.urlopen(req,timeout=20) as response: payload=response.read(3000000)
  parsed=feedparser.parse(payload)
  if parsed.bozo and not parsed.entries:return [],str(parsed.bozo_exception)
  items=[]
  for e in parsed.entries[:30]:
   link=e.get("link","").strip();title=e.get("title","").strip()
   if not link or not title:continue
   published=None
   try:published=parsedate_to_datetime(e.get("published") or e.get("updated")).astimezone(timezone.utc).isoformat()
   except Exception:pass
   items.append({"source_name":source["name"],"category":source["category"],"title":title,"url":link,"summary":e.get("summary","")[:4000],"published_at":published,"fingerprint":hashlib.sha256(link.encode()).hexdigest(),"verification_status":"待核实","collected_at":datetime.now(timezone.utc).isoformat()})
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
  with urllib.request.urlopen(req,timeout=25) as response:print("D1 ingest:",response.read().decode()[:1000])
 else:print("D1 ingestion skipped: missing NEWS_INGEST_URL / NEWS_INGEST_TOKEN; artifact only.")
 return 0
if __name__=="__main__":sys.exit(main())
