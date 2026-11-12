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
