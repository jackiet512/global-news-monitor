import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

from collect import to_beijing_iso, main

BJ_SUFFIX = "+08:00"


class CollectorBeijingTests(unittest.TestCase):
    def test_to_beijing_iso_z(self):
        self.assertEqual(to_beijing_iso("2026-01-01T00:00:00Z"), "2026-01-01T08:00:00+08:00")

    def test_to_beijing_iso_utc_offset(self):
        self.assertEqual(to_beijing_iso("2026-01-01T00:00:00+00:00"), "2026-01-01T08:00:00+08:00")

    def test_to_beijing_iso_negative_offset(self):
        self.assertEqual(to_beijing_iso("2026-01-01T00:00:00-05:00"), "2026-01-01T13:00:00+08:00")

    def test_to_beijing_iso_already_beijing(self):
        self.assertEqual(to_beijing_iso("2026-01-01T08:00:00+08:00"), "2026-01-01T08:00:00+08:00")

    def test_to_beijing_iso_sqlite_naive(self):
        self.assertEqual(to_beijing_iso("2026-01-01 00:00:00"), "2026-01-01T08:00:00+08:00")

    def test_to_beijing_iso_empty(self):
        self.assertEqual(to_beijing_iso(""), "")
        self.assertEqual(to_beijing_iso(None), "")

    def test_to_beijing_iso_invalid(self):
        self.assertEqual(to_beijing_iso("not-a-date"), "")

    @patch("collect.collect")
    def test_collect_main_outputs_beijing_times(self, mock_collect):
        fp = hashlib.sha256(b"https://example.com/a").hexdigest()
        mock_collect.return_value = ([
            {
                "fingerprint": fp,
                "title": "测试",
                "published_at": "2026-01-01T00:00:00Z",
                "collected_at": "2026-01-01T12:00:00-05:00",
            }
        ], [])
        tmp = ROOT / "collector" / "_test_latest_run.json"
        try:
            with patch("collect.OUT", tmp):
                main()
            report = json.loads(tmp.read_text(encoding="utf-8"))
        finally:
            tmp.unlink(missing_ok=True)
        self.assertTrue(report["run_at"].endswith(BJ_SUFFIX))
        self.assertNotIn("+00:00", report["run_at"])
        self.assertNotIn("Z", report["run_at"])
        for item in report["items"]:
            self.assertTrue(item["published_at"].endswith(BJ_SUFFIX))
            self.assertTrue(item["collected_at"].endswith(BJ_SUFFIX))

    def test_fingerprint_is_deterministic(self):
        url = "https://example.com/story"
        self.assertEqual(hashlib.sha256(url.encode()).hexdigest(),
                         hashlib.sha256(url.encode()).hexdigest())

    def test_fingerprint_changes_for_different_urls(self):
        a = hashlib.sha256(b"https://example.com/a").hexdigest()
        b = hashlib.sha256(b"https://example.com/b").hexdigest()
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()