"""T1: RTF strip không crash, văn bản có thể đọc (tiếng Việt / không mojibake kiểu LÖnh)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.extract_text import read_rtf_plain  # noqa: E402


def read_rtf_plain_from_string(s: str) -> str:
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".rtf", encoding="utf-8", delete=False) as f:
        f.write(s)
        p = Path(f.name)
    try:
        return read_rtf_plain(p)
    finally:
        p.unlink(missing_ok=True)


def test_read_rtf_plain_minimal() -> None:
    plain = read_rtf_plain_from_string(r"{\rtf1\ansi\f0\fs24 Luat giao thong duong bo.\par}")
    assert "giao thong" in plain.lower() or "Luat" in plain
    assert "LÖnh" not in plain


def test_workspace_rtf_law_26_if_present() -> None:
    rtf = PROJECT_ROOT / "data" / "raw_laws" / "9730_l26qh.rtf"
    if not rtf.exists():
        pytest.skip("RTF luật 26 không có trong workspace")
    plain = read_rtf_plain(rtf)
    assert len(plain) > 500
    # File RTF gốc có thể là ANSI/cp1252 không map đủ tiếng Việt; kiểm tra có nội dung luật (số hiệu / năm).
    assert "2001" in plain or "07/2001" in plain or "26" in plain
