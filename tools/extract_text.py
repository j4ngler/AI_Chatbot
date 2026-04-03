from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pypdf import PdfReader


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

        pdf_name = doc["pdf_filename"]
        pdf_path = RAW_LAWS_DIR / pdf_name
        if not pdf_path.exists():
            raise FileNotFoundError(f"Không thấy file PDF: {pdf_path}")

        out_path = PROCESSED_TEXT_DIR / f"{doc_id}.json"
        if out_path.exists() and not args.force:
            print(f"SKIP {doc_id} (đã tồn tại)")
            continue

        print(f"EXTRACT {doc_id}: {pdf_name}")
        pages = extract_pdf_pages(pdf_path)
        out = {
            "doc_id": doc_id,
            "law_number": doc["law_number"],
            "title": doc["title"],
            "pdf_filename": pdf_name,
            "pages": pages,
        }
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("DONE extract_text")


if __name__ == "__main__":
    main()

