import unittest

from collector.headlines import publication_metadata


class HeadlineTests(unittest.TestCase):
    def test_index_metadata(self):
        self.assertTrue(publication_metadata("责编：任成琦 汪灵犀 邮箱：editor@example.org"))
        self.assertTrue(publication_metadata("人民日报图文数据库（1946-2026）"))

    def test_news_about_editors_or_databases(self):
        self.assertFalse(publication_metadata("人民日报图文数据库新增历史资料"))
        self.assertFalse(publication_metadata("责任编辑谈重大报道如何核实来源"))
