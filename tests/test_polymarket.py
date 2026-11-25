"""AC2：Polymarket 双格式解析与防泛词误配。"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

from polymarket import _market_prob, _parse_list, match_polymarket  # noqa: E402


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
    },
    {
        "slug": "bitcoin-200k",
        "title": "Bitcoin reaches $200k before 2027",
        "volume24hr": 85000,
        "markets": [
            {
                "question": "Bitcoin above $200k in 2026?",
                "outcomes": ["Yes", "No"],
                "outcomePrices": ["0.68", "0.32"],
                "closed": False,
            }
        ],
    },
]


class PolymarketTests(unittest.TestCase):
    def test_parse_list_json_string(self):
        self.assertEqual(_parse_list('["Yes", "No"]'), ["Yes", "No"])

    def test_parse_list_native(self):
        self.assertEqual(_parse_list(["a", "b"]), ["a", "b"])

    def test_market_prob_yes_from_json_string(self):
        prob = _market_prob(
            {"outcomes": '["Yes","No"]', "outcomePrices": '["0.68","0.32"]', "closed": False, "question": "Q?"}
        )
        self.assertEqual(prob["probability"], 68)
        self.assertEqual(prob["outcome"], "Yes")

    def test_market_prob_skips_zero_prices(self):
        self.assertIsNone(_market_prob({"outcomes": ["Yes", "No"], "outcomePrices": ["0", "0"]}))

    def test_match_hit(self):
        item = {
            "original_title": "Donald Trump announces 2028 presidential campaign rally",
            "title": "特朗普宣布2028总统竞选集会",
        }
        hit = match_polymarket(item, events=SAMPLE_EVENTS)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["probability"], 42)

    def test_match_bitcoin(self):
        item = {
            "original_title": "Bitcoin reaches $150k before 2027 as ETF inflows accelerate",
            "title": "比特币有望在2027年前达到15万美元",
        }
        hit = match_polymarket(item, events=SAMPLE_EVENTS)
        self.assertIsNotNone(hit)
        self.assertIn("bitcoin", hit["url"].lower() if hit.get("url") else "bitcoin")

    def test_no_match_generic_words(self):
        for title in [
            "US President Will Win in 2026",
            "Will AI change the world in 2026",
            "President market news report",
        ]:
            item = {"original_title": title, "title": title}
            self.assertIsNone(match_polymarket(item, events=SAMPLE_EVENTS), msg=title)


if __name__ == "__main__":
    unittest.main()