"""比较报道中的事件线索，忽略标题语序和常见译法差异。"""
import re
from datetime import datetime

ALIASES = {
    "赫格塞斯": ("赫格斯", "赫格赛斯", "赫格塞思"),
    "斥责": ("训斥", "训诫", "谴责", "批评"),
    "警卫": ("守卫", "哨兵"),
    "团队": ("代表团", "随行人员", "工作人员", "顾问"),
}
STOP = set("the and for from with says after into amid that this news how his her are has more live video over why new their about was its".split())

def signals(original, translated, stamp):
    for standard, aliases in ALIASES.items():
        for alias in aliases:
            translated=translated.replace(alias,standard)
    words={w.rstrip("s") for w in re.findall(r"[a-z]{3,}",original.lower()) if w not in STOP}
    grams={part[i:i+2] for part in re.findall(r"[一-鿿]+",translated) for i in range(len(part)-1)}
    return words,grams,datetime.fromisoformat(stamp)

def same_event(a,b):
    words,grams,stamp=a
    other,chars,time=b
    if abs((stamp-time).total_seconds())>3*86400:return False
    shared=words & other
    common=grams & chars
    en=len(shared)/max(1,min(len(words),len(other)))
    zh=len(common)/max(1,min(len(grams),len(chars)))
    return ((len(shared)>=4 and en>=.60 and len(common)>=3)
            or (len(common)>=6 and zh>=.52)
            or (len(shared)>=3 and en>=.50 and len(common)>=6 and zh>=.33))

def incident_clues(item):
    """标题决定事件类型，报道导语补充地点；避免只因正文提及同一话题就合并。"""
    title=item["title"]
    lead=title+" "+item["reading_text"][:180]
    hour=datetime.fromisoformat(item["published_at"]).timestamp()/3600
    if re.search("枪击|枪杀|枪手",title):
        if "洛根圆环" in lead: return "枪击","华盛顿特区","洛根圆环",hour
        city=re.search(r"华盛顿特区|纽约市|芝加哥|洛杉矶",title)
        if city:return "枪击",city[0],"",hour
    if re.search("炸弹恐吓|炸弹威胁",title) and re.search("学校|校园",title):
        country=re.search("意大利|英国|爱尔兰|德国|法国|加拿大|美国",title)
        if country:return "学校炸弹威胁",country[0],"",hour
    if "弹劾" in title and "投票" in title:
        person=re.search(r"赫格(?:塞斯|斯|赛斯)|特朗普|拜登",title)
        if person:return "弹劾投票",person[0][:2],"",hour
    return None

def matching_incident(a,b):
    if not a or not b or a[:2]!=b[:2]:return False
    if a[2] and b[2] and a[2]!=b[2]:return False
    window=0.5 if a[0]=="枪击" and not (a[2] and b[2]) else 24
    return abs(a[3]-b[3])<=window
