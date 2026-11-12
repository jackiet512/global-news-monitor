import re
from html.parser import HTMLParser
from urllib.parse import urlsplit


class FeedText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data.strip())


def chinese_text(value):
    parser = FeedText()
    parser.feed(value or "")
    parser.close()
    text = " ".join(part for part in parser.parts if part)
    return text if re.search(r"[一-鿿]", text) else ""


def article_url(value):
    try:
        url = urlsplit(value)
        return bool(url.scheme in ("http", "https") and url.hostname)
    except ValueError:
        return False
