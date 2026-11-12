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

from boards import collect

def main():
 items,errors=collect(relevant)
 if not items:raise RuntimeError("未取得热榜，保留上一轮结果")
 unique={x["fingerprint"]:x for x in items}
 report={"ranked":True,"run_at":datetime.now(timezone.utc).isoformat(),"candidate_count":len(items),"unique_candidate_count":len(unique),"source_error_count":len(errors),"source_errors":errors,"items":sorted(unique.values(),key=lambda x:x.get("published_at") or "",reverse=True),"note":"RSS候选信息，尚未完成多源交叉核验；不得直接视为已确认重大新闻。"}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 endpoint=os.getenv("NEWS_INGEST_URL");token=os.getenv("NEWS_INGEST_TOKEN")
 if endpoint and token:
  data=json.dumps(report,ensure_ascii=False).encode();req=urllib.request.Request(endpoint,data=data,headers={"User-Agent":"GlobalNewsMonitor/1.0","Content-Type":"application/json","Authorization":"Bearer "+token},method="POST")
  with urllib.request.urlopen(req,timeout=90) as response:print("数据库写入结果：",response.read().decode()[:1000])
 else:print("未配置写入地址或令牌，本次仅保存采集文件。")
 return 0
if __name__=="__main__":sys.exit(main())
