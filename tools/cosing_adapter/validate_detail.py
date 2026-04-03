from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import List, Optional

import argparse

from .cosing_worker_selenium import CosingSeleniumWorker, WorkerConfig
from .schemas import QueryType


@dataclass
class Expected:
    inci_name: str
    cas: str
    ec: str
    annex_ref_contains: str
    functions_contains: List[str]
    sccs_opinions_contains: List[str]


def norm(s: str) -> str:
    return " ".join((s or "").split()).strip()


def contains_all(haystack: str, needles: List[str]) -> bool:
    h = (haystack or "").lower()
    return all((n or "").lower() in h for n in needles if n)


def validate(detail: dict, expected: Expected) -> List[str]:
    errors: List[str] = []
    if norm(detail.get("inci_name", "")) != expected.inci_name:
        errors.append(f"inci_name mismatch. expected={expected.inci_name} actual={detail.get('inci_name')}")
    if norm(detail.get("cas", "")) != expected.cas:
        errors.append(f"cas mismatch. expected={expected.cas} actual={detail.get('cas')}")
    if norm(detail.get("ec", "")) != expected.ec:
        errors.append(f"ec mismatch. expected={expected.ec} actual={detail.get('ec')}")
    if expected.annex_ref_contains and expected.annex_ref_contains.lower() not in norm(detail.get("annex_ref", "")).lower():
        errors.append(f"annex_ref mismatch. expected contains={expected.annex_ref_contains} actual={detail.get('annex_ref')}")

    if expected.functions_contains:
        if not contains_all(detail.get("functions", ""), expected.functions_contains):
            errors.append(
                "functions mismatch. expected contains="
                + ",".join(expected.functions_contains)
                + " actual="
                + str(detail.get("functions"))
            )

    if expected.sccs_opinions_contains:
        if not contains_all(detail.get("sccs_opinions", ""), expected.sccs_opinions_contains):
            errors.append(
                "sccs_opinions mismatch. expected contains="
                + ",".join(expected.sccs_opinions_contains)
                + " actual="
                + str(detail.get("sccs_opinions"))
            )

    return errors


def main() -> int:
    # Expected from video screenshot:
    expected = Expected(
        inci_name="POLYSILICONE-15",
        cas="207574-74-1",
        ec="426-000-4",
        annex_ref_contains="VI/26",
        functions_contains=["LIGHT STABILIZER", "UV ABSORBER", "UV FILTER"],
        sccs_opinions_contains=["Polysilicone-15", "Opinion"],
    )

    request_id = "REQ-validate-polysilicone15"

    parser = argparse.ArgumentParser(description="Validate CoSIng substance detail fields (Selenium).")
    parser.add_argument("--browser", default="chrome", choices=["chrome", "edge"])
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run with visible browser (closer to human/manual testing).",
    )
    args = parser.parse_args()

    worker = CosingSeleniumWorker(
        WorkerConfig(
            headless=not args.no_headless,
            browser=args.browser,
            timeout_seconds=75,
        ),
    )
    detail = worker.fetch_detail(
        query="Polysilicone-15",
        query_type="NAME_OR_INCI",  # type: ignore[arg-type]
        request_id=request_id,
    )

    print(json.dumps(detail, ensure_ascii=False, indent=2))

    if detail.get("status") != "OK":
        print(f"FAIL: worker returned status={detail.get('status')}")
        return 2

    errors = validate(detail, expected)
    if errors:
        print("\nFAIL: mismatches:")
        for e in errors:
            print("- " + e)
        return 1

    print("\nPASS: All expected fields match (with contains rules for lists).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

