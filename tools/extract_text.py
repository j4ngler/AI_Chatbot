from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pypdf import PdfReader
from striprtf.striprtf import rtf_to_text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_LAWS_DIR = PROJECT_ROOT / "data" / "raw_laws"
PROCESSED_TEXT_DIR = PROJECT_ROOT / "data" / "processed" / "text"


def normalize_text(s: str) -> str:
    s = s.replace("\x00", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def extract_pdf_pages(pdf_path: Path) -> list[dict]:
    reader = PdfReader(str(pdf_path))
    pages: list[dict] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = normalize_text(text)
        pages.append({"page": i + 1, "text": text})
    return pages


def read_rtf_plain(rtf_path: Path) -> str:
    raw = rtf_path.read_bytes()
    text_str: str | None = None
    for enc in ("utf-8", "utf-8-sig", "cp1258", "cp1252", "latin-1"):
        try:
            text_str = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text_str is None:
        text_str = raw.decode("latin-1", errors="replace")
    plain = rtf_to_text(text_str)
    return normalize_text(plain)


def extract_rtf_pages(rtf_path: Path, pseudo_page_chars: int = 12000) -> list[dict]:
    """
    RTF không có khái niệm trang PDF: gom thành một hoặc nhiều pseudo-page để legal_chunker ổn định.
    """
    plain = read_rtf_plain(rtf_path)
    if not plain:
        return [{"page": 1, "text": ""}]
    if len(plain) <= pseudo_page_chars:
        return [{"page": 1, "text": plain}]
    pages: list[dict] = []
    buf = ""
    page_no = 1
    for para in plain.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) + 2 <= pseudo_page_chars:
            buf = buf + "\n\n" + para if buf else para
        else:
            if buf:
                pages.append({"page": page_no, "text": buf})
                page_no += 1
            buf = para
    if buf:
        pages.append({"page": page_no, "text": buf})
    return pages


def resolve_source_path(doc: dict) -> Path:
    name = doc["pdf_filename"]
    path = RAW_LAWS_DIR / name
    fmt = (doc.get("source_format") or "").lower()
    if fmt == "rtf" and path.suffix.lower() != ".rtf":
        path = path.with_suffix(".rtf")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc-id", default=None, help="Chỉ xử lý 1 doc_id trong manifest.json")
    parser.add_argument("--force", action="store_true", help="Ghi đè output nếu đã tồn tại")
    args = parser.parse_args()

    manifest_path = RAW_LAWS_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    PROCESSED_TEXT_DIR.mkdir(parents=True, exist_ok=True)

    for doc in manifest:
        doc_id = doc["doc_id"]
        if args.doc_id and doc_id != args.doc_id:
            continue

        src_path = resolve_source_path(doc)
        if not src_path.exists():
            raise FileNotFoundError(f"Không thấy file nguồn: {src_path}")

        out_path = PROCESSED_TEXT_DIR / f"{doc_id}.json"
        if out_path.exists() and not args.force:
            print(f"SKIP {doc_id} (đã tồn tại)")
            continue

        fmt = (doc.get("source_format") or "").lower()
        suffix = src_path.suffix.lower()
        is_rtf = fmt == "rtf" or suffix == ".rtf"

        print(f"EXTRACT {doc_id}: {src_path.name} ({'rtf' if is_rtf else 'pdf'})")
        if is_rtf:
            pages = extract_rtf_pages(src_path)
        else:
            pages = extract_pdf_pages(src_path)

        out = {
            "doc_id": doc_id,
            "law_number": doc["law_number"],
            "title": doc["title"],
            "pdf_filename": doc["pdf_filename"],
            "pages": pages,
        }
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("DONE extract_text")


if __name__ == "__main__":
    main()
