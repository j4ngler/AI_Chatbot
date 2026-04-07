from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .cache_store import ChemicalCacheStore
from .chemical_lookup_service import ChemicalLookupService
from .cosing_worker_selenium import CosingSeleniumWorker, WorkerConfig
from .contract import validate_input_contract


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tra cuu CoSIng bang Selenium + cache TTL=24h")
    p.add_argument("--request-id", required=True, help="Ma request de trace artifacts/log")
    p.add_argument("--query", required=True, help="Ten chat can tra cuu (name or INCI)")
    p.add_argument(
        "--query-type",
        default="NAME_OR_INCI",
        choices=["NAME_OR_INCI"],
        help="Loai query (spec: NAME_OR_INCI).",
    )
    p.add_argument("--cache-dir", default="data/cache/cosing", help="Thu muc cache JSON.")
    p.add_argument("--browser", default="chrome", choices=["chrome", "edge"], help="Trinh duyet automation.")
    p.add_argument("--headless", action="store_true", help="Chay headless (mac dinh true neu khong set).")
    p.add_argument("--no-headless", action="store_true", help="Bat tat headless.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    headless = True
    if args.no_headless:
        headless = False

    input_payload = {
        "request_id": args.request_id,
        "query": args.query,
        "query_type": args.query_type,
    }
    # Validate Input contract early for better error visibility.
    validated = validate_input_contract(input_payload)

    cache_store = ChemicalCacheStore(cache_dir=Path(args.cache_dir), ttl_hours=24)
    enrich_raw = (os.getenv("COSING_ENRICH_DETAIL", "true") or "").strip().lower()
    enrich_detail = enrich_raw in ("1", "true", "yes", "on")
    worker = CosingSeleniumWorker(
        WorkerConfig(
            headless=headless,
            browser=args.browser,
            enrich_detail=enrich_detail,
        )
    )
    service = ChemicalLookupService(cache_store=cache_store, worker=worker)

    out = service.lookup(
        query=validated.query,
        query_type=validated.query_type,
        request_id=validated.request_id,
    )
    print(json.dumps(out.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

