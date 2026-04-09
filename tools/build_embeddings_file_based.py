from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import joblib
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHUNKS_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"


def iter_chunk_records() -> list[dict]:
    chunk_files = sorted(CHUNKS_DIR.glob("*.jsonl"))
    if not chunk_files:
        raise RuntimeError(
            f"Không tìm thấy chunks tại {CHUNKS_DIR}. Hãy chạy extract_text + legal_chunker trước."
        )

    records: list[dict] = []
    for cf in chunk_files:
        with cf.open("r", encoding="utf-8") as f:
            for line in f:
                records.append(json.loads(line))
    return records


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="Xoá vector store rồi build lại")
    parser.add_argument("--max-chunks", type=int, default=0, help="0 = không giới hạn")
    args = parser.parse_args()

    persist_dir = PROJECT_ROOT / os.getenv("VECTOR_STORE_DIR", "data/vector_db/file_based_demo")
    persist_dir.mkdir(parents=True, exist_ok=True)
    vectorizer_path = persist_dir / os.getenv("TFIDF_VECTORIZER_FILENAME", "vectorizer.joblib")
    matrix_path = persist_dir / os.getenv("TFIDF_MATRIX_FILENAME", "tfidf_matrix.joblib")
    metas_path = persist_dir / os.getenv("METAS_FILENAME", "metadatas.jsonl")

    if args.rebuild:
        if vectorizer_path.exists():
            vectorizer_path.unlink()
        if matrix_path.exists():
            matrix_path.unlink()
        if metas_path.exists():
            metas_path.unlink()

    if vectorizer_path.exists() and matrix_path.exists() and metas_path.exists() and not args.rebuild:
        print(f"SKIP (already exists): {vectorizer_path.name}")
        return

    records = iter_chunk_records()
    if args.max_chunks and args.max_chunks > 0:
        records = records[: args.max_chunks]
    if not records:
        raise RuntimeError("Không có chunk để embed.")

    # Tạo embedding theo batch
    chunk_texts = [r["chunk_text"] for r in records]
    meta_records = []
    for r in records:
        meta_records.append(
            {
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "law_number": r.get("law_number"),
                "title": r.get("title"),
                "article_ref": r.get("article_ref"),
                "page_start": r.get("page_start"),
                "page_end": r.get("page_end"),
                "chunk_text": r.get("chunk_text"),
                "business_group": (r.get("business_group") or "general"),
            }
        )

    # Windows console đôi khi không encode được ký tự tiếng Việt (CP1252),
    # nên giữ log thuần ASCII để tránh UnicodeEncodeError.
    print(f"Building TF-IDF index for {len(chunk_texts)} chunks ...")

    vectorizer = TfidfVectorizer(
        max_features=50000,
        ngram_range=(1, 2),
        lowercase=True,
    )
    tfidf_matrix = vectorizer.fit_transform(chunk_texts)

    joblib.dump(vectorizer, vectorizer_path)
    joblib.dump(tfidf_matrix, matrix_path)
    with metas_path.open("w", encoding="utf-8") as f:
        for m in meta_records:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    print(f"DONE build_embeddings_file_based (TF-IDF) -> {persist_dir}")


def rebuild_tfidf_vector_store(*, project_root: Path | None = None) -> Path:
    """Xoá vectorizer/matrix/metas cũ và build lại từ toàn bộ *.jsonl trong CHUNKS_DIR."""
    root = project_root or PROJECT_ROOT
    load_dotenv(root / ".env")
    persist_dir = root / os.getenv("VECTOR_STORE_DIR", "data/vector_db/file_based_demo")
    persist_dir.mkdir(parents=True, exist_ok=True)
    vectorizer_path = persist_dir / os.getenv("TFIDF_VECTORIZER_FILENAME", "vectorizer.joblib")
    matrix_path = persist_dir / os.getenv("TFIDF_MATRIX_FILENAME", "tfidf_matrix.joblib")
    metas_path = persist_dir / os.getenv("METAS_FILENAME", "metadatas.jsonl")
    for p in (vectorizer_path, matrix_path, metas_path):
        if p.exists():
            p.unlink()
    records = iter_chunk_records()
    if not records:
        raise RuntimeError("Không có chunk để embed.")
    chunk_texts = [r["chunk_text"] for r in records]
    meta_records = []
    for r in records:
        meta_records.append(
            {
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "law_number": r.get("law_number"),
                "title": r.get("title"),
                "article_ref": r.get("article_ref"),
                "page_start": r.get("page_start"),
                "page_end": r.get("page_end"),
                "chunk_text": r.get("chunk_text"),
                "business_group": (r.get("business_group") or "general"),
            }
        )
    vectorizer = TfidfVectorizer(
        max_features=50000,
        ngram_range=(1, 2),
        lowercase=True,
    )
    tfidf_matrix = vectorizer.fit_transform(chunk_texts)
    joblib.dump(vectorizer, vectorizer_path)
    joblib.dump(tfidf_matrix, matrix_path)
    with metas_path.open("w", encoding="utf-8") as f:
        for m in meta_records:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    return persist_dir


if __name__ == "__main__":
    main()

