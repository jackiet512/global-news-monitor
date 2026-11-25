"""AC3：社区脉络聚合与异常隔离。"""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

from community import enrich_items, ensure_en_titles, query_terms, search_community  # noqa: E402
from polymarket import match_polymarket  # noqa: E402
from boards import collect  # noqa: E402

SAMPLE_EVENTS = [
    {
        "slug": "trump-2028-election",
        "title": "Donald Trump wins 2028 presidential election",
        "volume": 1200000,
        "markets": [
            {
                "question": "Will Donald Trump win the 2028 presidential election?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.42", "0.58"]',
                "closed": False,
            }
        ],
    }
]


class CommunityTests(unittest.TestCase):
    def test_query_terms_extraction(self):
        item = {"original_title": "OpenAI releases GPT-5 multimodal reasoning", "en_title": "OpenAI releases GPT-5 multimodal reasoning", "title": "OpenAI发布GPT-5"}
        terms = query_terms(item)
        self.assertGreaterEqual(len(terms), 2)
        self.assertIn("openai", terms)

    @patch("community._http_get")
    def test_hn_reddit_parse(self, mock_get):
        def side_effect(url, timeout=8):
            if "hn.algolia" in url:
                return {"hits": [{"objectID": "1", "title": "Test Story", "points": 100, "num_comments": 20, "url": "https://example.com"}]}
            return {"data": {"children": [{"data": {"subreddit": "worldnews", "title": "Test Reddit", "score": 500, "num_comments": 42, "permalink": "/r/worldnews/comments/abc/test/"}}]}}

        mock_get.side_effect = side_effect
        result = search_community("openai gpt release")
        self.assertEqual(len(result["hn"]), 1)
        self.assertEqual(len(result["reddit"]), 1)

    @patch("community._http_get")
    def test_http_errors_isolated(self, mock_get):
        import urllib.error

        mock_get.side_effect = urllib.error.HTTPError("http://x", 403, "forbidden", {}, None)
        result = search_community("test query")
        self.assertEqual(result["source_status"]["hn"], "unavailable")

    @patch("community.search_community")
    def test_enrich_timeout_no_raise(self, mock_search):
        def slow(_q):
            time.sleep(1.2)
            return {"hn": [], "reddit": [], "source_status": {"hn": "empty", "reddit": "empty"}}

        mock_search.side_effect = slow
        items = [
            {"title": "OpenAI release", "original_title": "OpenAI release", "en_title": "OpenAI release"} for _ in range(4)
        ]
        out, errors = enrich_items(items, budget=0.3, max_workers=1, max_items=4)
        self.assertEqual(len(out), 4)
        self.assertTrue(all(i.get("query_terms") for i in out))

    @patch("community.to_english", return_value="Donald Trump announces 2028 presidential campaign rally")
    def test_chinese_source_english_terms_and_polymarket(self, _mock_en):
        item = {"title": "特朗普宣布2028总统竞选集会", "original_title": "特朗普宣布2028总统竞选集会"}
        ensure_en_titles([item])
        terms = query_terms(item)
        self.assertGreaterEqual(len(terms), 2)
        hit = match_polymarket(item, events=SAMPLE_EVENTS)
        self.assertIsNotNone(hit)

    def test_foreign_media_query_terms(self):
        item = {
            "title": "特朗普集会",
            "original_title": "Donald Trump announces 2028 presidential campaign rally",
            "en_title": "Donald Trump announces 2028 presidential campaign rally",
        }
        terms = query_terms(item)
        self.assertGreaterEqual(len(terms), 2)
        self.assertIsNotNone(match_polymarket(item, events=SAMPLE_EVENTS))

    @patch("boards.enrich")
    @patch("boards.enrich_items", side_effect=RuntimeError("community down"))
    @patch("boards.attach_polymarket", side_effect=lambda items, **kw: items)
    @patch("boards.collect_hn", return_value=([], "unavailable"))
    @patch("boards.ThreadPoolExecutor")
    def test_collect_survives_community_failure(self, te, *_mocks):
        te.return_value.__enter__.return_value.map.return_value = [[] for _ in range(len(__import__("boards").SITES))]
        items, errors = collect(lambda t: True)
        self.assertIsInstance(items, list)
        self.assertTrue(any(e.get("source") == "Community" for e in errors))


if __name__ == "__main__":
    unittest.main()