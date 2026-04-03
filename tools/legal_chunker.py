from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_LAWS_DIR = PROJECT_ROOT / "data" / "raw_laws"
PROCESSED_TEXT_DIR = PROJECT_ROOT / "data" / "processed" / "text"
PROCESSED_CHUNKS_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"


def normalize_ws(s: str) -> str:
    s = s.replace("\x00", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def find_first_page_containing_article(pages: list[dict], article_no: int) -> int | None:
    pat = re.compile(rf"Điều\s+{article_no}\b", flags=re.IGNORECASE)
    for p in pages:
        if pat.search(p.get("text", "")):
            return int(p.get("page"))
    return None


def split_if_too_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    # Ưu tiên tách theo đoạn để giữ ngữ nghĩa
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paras:
        if not buf:
            buf = para
            continue
        if len(buf) + 2 + len(para) <= max_chars:
            buf = buf + "\n\n" + para
        else:
            chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)
    return chunks


def chunk_by_article(pages: list[dict], doc_id: str, law_number: str, title: str, max_chars: int) -> list[dict]:
    full_text = "\n\n".join([normalize_ws(p.get("text", "")) for p in pages if p.get("text")])
    if not full_text:
        return []

    # Match: "Điều 1.", "Điều 1 " hoặc "Điều 1:"...
    article_re = re.compile(r"(Điều\s+(\d+)\b)", flags=re.IGNORECASE)
    matches = list(article_re.finditer(full_text))
    if not matches:
        # Dự phòng: nếu không tách theo "Điều", tạo chunk theo "Toàn văn" để không bị rỗng.
        fallback_text = normalize_ws(full_text)
        sub_texts = split_if_too_long(fallback_text, max_chars=max_chars)
        chunks: list[dict] = []
        for sub_i, sub_text in enumerate(sub_texts):
            chunk_id = f"{doc_id}_full_s{sub_i}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "law_number": law_number,
                    "title": title,
                    "article_ref": "Toàn văn",
                    "page_start": None,
                    "page_end": None,
                    "chunk_text": sub_text,
                }
            )
        return chunks

    chunks: list[dict] = []
    for idx, m in enumerate(matches):
        article_no = int(m.group(2))
        start = m.start(1)
        end = matches[idx + 1].start(1) if idx + 1 < len(matches) else len(full_text)
        article_text = normalize_ws(full_text[start:end])
        if not article_text:
            continue

        page_start = find_first_page_containing_article(pages, article_no)
        page_end = page_start  # Demo: chưa suy ra end chính xác (có thể mở rộng sau)

        sub_texts = split_if_too_long(article_text, max_chars=max_chars)
        for sub_i, sub_text in enumerate(sub_texts):
            chunk_id = f"{doc_id}_a{article_no}_s{sub_i}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "law_number": law_number,
                    "title": title,
                    "article_ref": f"Điều {article_no}",
                    "page_start": page_start,
                    "page_end": page_end,
                    "chunk_text": sub_text,
                }
            )
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc-id", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-chars", type=int, default=2500)
    args = parser.parse_args()

    manifest = json.loads((RAW_LAWS_DIR / "manifest.json").read_text(encoding="utf-8"))
    PROCESSED_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    for doc in manifest:
        doc_id = doc["doc_id"]
        if args.doc_id and doc_id != args.doc_id:
            continue

        text_path = PROCESSED_TEXT_DIR / f"{doc_id}.json"
        if not text_path.exists():
            raise FileNotFoundError(f"Thiếu text: {text_path}. Hãy chạy extract_text trước.")

        out_path = PROCESSED_CHUNKS_DIR / f"{doc_id}.jsonl"
        if out_path.exists() and not args.force:
            print(f"SKIP {doc_id} (đã tồn tại)")
            continue

        raw = json.loads(text_path.read_text(encoding="utf-8"))
        pages = raw.get("pages", [])
        print(f"CHUNK {doc_id}")
        chunks = chunk_by_article(
            pages=pages,
            doc_id=doc_id,
            law_number=doc["law_number"],
            title=doc["title"],
            max_chars=args.max_chars,
        )

        with out_path.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        print(f"WROTE {len(chunks)} chunks -> {out_path.name}")

    print("DONE legal_chunker")


if __name__ == "__main__":
    main()

