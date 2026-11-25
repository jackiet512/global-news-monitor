"""AC3：社区脉络聚合与异常隔离。"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

from community import query_terms, search_community  # noqa: E402
from boards import collect  # noqa: E402


class CommunityTests(unittest.TestCase):
    def test_query_terms_extraction(self):
        item = {"original_title": "OpenAI releases GPT-5 multimodal reasoning", "title": "OpenAI发布GPT-5"}
        terms = query_terms(item)
        self.assertGreaterEqual(len(terms), 2)
        self.assertIn("openai", terms)

    @patch("community._get")
    def test_hn_reddit_parse(self, mock_get):
        def side_effect(url, timeout=8):
            if "hn.algolia" in url:
                return {
                    "hits": [
                        {
                            "objectID": "1",
                            "title": "Test Story",
                            "points": 100,
                            "num_comments": 20,
                            "url": "https://example.com",
                        }
                    ]
                }
            return {
                "data": {
                    "children": [
                        {
                            "data": {
                                "subreddit": "worldnews",
                                "title": "Test Reddit",
                                "score": 500,
                                "num_comments": 42,
                                "permalink": "/r/worldnews/comments/abc/test/",
                            }
                        }
                    ]
                }
            }

        mock_get.side_effect = side_effect
        result = search_community("openai gpt release")
        self.assertEqual(len(result["hn"]), 1)
        self.assertEqual(len(result["reddit"]), 1)
        self.assertEqual(result["reddit"][0]["subreddit"], "worldnews")

    @patch("community._get")
    def test_http_errors_isolated(self, mock_get):
        import urllib.error

        mock_get.side_effect = urllib.error.HTTPError("http://x", 403, "forbidden", {}, None)
        result = search_community("test query")
        self.assertEqual(result["source_status"]["hn"], "unavailable")
        self.assertEqual(result["source_status"]["reddit"], "unavailable")

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