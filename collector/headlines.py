"""排除出现在新闻索引里的版务信息和导航页。"""
import re
import unicodedata


def publication_metadata(title):
    title = unicodedata.normalize("NFKC", title).strip()
    return bool(re.match(
        r"^(?:本版)?(?:责编|责任编辑|值班编辑|版面编辑|联系邮箱|投稿邮箱|读者来信邮箱)\s*:"
        r"|^(?:人民日报(?:海外版)?|人民网)\s*(?:图文数据库|电子报首页|版面导航)(?:\s*\([\d\s—–-]+\))?$",
        title,
    ))
