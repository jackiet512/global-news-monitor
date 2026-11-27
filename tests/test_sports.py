"""AC1/AC2：体育新闻确定性过滤与采集链路接入。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

from sports import is_sports_news  # noqa: E402
from hackernews import collect_hn  # noqa: E402
from polymarket import _event_candidates  # noqa: E402


class SportsDetectionTests(unittest.TestCase):
    def test_bbc_sport_url(self):
        self.assertTrue(
            is_sports_news(
                title="Match report",
                url="https://www.bbc.com/sport/football/articles/abc123",
            )
        )

    def test_nba_playoffs_en(self):
        self.assertTrue(
            is_sports_news(original_title="Lakers advance in NBA playoffs after overtime win")
        )

    def test_chinese_league_titles(self):
        for title in ("英超争冠形势白热化", "欧冠八强对阵出炉", "国乒世锦赛夺金"):
            self.assertTrue(is_sports_news(title=title), msg=title)

    def test_f1_grand_prix(self):
        self.assertTrue(is_sports_news(original_title="Verstappen wins Monaco Grand Prix F1 race"))

    def test_tennis_grand_slam(self):
        self.assertTrue(is_sports_news(title="温网女单决赛精彩对决"))

    def test_ai_competition_not_sports(self):
        self.assertFalse(is_sports_news(title="中美AI算力竞赛升级"))

    def test_benchmark_champion_not_sports(self):
        self.assertFalse(
            is_sports_news(title="OpenAI新模型在数学基准测试夺冠")
        )

    def test_trade_deal_not_sports(self):
        self.assertFalse(is_sports_news(title="欧盟与美国就关税达成协议"))

    def test_fed_rate_not_sports(self):
        self.assertFalse(is_sports_news(title="美联储季度利率决议公布"))

    def test_broad_words_not_sports(self):
        for title in (
            "科技巨头联盟宣布新标准",
            "本季度团队得分创新高",
            "赛季性流感疫苗接种启动",
        ):
            self.assertFalse(is_sports_news(title=title), msg=title)

    def test_stadium_stampede_emergency_exempt(self):
        self.assertFalse(
            is_sports_news(title="某足球场发生踩踏事件致多人伤亡")
        )

    def test_marathon_evacuation_emergency_exempt(self):
        self.assertFalse(
            is_sports_news(title="马拉松赛事突遇极端天气发布紧急疏散预警")
        )

    def test_shooting_at_stadium_exempt(self):
        self.assertFalse(
            is_sports_news(
                original_title="Shooting at stadium leaves casualties",
                url="https://example.com/news/stadium-incident",
            )
        )


class SportsCollectorIntegrationTests(unittest.TestCase):
    @patch("hackernews._get")
    def test_hn_skips_sports_story(self, mock_get):
        mock_get.return_value = {
            "hits": [
                {
                    "objectID": "1",
                    "title": "NBA Finals Game 7 recap",
                    "url": "https://espn.com/nba/finals",
                    "points": 50,
                    "num_comments": 20,
                    "created_at": "2026-01-01T00:00:00Z",
                },
                {
                    "objectID": "2",
                    "title": "New Rust async runtime",
                    "url": "https://example.com/rust",
                    "points": 40,
                    "num_comments": 10,
                    "created_at": "2026-01-01T00:00:00Z",
                },
            ]
        }
        items, status = collect_hn(lambda x: x, lambda x: x, limit=5)
        self.assertEqual(status, "ok")
        self.assertEqual(len(items), 1)
        self.assertIn("Rust", items[0]["original_title"])

    @patch("hackernews._get")
    def test_hn_keeps_emergency_at_stadium(self, mock_get):
        mock_get.return_value = {
            "hits": [
                {
                    "objectID": "3",
                    "title": "Stampede at football stadium kills dozens",
                    "url": "https://example.com/stampede",
                    "points": 80,
                    "num_comments": 30,
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        }
        items, _ = collect_hn(lambda x: x, lambda x: x, limit=1)
        self.assertEqual(len(items), 1)
        self.assertIn("Stampede", items[0]["original_title"])

    def test_polymarket_skips_sports_market(self):
        events = [
            {
                "slug": "nba-finals-winner",
                "title": "2026 NBA Finals Champion",
                "volume": 500000,
                "markets": [
                    {
                        "question": "Will the Lakers win the 2026 NBA Finals?",
                        "outcomes": '["Yes","No"]',
                        "outcomePrices": '["0.35","0.65"]',
                        "closed": False,
                    }
                ],
            },
            {
                "slug": "us-election",
                "title": "2028 US Presidential Election",
                "volume": 1000000,
                "markets": [
                    {
                        "question": "Will candidate win the election?",
                        "outcomes": '["Yes","No"]',
                        "outcomePrices": '["0.45","0.55"]',
                        "closed": False,
                    }
                ],
            },
        ]
        candidates = _event_candidates(events)
        slugs = {c["slug"] for c in candidates}
        self.assertNotIn("nba-finals-winner", slugs)
        self.assertIn("us-election", slugs)


if __name__ == "__main__":
    unittest.main()