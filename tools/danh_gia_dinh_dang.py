#!/usr/bin/env python3
"""
Tool danh gia dinh dang tai lieu DOCX theo huong dan ChatAI V2.0.

Quy tac trich xuat tu phan III - CHUAN HOA TAI LIEU:
- Quyet dinh:
  * Tieu de van ban: Heading 1
  * Chuong: Heading 2
  * Muc: Heading 3
  * Dieu: Heading 4
- Quy dinh:
  * Tieu de quy dinh: Heading 1
  * Chuong: Heading 2
  * Dieu: Heading 3
- Nhiem vu:
  * Linh vuc: Heading 1
  * Ten cong viec/Trich yeu: Heading 2
  * Cac truong thong tin khac: khong heading
- Lich lam viec:
  * "Thu, ngay, thang, nam": Heading 1
  * "Buoi + thu, ngay, thang, nam": Heading 2
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Pattern, Tuple

try:
    from docx import Document  # type: ignore
except Exception as exc:  # pragma: no cover
    print("Khong the import python-docx. Cai dat bang: pip install python-docx")
    print(f"Chi tiet loi: {exc}")
    sys.exit(1)


@dataclass
class Violation:
    line: int
    text: str
    expected: str
    actual: str
    rule: str


@dataclass
class EvaluationResult:
    profile: str
    file: str
    score: float
    total_checks: int
    violations: List[Violation]
    summary: Dict[str, int]


def heading_level(style_name: str) -> Optional[int]:
    name = (style_name or "").strip().lower()
    m = re.search(r"heading\s*(\d+)", name)
    if m:
        return int(m.group(1))
    return None


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def build_patterns() -> Dict[str, List[Tuple[Pattern[str], Optional[int], str]]]:
    return {
        "quyet_dinh": [
            (re.compile(r"^quy[eê]́?t?\s*đ[iị]nh\b", re.IGNORECASE), 1, "Tieu de Quyet dinh phai la Heading 1"),
            (re.compile(r"^ch[ưu]ơng\b", re.IGNORECASE), 2, "Ten Chuong phai la Heading 2"),
            (re.compile(r"^m[uụ]c\b", re.IGNORECASE), 3, "Ten Muc phai la Heading 3"),
            (re.compile(r"^đi[eề]u\s+\d+", re.IGNORECASE), 4, "Cac Dieu phai la Heading 4"),
        ],
        "quy_dinh": [
            (re.compile(r"^quy\s*đ[iị]nh\b", re.IGNORECASE), 1, "Tieu de Quy dinh phai la Heading 1"),
            (re.compile(r"^ch[ưu]ơng\b", re.IGNORECASE), 2, "Ten Chuong phai la Heading 2"),
            (re.compile(r"^đi[eề]u\s+\d+", re.IGNORECASE), 3, "Cac Dieu phai la Heading 3"),
        ],
        "nhiem_vu": [
            (re.compile(r"^l[iĩi]nh\s*v[ựu]c\b", re.IGNORECASE), 1, "Linh vuc phai la Heading 1"),
            (
                re.compile(r"^(t[eê]n\s*c[oô]ng\s*vi[eệ]c|tr[ií]ch\s*y[eế]u)\b", re.IGNORECASE),
                2,
                "Ten cong viec/Trich yeu phai la Heading 2",
            ),
            (
                re.compile(
                    r"^(s[oố],?\s*ng[aà]y|l[aã]nh\s*đạo\s*đơn\s*v[iị]|đơn\s*v[iị]\s*th[ựu]c\s*hi[eệ]n|ngu[oồ]n\s*nhi[eệ]m\s*v[uụ]|ti[eế]n\s*độ|ph[aâ]n\s*lo[aạ]i\s*nhi[eệ]m\s*v[uụ]|giao\s*cho\s*ai)\b",
                    re.IGNORECASE,
                ),
                None,
                "Cac truong thong tin trong Nhiem vu khong duoc danh Heading",
            ),
        ],
        "lich_lam_viec": [
            (
                re.compile(r"^th[ứu]\s*[2-7]|^th[ứu]\s*(hai|ba|t[uư]|n[aă]m|s[aá]u|b[aả]y|ch[uủ]\s*nh[aậ]t)", re.IGNORECASE),
                1,
                "Dong Thu/Ngay phai la Heading 1",
            ),
            (
                re.compile(
                    r"^(s[aá]ng|chi[eề]u|t[oố]i)\s+th[ứu]\s*([2-7]|hai|ba|t[uư]|n[aă]m|s[aá]u|b[aả]y|ch[uủ]\s*nh[aậ]t)",
                    re.IGNORECASE,
                ),
                2,
                "Dong Buoi + Thu/Ngay phai la Heading 2",
            ),
        ],
    }


def evaluate_docx(
    file_path: Path,
    profile: str,
) -> EvaluationResult:
    patterns = build_patterns()
    if profile not in patterns:
        raise ValueError(f"Profile khong hop le: {profile}")

    doc = Document(str(file_path))
    violations: List[Violation] = []
    checks = 0

    for idx, para in enumerate(doc.paragraphs, start=1):
        text = normalize_text(para.text)
        if not text:
            continue

        h_level = heading_level(para.style.name if para.style else "")
        for regex, expected_level, rule in patterns[profile]:
            if regex.search(text):
                checks += 1
                if expected_level is None:
                    if h_level is not None:
                        violations.append(
                            Violation(
                                line=idx,
                                text=text[:120],
                                expected="No Heading",
                                actual=f"Heading {h_level}",
                                rule=rule,
                            )
                        )
                elif h_level != expected_level:
                    actual = "No Heading" if h_level is None else f"Heading {h_level}"
                    violations.append(
                        Violation(
                            line=idx,
                            text=text[:120],
                            expected=f"Heading {expected_level}",
                            actual=actual,
                            rule=rule,
                        )
                    )

    if checks == 0:
        score = 0.0
    else:
        score = round((1 - (len(violations) / checks)) * 100, 2)

    summary = {
        "matched_checks": checks,
        "violations": len(violations),
        "passed": max(checks - len(violations), 0),
    }

    return EvaluationResult(
        profile=profile,
        file=str(file_path),
        score=score,
        total_checks=checks,
        violations=violations,
        summary=summary,
    )


def format_text_report(result: EvaluationResult, max_items: int) -> str:
    lines: List[str] = []
    lines.append("=== BAO CAO DANH GIA DINH DANG ===")
    lines.append(f"File: {result.file}")
    lines.append(f"Profile: {result.profile}")
    lines.append(f"Diem: {result.score}/100")
    lines.append(f"So luong quy tac khop: {result.total_checks}")
    lines.append(f"So loi: {len(result.violations)}")
    lines.append("")

    if result.total_checks == 0:
        lines.append("Khong tim thay dong nao khop quy tac profile da chon.")
        lines.append("Kiem tra lai profile hoac noi dung tai lieu.")
        return "\n".join(lines)

    if not result.violations:
        lines.append("Tai lieu DAT chuan theo cac quy tac da khai bao.")
        return "\n".join(lines)

    lines.append("Chi tiet loi (toi da %d dong):" % max_items)
    for i, v in enumerate(result.violations[:max_items], start=1):
        lines.append(f"{i}. [Dong {v.line}] {v.rule}")
        lines.append(f"   - Van ban: {v.text}")
        lines.append(f"   - Mong doi: {v.expected}")
        lines.append(f"   - Thuc te : {v.actual}")
    if len(result.violations) > max_items:
        lines.append(f"... con {len(result.violations) - max_items} loi khac")
    return "\n".join(lines)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Danh gia dinh dang DOCX theo huong dan chuan hoa tai lieu."
    )
    parser.add_argument("--input", required=True, help="Duong dan file .docx can danh gia")
    parser.add_argument(
        "--profile",
        required=True,
        choices=["quyet_dinh", "quy_dinh", "nhiem_vu", "lich_lam_viec"],
        help="Loai tai lieu de ap dung quy tac",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Neu cung cap, ghi ket qua JSON ra file nay",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=20,
        help="So dong loi toi da hien thi tren console",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    file_path = Path(args.input)
    if not file_path.exists():
        print(f"Khong tim thay file: {file_path}")
        return 2
    if file_path.suffix.lower() != ".docx":
        print("Chi ho tro file .docx")
        return 2

    result = evaluate_docx(file_path, args.profile)
    print(format_text_report(result, args.max_items))

    if args.output_json:
        out = Path(args.output_json)
        payload = asdict(result)
        payload["violations"] = [asdict(v) for v in result.violations]
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDa ghi JSON: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
