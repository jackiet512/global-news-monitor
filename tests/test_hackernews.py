"""AC1：HN 热榜与安全正文补全。"""
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

from hackernews import _public_url, _score, collect_hn, top_comments  # noqa: E402
from reading import _hostname_blocked, _url_allowed, enrich  # noqa: E402


class HackernewsTests(unittest.TestCase):
    def test_score_sorting(self):
        self.assertGreater(_score({"points": 100, "num_comments": 50}), _score({"points": 80, "num_comments": 10}))

    def test_public_url_fallback_discussion(self):
        hit = {"objectID": "12345", "url": ""}
        url = _public_url(hit)
        self.assertIn("news.ycombinator.com/item?id=12345", url)

    def test_public_url_external_https(self):
        hit = {"objectID": "1", "url": "https://example.com/story"}
        self.assertEqual(_public_url(hit), "https://example.com/story")

    @patch("hackernews._get")
    def test_collect_hn_max_five(self, mock_get):
        hits = [
            {"objectID": str(i), "title": f"Story {i}", "url": f"https://ex{i}.com", "points": 100 - i, "num_comments": 10, "created_at": "2026-01-01T00:00:00Z"}
            for i in range(20)
        ]
        mock_get.side_effect = [{"hits": hits}, {"hits": []}]
        with patch("hackernews.top_comments", return_value=[]):
            items, status = collect_hn(lambda x: x, lambda x: x, limit=5)
        self.assertEqual(status, "ok")
        self.assertLessEqual(len(items), 5)
        self.assertTrue(all(i["source_name"] == "Hacker News" for i in items))

    @patch("hackernews._get")
    def test_ask_hn_no_url_uses_discussion(self, mock_get):
        mock_get.return_value = {"hits": [{"objectID": "99", "title": "Ask HN: test", "points": 50, "num_comments": 20, "created_at": "2026-01-01T00:00:00Z"}]}
        with patch("hackernews.top_comments", return_value=[]):
            items, _ = collect_hn(lambda x: x, lambda x: x)
        self.assertEqual(items[0]["url"], "https://news.ycombinator.com/item?id=99")

    def test_hostname_blocked_localhost(self):
        self.assertTrue(_hostname_blocked("localhost"))
        self.assertTrue(_hostname_blocked("127.0.0.1"))

    def test_url_allowed_blocks_private_ip(self):
        self.assertTrue(_url_allowed("http://127.0.0.1/secret"))
        self.assertTrue(_url_allowed("http://192.168.1.1/admin"))

    def test_reading_hacker_news_no_keyerror(self):
        items = [
            {
                "title": "测试",
                "url": "https://news.ycombinator.com/item?id=1",
                "source_name": "Hacker News",
                "reading_text": "",
                "image_url": "",
            }
        ]
        enrich(items, {}, lambda u: b"", lambda t: t)
        self.assertEqual(items[0]["source_name"], "Hacker News")

    def test_reading_hn_https_article(self):
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
            return b"<html><head><meta property='og:description' content='hello world text'></head><body><p>hello world text</p></body></html>"

        enrich(items, {}, fake_read, lambda t: t)
        self.assertEqual(items[0]["source_name"], "Hacker News")


if __name__ == "__main__":
    unittest.main()