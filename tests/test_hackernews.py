"""AC1：HN 热榜与安全正文补全。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

from hackernews import _public_url, _bj_iso, _score, collect_hn  # noqa: E402
from reading import _hostname_blocked, _url_allowed, enrich  # noqa: E402


class HackernewsTests(unittest.TestCase):
    def test_score_sorting(self):
        self.assertGreater(_score({"points": 100, "num_comments": 50}), _score({"points": 80, "num_comments": 10}))

    def test_public_url_fallback_discussion(self):
        url = _public_url({"objectID": "12345", "url": ""})
        self.assertIn("news.ycombinator.com/item?id=12345", url)

    def test_bj_iso_timezone(self):
        stamp = _bj_iso("2026-01-01T12:00:00Z")
        self.assertIn("+08:00", stamp)

    @patch("hackernews._get")
    def test_collect_hn_community_has_title(self, mock_get):
        mock_get.side_effect = [
            {"hits": [{"objectID": "1", "title": "Show HN", "points": 40, "num_comments": 10, "created_at": "2026-01-01T00:00:00Z"}]},
            {"children": [{"type": "comment", "author": "pg", "text": "Nice", "points": 3}]},
        ]
        items, _ = collect_hn(lambda x: x, lambda x: x, limit=1)
        hn = items[0]["community"]["hn"][0]
        self.assertTrue(hn["title"])
        self.assertIn("discussion_url", hn)
        self.assertIn("news.ycombinator.com", hn["discussion_url"])

    def test_hostname_blocked_localhost(self):
        self.assertTrue(_hostname_blocked("localhost"))

    @patch("reading.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))])
    def test_url_allowed_public_https_ip(self, _gai):
        self.assertTrue(_url_allowed("https://93.184.216.34/post", require_https=True))

    def test_url_allowed_rejects_blocked(self):
        for url in (
            "http://example.com/x",
            "ftp://evil.example/file",
            "file:///etc/passwd",
            "https://localhost/admin",
            "https://127.0.0.1/admin",
            "https://192.168.1.1/admin",
            "https://169.254.169.254/meta",
        ):
            self.assertFalse(_url_allowed(url, require_https=True), msg=url)

    def test_reading_hn_https_article_non_empty(self):
        items = [
            {
                "title": "测试",
                "url": "https://example.com/article",
                "source_name": "Hacker News",
                "reading_text": "",
                "image_url": "",
            }
        ]

        def fake_read(url):
            return b"<html><head><meta property='og:description' content='hello world text'></head><body><p>hello world text paragraph content here</p></body></html>"

        with patch("reading.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
            enrich(items, {}, fake_read, lambda t: t)
        self.assertTrue(items[0].get("reading_text"))


if __name__ == "__main__":
    unittest.main()