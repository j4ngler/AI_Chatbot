"""Test contract, cache và service (không cần Selenium / trình duyệt)."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from tools.cosing_adapter.cache_store import ChemicalCacheStore
from tools.cosing_adapter.chemical_lookup_service import ChemicalLookupService
from tools.cosing_adapter.contract import validate_input_contract
from tools.cosing_adapter.schemas import ChemicalLookupOutput, Substance


class FakeWorker:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, query: str, query_type: str, request_id: str) -> ChemicalLookupOutput:
        self.calls += 1
        return ChemicalLookupOutput(
            request_id=request_id,
            substances=[
                Substance(
                    substance_name="Demo",
                    inci_name="DEMO-INCI",
                    cas="123-45-6",
                    ec="200-000-0",
                    function="Humectant",
                    restrictions="—",
                    reference_url="https://ec.europa.eu/growth/tools-databases/cosing/details/1",
                )
            ],
            status="OK",
        )


class TestContract(unittest.TestCase):
    def test_normalize_query(self):
        v = validate_input_contract(
            {
                "query": "  Glycerin   test  ",
                "query_type": "NAME_OR_INCI",
                "request_id": "r1",
            }
        )
        self.assertEqual(v.query, "Glycerin test")
        self.assertEqual(v.request_id, "r1")

    def test_rejects_empty_query(self):
        with self.assertRaises(ValueError):
            validate_input_contract(
                {"query": "  ", "query_type": "NAME_OR_INCI", "request_id": "r1"}
            )

    def test_rejects_bad_query_type(self):
        with self.assertRaises(ValueError):
            validate_input_contract(
                {"query": "x", "query_type": "CAS_ONLY", "request_id": "r1"}
            )


class TestCacheStore(unittest.TestCase):
    def test_roundtrip_payload(self):
        with tempfile.TemporaryDirectory() as d:
            store = ChemicalCacheStore(Path(d), ttl_hours=24)
            out = ChemicalLookupOutput(
                request_id="rid",
                substances=[Substance(substance_name="S1", reference_url="https://ex/details/9")],
                status="OK",
            )
            store.set("niacinamide", "NAME_OR_INCI", out)
            payload = store.get("niacinamide", "NAME_OR_INCI")
            self.assertIsNotNone(payload)
            assert payload is not None
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(len(payload["substances"]), 1)
            self.assertEqual(payload["substances"][0]["substance_name"], "S1")
            self.assertIn("details", payload["substances"][0]["reference_url"])

    def test_query_key_is_casefold_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            store = ChemicalCacheStore(Path(d), ttl_hours=24)
            out = ChemicalLookupOutput(request_id="r", substances=[], status="OK")
            store.set("Salicylic Acid", "NAME_OR_INCI", out)
            self.assertIsNotNone(store.get("salicylic acid", "NAME_OR_INCI"))


class TestChemicalLookupService(unittest.TestCase):
    def test_second_lookup_uses_cache(self):
        with tempfile.TemporaryDirectory() as d:
            worker = FakeWorker()
            svc = ChemicalLookupService(ChemicalCacheStore(Path(d), ttl_hours=24), worker)
            o1 = svc.lookup("vitamin c", "NAME_OR_INCI", "req-first")
            self.assertEqual(worker.calls, 1)
            self.assertEqual(o1.request_id, "req-first")
            self.assertEqual(o1.substances[0].inci_name, "DEMO-INCI")
            o2 = svc.lookup("vitamin c", "NAME_OR_INCI", "req-second")
            self.assertEqual(worker.calls, 1)
            self.assertEqual(o2.request_id, "req-second")
            self.assertEqual(len(o2.substances), 1)

    def test_hydrate_substance_from_cache_without_ec_field(self):
        """Cache cũ thiếu key 'ec' vẫn tạo được Substance (mặc định rỗng)."""
        with tempfile.TemporaryDirectory() as d:
            store = ChemicalCacheStore(Path(d), ttl_hours=24)
            legacy = {
                "request_id": "old",
                "source": "EU_COSING",
                "status": "OK",
                "substances": [
                    {
                        "substance_name": "Legacy",
                        "inci_name": "",
                        "cas": "50-00-0",
                        "function": "",
                        "restrictions": "",
                        "reference_url": "https://example.com/advanced",
                        "fetched_at": "t",
                    }
                ],
            }
            key = store._key("legacyq", "NAME_OR_INCI")
            p = store._path(key)
            p.write_text(
                json.dumps({"cached_at": time.time(), "payload": legacy}, ensure_ascii=False),
                encoding="utf-8",
            )
            worker = FakeWorker()
            svc = ChemicalLookupService(store, worker)
            out = svc.lookup("legacyq", "NAME_OR_INCI", "new-req")
            self.assertEqual(worker.calls, 0)
            self.assertEqual(out.substances[0].substance_name, "Legacy")
            self.assertEqual(out.substances[0].ec, "")


if __name__ == "__main__":
    unittest.main()
