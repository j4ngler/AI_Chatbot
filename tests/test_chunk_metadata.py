"""Heuristic: article_ref (Điều N) có xuất hiện gần đầu chunk_text không — law_35_2018 nhiều đoạn sửa đổi nên cho phép tỷ lệ thấp."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_law_35_2018_article_prefix_alignment() -> None:
    path = PROJECT_ROOT / "data" / "processed" / "chunks" / "law_35_2018_qh14.jsonl"
    if not path.exists():
        pytest.skip("Chưa có chunk law_35_2018_qh14.jsonl")

    ok = 0
    bad = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        ref = (r.get("article_ref") or "").strip()
        text = (r.get("chunk_text") or "")[:400]
        if ref == "Toàn văn" or not ref.startswith("Điều"):
            continue
        m = re.match(r"Điều\s+(\d+)\b", ref, re.IGNORECASE)
        if not m:
            continue
        n = m.group(1)
        if re.search(rf"Điều\s+{n}\b", text[:350], re.IGNORECASE):
            ok += 1
        else:
            bad += 1

    assert ok >= 1, "Không có chunk nào khớp heuristic Điều N ở đầu body"
    if ok + bad > 0:
        ratio = ok / (ok + bad)
        assert ratio >= 0.35, f"Tỷ lệ khớp {ratio:.2f} < 0.35 — nên rà soát chunker hoặc nguồn PDF"
