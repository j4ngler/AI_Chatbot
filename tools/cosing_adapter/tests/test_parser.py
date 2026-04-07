import json
import unittest
from pathlib import Path

from tools.cosing_adapter.parser import parse_cosing_detail_page, parse_cosing_results_table


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
        self.assertEqual(s0.ec, "200-712-4")
        self.assertTrue(s0.function)
        self.assertTrue(s0.restrictions)
        self.assertEqual(
            s0.reference_url,
            "https://ec.europa.eu/growth/tools-databases/cosing/details/99999",
        )
        self.assertGreaterEqual(len(subs), 2)
        self.assertEqual(subs[1].reference_url, "https://example.com")

    def test_five_column_ec_before_function(self):
        html = (
            "<table><thead><tr>"
            "<th>Substance name</th><th>INCI name</th><th>CAS number</th>"
            "<th>Foo</th><th>Bar</th>"
            "</tr></thead><tbody><tr>"
            "<td>GLYCERIN</td><td>GLYCERIN</td><td>56-81-5</td>"
            "<td>200-289-5</td><td>Humectant</td>"
            "</tr></tbody></table>"
        )
        subs = parse_cosing_results_table(html, reference_url="https://example.com/advanced")
        self.assertEqual(len(subs), 1)
        s = subs[0]
        self.assertEqual(s.cas, "56-81-5")
        self.assertEqual(s.ec, "200-289-5")
        self.assertEqual(s.function, "Humectant")

    def test_parse_detail_page_labels(self):
        html = (
            "<table>"
            "<tr><td>INCI name</td><td>GLYCERIN</td></tr>"
            "<tr><td>CAS #</td><td>56-81-5</td></tr>"
            "<tr><td>EC #</td><td>200-289-5</td></tr>"
            "<tr><td>Maximum concentration when used in rinse-off products</td><td>10 %</td></tr>"
            "<tr><td>Name of Common Ingredients Glossary</td><td>Polysilicone-15</td></tr>"
            "</table>"
        )
        d = parse_cosing_detail_page(html, "https://example.com/detail")
        self.assertEqual(d.get("inci_name"), "GLYCERIN")
        self.assertEqual(d.get("cas"), "56-81-5")
        self.assertEqual(d.get("ec"), "200-289-5")
        self.assertIn("10", d.get("max_concentration", ""))
        self.assertEqual(d.get("glossary_name"), "Polysilicone-15")
        self.assertEqual(d.get("reference_url"), "https://example.com/detail")


if __name__ == "__main__":
    unittest.main()

