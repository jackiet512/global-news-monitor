"""比较报道中的事件线索，忽略标题语序和常见译法差异。"""
import re
from datetime import datetime

ALIASES = {
    "赫格塞斯": ("赫格斯", "赫格赛斯", "赫格塞思"),
    "斥责": ("训斥", "训诫", "谴责", "批评"),
    "警卫": ("守卫", "哨兵"),
    "团队": ("代表团", "随行人员", "工作人员", "顾问"),
    "丧生": ("死亡", "身亡", "遇难", "致死", "毙命"),
    "风暴": ("大风暴", "暴风雨", "强风暴"),
    "导致": ("带来", "造成", "引发", "致使"),
    "袭击": ("袭击事件", "空袭", "无人机袭击"),
    "否认": ("驳斥", "拒绝承认"),
    "指控": ("指责", "控告"),
}
STOP = set("the and for from with says after into amid that this news how his her are has more live video over why new their about was its".split())
ZH_STOP = set("的在中给被对此和与、，了将称表示强大")
CONFLICT_GROUPS = (
    ("法国", "意大利", "日本", "德国", "英国", "爱尔兰", "加拿大", "美国", "科威特", "伊朗", "中国", "俄罗斯", "乌克兰", "以色列"),
    ("OpenAI", "Anthropic", "谷歌", "微软", "苹果", "亚马逊"),
    ("美联储", "欧洲央行", "日本央行", "英国央行"),
)


def _normalize_zh(text):
    norm = text
    for standard, aliases in ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            norm = norm.replace(alias, standard)
    return norm


def _zh_bigrams(text):
  grams = set()
  for part in re.findall(r"[一-鿿]+", text):
    clean = "".join(c for c in part if c not in ZH_STOP)
    grams.update(clean[i : i + 2] for i in range(len(clean) - 1))
  return grams


def _entities(text):
    found = []
    for group in CONFLICT_GROUPS:
        for entity in group:
            if entity in text:
                found.append((group, entity))
    return found


def has_entity_conflict(text_a, text_b):
    ents_a = _entities(text_a)
    ents_b = _entities(text_b)
    for group in CONFLICT_GROUPS:
        in_a = {e for g, e in ents_a if g == group}
        in_b = {e for g, e in ents_b if g == group}
        if in_a and in_b and not (in_a & in_b):
            return True
    return False


def signals(original, translated, stamp):
    norm = _normalize_zh(translated)
    words = {w.rstrip("s") for w in re.findall(r"[a-z]{3,}", original.lower()) if w not in STOP}
    grams = _zh_bigrams(norm)
    return words, grams, datetime.fromisoformat(stamp), norm


def same_event(a, b):
    words, grams, stamp = a[0], a[1], a[2]
    other, chars, time = b[0], b[1], b[2]
    norm_a = a[3] if len(a) > 3 else ""
    norm_b = b[3] if len(b) > 3 else ""
    if abs((stamp - time).total_seconds()) > 3 * 86400:
        return False
    if norm_a and norm_b and has_entity_conflict(norm_a, norm_b):
        return False
    shared = words & other
    common = grams & chars
    en = len(shared) / max(1, min(len(words), len(other)))
    zh = len(common) / max(1, min(len(grams), len(chars)))
    if len(common) >= 4 and zh >= 0.40:
        return True
    return (
        (len(shared) >= 4 and en >= 0.60 and len(common) >= 3)
        or (len(common) >= 6 and zh >= 0.52)
        or (len(shared) >= 3 and en >= 0.50 and len(common) >= 6 and zh >= 0.33)
    )


def incident_clues(item):
    """标题决定事件类型，报道导语补充地点；避免只因正文提及同一话题就合并。"""
    title = item["title"]
    lead = title + " " + item["reading_text"][:180]
    hour = datetime.fromisoformat(item["published_at"]).timestamp() / 3600
    if re.search("枪击|枪杀|枪手", title):
        if "洛根圆环" in lead:
            return "枪击", "华盛顿特区", "洛根圆环", hour
        city = re.search(r"华盛顿特区|纽约市|芝加哥|洛杉矶", title)
        if city:
            return "枪击", city[0], "", hour
    if re.search("炸弹恐吓|炸弹威胁", title) and re.search("学校|校园", title):
        country = re.search("意大利|英国|爱尔兰|德国|法国|加拿大|美国", title)
        if country:
            return "学校炸弹威胁", country[0], "", hour
    if "弹劾" in title and "投票" in title:
        person = re.search(r"赫格(?:塞斯|斯|赛斯)|特朗普|拜登", title)
        if person:
            return "弹劾投票", person[0][:2], "", hour
    return None


def matching_incident(a, b):
    if not a or not b or a[:2] != b[:2]:
        return False
    if a[2] and b[2] and a[2] != b[2]:
        return False
    window = 0.5 if a[0] == "枪击" and not (a[2] and b[2]) else 24
    return abs(a[3] - b[3]) <= window