import json
import unittest
from pathlib import Path

from tools.cosing_adapter.parser import parse_cosing_results_table


class TestCosingParser(unittest.TestCase):
    def test_parse_fixture(self):
        fixture_path = Path(__file__).parent / "fixtures" / "cosing_table_example.html"
        html = fixture_path.read_text(encoding="utf-8")

        subs = parse_cosing_results_table(html, reference_url="https://example.com")
        self.assertIsInstance(subs, list)
        self.assertGreaterEqual(len(subs), 1)

        s0 = subs[0]
        self.assertTrue(s0.substance_name)
        self.assertTrue(s0.inci_name)
        self.assertTrue(s0.cas)
        self.assertTrue(s0.function)
        self.assertTrue(s0.restrictions)
        self.assertEqual(s0.reference_url, "https://example.com")


if __name__ == "__main__":
    unittest.main()

