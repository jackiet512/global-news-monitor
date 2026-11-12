import hashlib
import unittest

class CollectorContractTests(unittest.TestCase):
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
