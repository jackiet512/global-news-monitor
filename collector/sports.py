"""确定性体育新闻识别与过滤。"""
import re
from urllib.parse import urlsplit

EMERGENCY_ZH = re.compile(r"伤亡|遇难|踩踏|枪击|爆炸|恐袭|地震|预警|疏散|应急响应")
EMERGENCY_EN = re.compile(
    r"\b(casualties|stampede|shooting|explosion|terror|evacuat)\w*\b", re.I
)

SPORTS_PATH = re.compile(
    r"/(?:sports?|football|soccer|nba|nfl|mlb|nhl|cricket|rugby|tennis|golf|"
    r"f1|formula1|olympics|athletics|boxing|ufc|mma|baseball|basketball)(?:/|$)",
    re.I,
)

EN_SPORTS = re.compile(
    r"\b(?:nba|nfl|mlb|nhl|wnba|ncaa|fifa|uefa|premier\s+league|champions\s+league|"
    r"la\s+liga|serie\s+a|bundesliga|super\s+bowl|world\s+cup|wimbledon|grand\s+prix|"
    r"formula\s+1|f1|ufc|mma|boxing|cricket|rugby|tennis|baseball|basketball|"
    r"badminton|table\s+tennis|golf|pga|nascar|motogp|marathon|playoffs|quarterback|"
    r"touchdown|home\s+run|goalkeeper|hat-trick|red\s+card|penalty\s+kick|"
    r"transfer\s+window|esports)\b",
    re.I,
)

ZH_SPORTS = re.compile(
    r"英超|欧冠|西甲|意甲|德甲|法甲|中超|CBA|NBA|NFL|MLB|NHL|UFC|F1|WTA|ATP|世预赛|"
    r"世界杯|欧洲杯|美洲杯|亚洲杯|亚冠|大满贯|温网|法网|美网|澳网|冬奥会|奥运会|"
    r"亚运会|全运会|超级碗|季后赛|总决赛|常规赛|全明星赛|男足|女足|男篮|女篮|"
    r"男排|女排|国足|国乒|国羽|足球|篮球|网球|排球|乒乓球|羽毛球|棒球|橄榄球|"
    r"高尔夫|台球|斯诺克|拳击|田径|马拉松|花样滑冰|短道速滑|跳水|体操|电竞|"
    r"球星|球员|门将|前锋|后卫|主帅|主教练|转会|绝杀|点球|红牌|黄牌|加时赛|"
    r"三分球|扣篮|篮板|助攻|帽子戏法|卫冕冠军|晋级八强|晋级四强|晋级决赛"
)


def _text(title="", original_title="", summary=""):
    return " ".join(p for p in (title, original_title, summary) if p)


def _emergency_exempt(text):
    return bool(EMERGENCY_ZH.search(text) or EMERGENCY_EN.search(text))


def is_sports_news(title="", original_title="", url="", summary=""):
    """判定是否为体育赛事/球队/联赛类新闻；重大公共安全突发豁免。"""
    combined = _text(title, original_title, summary)
    if _emergency_exempt(combined):
        return False
    path = urlsplit(url or "").path.lower()
    if SPORTS_PATH.search(path):
        return True
    if EN_SPORTS.search(combined) or ZH_SPORTS.search(combined):
        return True
    return False